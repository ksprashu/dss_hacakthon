#!/usr/bin/env python3
import os
import time
import uuid
import threading
import subprocess
import json
import re
import enum

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from grove.grove_ryb_led_button import GroveLedButton
import board
import neopixel_spi as neopixel

from picamera2 import Picamera2
from libcamera import Transform, controls

from grove.display.jhd1802 import JHD1802

import RPi.GPIO as GPIO
import atexit

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

def _atexit_cleanup():
    try:
        GPIO.cleanup()
        controller.shutdown()
    except Exception:
        pass

atexit.register(_atexit_cleanup)

import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scan")


# Button event bitmasks
CLICK     = 2
DBLCLICK  = 4
LONGPRESS = 8
NOISE     = 16

# NeoPixel ring
NUM_PIXELS = 24
MAX_BRIGHTNESS = 0.1

# Storage
SCAN_ROOT = "./scans"

# Audio config (override with env var)
AUDIO_DEVICE = "hw:2,0"
AUDIO_RATE = 44100
AUDIO_CHANNELS = 1
AUDIO_FORMAT = "S16_LE"


app = FastAPI(title="Hackathon Capture Service", version="0.1.0")

def get_stat(parsed: dict, key: str):
    """
    Safe lookup for SoX stat keys that may contain weird spacing.
    """
    return parsed.get(key) or parsed.get(re.sub(r"\s+", " ", key))

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def run_cmd(cmd: list[str], *, timeout: int | None = None) -> str:
    log.info("CMD start: %s", " ".join(cmd))
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,   # IMPORTANT: don't raise automatically
        )
        out = (p.stdout or "").strip()
        if out:
            log.info("CMD output:\n%s", out)
        if p.returncode != 0:
            raise RuntimeError(f"Command failed rc={p.returncode}: {' '.join(cmd)}")
        log.info("CMD ok: %s", " ".join(cmd))
        return out
    except Exception as e:
        log.exception("CMD exception: %s", e)
        raise


def _fit_16(s: str) -> str:
    s = (s or "")
    return s[:16].ljust(16)


def json_safe(obj):
    """Convert libcamera / numpy / enum-rich structures into JSON-serializable types."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # libcamera enums are Python Enums
    if isinstance(obj, enum.Enum):
        return obj.name  # or obj.value

    # common tuple/list containers
    if isinstance(obj, (list, tuple)):
        return [json_safe(x) for x in obj]

    # dict-like
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}

    # numpy scalars (if any show up)
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            return obj.item()
    except Exception:
        pass

    # fallback: string representation
    return str(obj)


def record_audio_wav(out_wav: str, duration_s: int):
    cmd = [
        "arecord",
        "-D", "hw:2,0",
        "-f", "S16_LE",
        "-r", "44100",
        "-c", "1",
        "-d", str(duration_s),
        out_wav,
    ]
    log.info("Recording texture audio: %s", " ".join(cmd))
    run_cmd(cmd)


def sox_remove_dc(in_wav: str, out_wav: str) -> str:
    cmd = ["sox", in_wav, out_wav, "gain", "-1", "highpass", "20"]
    return run_cmd(cmd)


def sox_stat(wav_path):
    out = run_cmd(["sox", wav_path, "-n", "stat"])
    parsed = {}

    for line in out.splitlines():
        if ":" not in line:
            continue

        key, val = line.split(":", 1)

        # Collapse any crazy whitespace to a single space
        key = re.sub(r"\s+", " ", key.strip())

        # Take the first token of the value (numeric)
        val = val.strip().split()[0]
        try:
            val = float(val)
        except ValueError:
            pass

        parsed[key] = val

    return {"raw": out, "parsed": parsed}


def sox_spectrogram(in_wav: str, out_png: str) -> str:
    return run_cmd(["sox", in_wav, "-n", "spectrogram", "-o", out_png])


def sox_normalize(in_wav: str, out_wav: str, peak_db: float = -6.0) -> str:
    """
    Normalize audio so peak is at `peak_db` dBFS (negative value).
    -6 dBFS gives good headroom.
    """
    cmd = [
        "sox",
        in_wav,
        out_wav,
        "norm",
        str(peak_db),
    ]
    return run_cmd(cmd)


def init_camera():
    cam = Picamera2()

    # Still config (tune size as you like)
    cfg = cam.create_still_configuration(
        main={"size": (1920, 1080)},
        transform=Transform(rotation=180),  # <-- rotate once, globally
        controls={
            "AeEnable": True,
            "AwbEnable": True,
            "AfMode": controls.AfModeEnum.Continuous,  # start in continuous
        },
    )
    cam.configure(cfg)
    cam.start()
    time.sleep(1.0)  # Let sensor + ISP settle

    log.info("Camera initialized (still, 1920x1080, rotated)")
    return cam


def capture_locked(cam: Picamera2, path: str, settle_s: float = 0.6):
    # 1) Let AE/AWB settle on current lighting
    cam.set_controls({"AeEnable": True, "AwbEnable": True, "AfMode": controls.AfModeEnum.Continuous})
    time.sleep(settle_s)

    # 2) Trigger AF once (more deterministic than hoping continuous AF is done)
    cam.set_controls({"AfMode": controls.AfModeEnum.Auto, "AfTrigger": controls.AfTriggerEnum.Start})
    time.sleep(0.5)

    # 3) Read metadata and lock exposure + white balance + focus
    md = cam.capture_metadata()

    lock = {}

    # Lock exposure: use whatever AE decided
    if "ExposureTime" in md:
        lock["ExposureTime"] = md["ExposureTime"]
    if "AnalogueGain" in md:
        lock["AnalogueGain"] = md["AnalogueGain"]
    lock["AeEnable"] = False

    # Lock white balance
    if "ColourGains" in md:
        lock["ColourGains"] = md["ColourGains"]
    lock["AwbEnable"] = False

    # Lock focus (LensPosition exists on AF cameras)
    if "LensPosition" in md:
        lock["LensPosition"] = md["LensPosition"]
    lock["AfMode"] = controls.AfModeEnum.Manual

    cam.set_controls(lock)

    # 4) Capture
    cam.capture_file(path)
    return md, lock


@dataclass
class ScanStatus:
    state: str = "IDLE"
    scan_id: Optional[str] = None
    started_at: Optional[float] = None
    message: str = ""
    progress: float = 0.0


class LabelPayload(BaseModel):
    label: str = Field(..., description="Human label for the scanned cloth/item")
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


class Buzzer:
    def __init__(self, pin: int):
        self.pin = pin
        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, GPIO.LOW)
        log.info("Buzzer ready on GPIO%d", pin)

    def beep(self, duration=0.15):
        if GPIO.getmode() is None:
            GPIO.setmode(GPIO.BCM)

        GPIO.output(self.pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(self.pin, GPIO.LOW)

    def triple(self):
        for _ in range(3):
            self.beep(0.12)
            time.sleep(0.08)

    def long(self):
        self.beep(0.4)


class ScanController:
    def __init__(self):
        self.status = ScanStatus()
        self._lock = threading.Lock()
        self._busy = threading.Event()

        self.buzzer = Buzzer(22)

        # LED button
        self.ledbtn = GroveLedButton(26)
        self.led_state = {"on": False}
        self.ledbtn.on_event = self._handle_button_event

        # Ring
        self.pixels = neopixel.NeoPixel_SPI(
            board.SPI(),
            NUM_PIXELS,
            pixel_order=neopixel.GRB,
            brightness=0.0,
            auto_write=False,
        )
        self.pixels.fill((0, 0, 0))
        self.pixels.show()

        # Pi Camera
        self.cam = init_camera()

        ensure_dir(SCAN_ROOT)

        # LCD
        self.lcd = JHD1802()
        self.lcd_lock = threading.Lock()

        # optional boot message
        self.lcd_write("Texture scanner", "Ready...")

    def shutdown(self):
        # stop camera cleanly
        try:
            if self.cam is not None:
                log.info("Stopping camera...")
                self.cam.stop()
        except Exception as e:
            log.warning("Camera stop failed: %s", e)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return asdict(self.status)

    def lcd_write(self, line1: str, line2: str = "") -> None:
        try:
            l1, l2 = _fit_16(line1), _fit_16(line2)
            with self.lcd_lock:
                self.lcd.setCursor(0, 0)
                self.lcd.write(l1)
                self.lcd.setCursor(1, 0)
                self.lcd.write(l2)
        except Exception as e:
            log.warning("LCD write failed: %s", e)


    def lcd_step(self, step: str, detail: str = "") -> None:
        """Convenience wrapper for step/status display."""
        # Keep step short; detail can be label/color/timer/etc.
        self.lcd_write(step, detail)

    def start_scan(self) -> str:
        with self._lock:
            if self._busy.is_set():
                raise RuntimeError("Scan already in progress")
            scan_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            self.status = ScanStatus(
                state="ARMING",
                scan_id=scan_id,
                started_at=time.time(),
                message="Arming scan...",
                progress=0.05,
            )
            self._busy.set()

        t = threading.Thread(target=self._run_scan, args=(scan_id,), daemon=True)
        t.start()
        return scan_id

    def label_scan(self, scan_id: str, payload: LabelPayload) -> None:
        scan_dir = os.path.join(SCAN_ROOT, scan_id)
        if not os.path.isdir(scan_dir):
            raise FileNotFoundError("Unknown scan_id")
        with open(os.path.join(scan_dir, "label.json"), "w", encoding="utf-8") as f:
            json.dump(payload.model_dump(), f, indent=2)

    def _set_button_led(self, on: bool) -> None:
        try:
            self.ledbtn.led.light(on)
            self.led_state["on"] = on
        except Exception as e:
            print("LED set error:", e)

    def _handle_button_event(self, index, code, t):
        if GPIO.getmode() is None:
            GPIO.setmode(GPIO.BCM)

        if code == NOISE:
            return
        if code & CLICK:
            try:
                self.start_scan()
            except RuntimeError:
                pass
        elif code & LONGPRESS:
            self._set_button_led(False)

    def _ring_off(self):
        self.pixels.brightness = 0.0
        self.pixels.fill((0, 0, 0))
        self.pixels.show()

    def _ring_set(self, rgb, brightness=MAX_BRIGHTNESS):
        self.pixels.brightness = clamp(brightness, 0.0, MAX_BRIGHTNESS)
        self.pixels.fill(rgb)
        self.pixels.show()

    def _run_scan(self, scan_id: str):
        scan_dir = os.path.join(SCAN_ROOT, scan_id)
        ensure_dir(scan_dir)

        def update(state, msg, prog):
            with self._lock:
                self.status.state = state
                self.status.message = msg
                self.status.progress = prog

        log.info("=== SCAN BEGIN %s ===", scan_id)
        self.lcd_step("Scan started", scan_id[-8:])

        try:
            self._set_button_led(True)
            update("LABEL", "Waiting for terminal label...", 0.05)
            self.lcd_step("Enter label", "in terminal...")

            # 1) Terminal prompt (blocking by design)
            log.info("Prompting for label in terminal...")
            label = input(f"[{scan_id}] Enter item label: ").strip()
            if not label:
                label = "unlabeled"
            log.info("Label = %r", label)
            self.lcd_step("Label set", label[:16])


            # Save label immediately
            with open(os.path.join(scan_dir, "label.txt"), "w", encoding="utf-8") as f:
                f.write(label + "\n")

            # 2) 3 second “position item” window
            update("POSITION", "Position item (3s)...", 0.10)
            log.info("Waiting 3 seconds for user to position item...")
            for i in range(3, 0, -1):
              self.lcd_step("Position item", f"starting in {i}")
              time.sleep(1.0)

            # 3) Beep: capture starting
            log.info("Beep: starting lighting + snapshots")
            self.buzzer.triple()

            # 4) Ring color cycle + snapshots
            update("IMAGES", "Capturing images under 3 lights...", 0.25)

            # Freeze exposure after initial settle
            self.cam.set_controls({
                "AeEnable": False,
            })

            # Warm daylight, neutral, cool
            schedule = [
                ((255, 140, 60), "warm.jpg", "warm"),
                ((255, 255, 255), "neutral.jpg", "neutral"),
                ((120, 160, 255), "cool.jpg", "cool"),
            ]

            self.lcd_step("Taking photos", "warm/neutral/cool")
            for rgb, filename, name in schedule:
                log.info("Ring -> %s (%s)", name, rgb)
                self._ring_set(rgb, brightness=MAX_BRIGHTNESS)

                self.lcd_step("Photo", name)  # name is warm/neutral/cool
                img_path = os.path.join(scan_dir, filename)
                md, lock = capture_locked(self.cam, img_path)

                # Optional: save metadata to debug exposure/focus
                try:
                    with open(img_path.replace(".jpg", ".meta.json"), "w") as f:
                        json.dump(json_safe({"metadata": md, "lock": lock}), f, indent=2)
                except Exception as e:
                    log.warning("Failed to write metadata JSON: %s", e)

                time.sleep(0.2)  # small gap

            self.cam.set_controls({
                "AeEnable": True,
            })

            # 5) Beep: entering texture mode, ring OFF
            log.info("Beep: entering texture mode; ring OFF")
            self.buzzer.triple()
            self._ring_off()
            self.lcd_step("Texture mode", "get ready")

            # 6) Beep, wait 2s
            log.info("Beep: texture starts in 5 seconds")
            self.buzzer.triple()
            for i in range(5, 0, -1):
              self.lcd_step("Texture in", f"{i} sec")
              time.sleep(1.0)

            # 7) Beep: start texture capture
            log.info("Beep: START texture audio capture (3s)")
            self.buzzer.long()

            update("TEXTURE", "Recording texture audio (3s)...", 0.70)

            audio_raw = os.path.join(scan_dir, "texture_raw.wav")
            audio_nodc = os.path.join(scan_dir, "texture_nodc.wav")
            audio_norm = os.path.join(scan_dir, "texture_norm.wav")
            spec_png = os.path.join(scan_dir, "texture_nodc.png")

            # record 3 seconds
            arecord_log = record_audio_wav(audio_raw, duration_s=3)

            # 8) Beep: done
            log.info("Beep: texture capture done")
            self.buzzer.long()

            update("PROCESSING", "Post-processing audio...", 0.85)

            # ---- DC removal ----
            self.lcd_step("Processing", "DC remove")
            sox_dc_log = sox_remove_dc(audio_raw, audio_nodc)

            raw_stats = sox_stat(audio_raw)
            log.info("RAW  RMS=%s MAX=%s MID=%s",
                get_stat(raw_stats["parsed"], "RMS amplitude"),
                get_stat(raw_stats["parsed"], "Maximum amplitude"),
                get_stat(raw_stats["parsed"], "Midline amplitude"))

            nodc_stats = sox_stat(audio_nodc)
            log.info("NODC RMS=%s MAX=%s MID=%s",
                get_stat(nodc_stats["parsed"], "RMS amplitude"),
                get_stat(nodc_stats["parsed"], "Maximum amplitude"),
                get_stat(nodc_stats["parsed"], "Midline amplitude"))

            # ---- NORMALIZATION (this was missing) ----
            self.lcd_step("Processing", "normalize")
            sox_norm_log = sox_normalize(audio_nodc, audio_norm, peak_db=-6.0)

            norm_stats = sox_stat(audio_norm)
            log.info("NORM RMS=%s MAX=%s MID=%s",
                get_stat(norm_stats["parsed"], "RMS amplitude"),
                get_stat(norm_stats["parsed"], "Maximum amplitude"),
                get_stat(norm_stats["parsed"], "Midline amplitude"))

            # ---- Spectrogram (still from nodc) ----
            spec_ok = True
            try:
                self.lcd_step("Processing", "spectrogram")
                sox_spectrogram(audio_nodc, spec_png)
            except Exception:
                spec_ok = False
                log.warning("Spectrogram failed (continuing)")

            results = {
                "scan_id": scan_id,
                "label": label,
                "audio": {
                    "device": AUDIO_DEVICE,
                    "raw_wav": os.path.basename(audio_raw),
                    "nodc_wav": os.path.basename(audio_nodc),
                    "norm_wav": os.path.basename(audio_norm),
                    "spectrogram_png": os.path.basename(spec_png) if spec_ok else None,
                    "arecord_log": arecord_log,
                    "sox_dc_log": sox_dc_log,
                    "sox_norm_log": sox_norm_log,
                    "stats_raw": raw_stats,
                    "stats_nodc": nodc_stats,
                    "stats_norm": norm_stats,
                },
                "images": {
                    "warm": "warm.jpg",
                    "neutral": "neutral.jpg",
                    "cool": "cool.jpg",
                },
            }

            with open(os.path.join(scan_dir, "results.json"), "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)

            update("DONE", "Scan complete", 1.0)
            log.info("=== SCAN DONE %s ===", scan_id)
            self.lcd_step("Done", label[:16])

        except Exception as e:
            update("ERROR", str(e), 1.0)
            log.exception("=== SCAN ERROR %s ===", scan_id)

        finally:
            self._ring_off()
            self._set_button_led(False)
            self._busy.clear()
            log.info("Cleanup complete; back to IDLE")
            with self._lock:
                last_id = self.status.scan_id
                last_msg = self.status.message
            time.sleep(0.2)
            self.lcd_step("Idle", "Ready")
            with self._lock:
                self.status.state = "IDLE"
                self.status.scan_id = last_id
                self.status.message = last_msg
                self.status.progress = 0.0


controller = ScanController()

@app.get("/scan/status")
def scan_status():
    return controller.get_status()


@app.post("/scan/start")
def scan_start():
    try:
        scan_id = controller.start_scan()
        return {"ok": True, "scan_id": scan_id}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/scan/{scan_id}/label")
def scan_label(scan_id: str, payload: LabelPayload):
    try:
        controller.label_scan(scan_id, payload)
        return {"ok": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="scan_id not found")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    # Now `python texture_server.py` will actually run the server.
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
