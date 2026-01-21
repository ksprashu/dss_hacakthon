#!/usr/bin/env python3
import os
import time
import uuid
import threading
import subprocess
import json

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- Your existing imports (drivers) ---
from grove.grove_ryb_led_button import GroveLedButton
import board
import neopixel_spi as neopixel

# Camera: Picamera2 is typical on Pi OS (Bullseye/Bookworm).
# We'll wire it in once you confirm your stack; placeholder here.
# from picamera2 import Picamera2

# Audio: likely arecord / sounddevice; will finalize after your piezo doc.
# import subprocess

CLICK     = 2
DBLCLICK  = 4
LONGPRESS = 8
NOISE     = 16

NUM_PIXELS = 24
MAX_BRIGHTNESS = 0.3

SCAN_ROOT = "./scans"

app = FastAPI(title="Hackathon Capture Service", version="0.1.0")


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))

AUDIO_DEV = os.environ.get("AUDIO_DEV", "plughw:2,0")  # set this!
AUDIO_RATE = 44100
AUDIO_FORMAT = "S16_LE"
AUDIO_CHANNELS = 1

def run_cmd(cmd: list[str]) -> str:
    """Run a command and return stdout+stderr as text; raises on failure."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
    return p.stdout

def record_audio_wav(out_wav: str, duration_s: float) -> str:
    """
    Record mono WAV via ALSA arecord.
    Mirrors your doc’s approach (device, format, rate, duration). :contentReference[oaicite:6]{index=6}
    """
    cmd = [
        "arecord",
        "-D", AUDIO_DEV,
        "-f", AUDIO_FORMAT,
        "-r", str(AUDIO_RATE),
        "-c", str(AUDIO_CHANNELS),
        "-d", str(int(duration_s)),
        out_wav,
    ]
    return run_cmd(cmd)

def sox_remove_dc(in_wav: str, out_wav: str) -> str:
    """
    Remove DC bias using highpass 20Hz (mandatory per your doc). :contentReference[oaicite:7]{index=7}
    Also apply gain -1 to reduce clipping risk on spikes (optional path from doc). :contentReference[oaicite:8]{index=8}
    """
    cmd = ["sox", in_wav, out_wav, "gain", "-1", "highpass", "20"]
    return run_cmd(cmd)

def sox_stat(wav_path: str) -> dict:
    """
    Parse `sox <wav> -n stat` into a dict (RMS, max amp, etc.). :contentReference[oaicite:9]{index=9}
    """
    cmd = ["sox", wav_path, "-n", "stat"]
    out = run_cmd(cmd)
    stats = {}
    for line in out.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            stats[k.strip()] = v.strip()
    return {"raw": out, "parsed": stats}

def sox_spectrogram(in_wav: str, out_png: str) -> str:
    """Optional spectrogram for visual validation. :contentReference[oaicite:10]{index=10}"""
    cmd = ["sox", in_wav, "-n", "spectrogram", "-o", out_png]
    return run_cmd(cmd)

@dataclass
class ScanStatus:
    state: str = "IDLE"
    scan_id: Optional[str] = None
    started_at: Optional[float] = None
    message: str = ""
    progress: float = 0.0  # 0..1


class LabelPayload(BaseModel):
    label: str = Field(..., description="Human label for the scanned cloth/item")
    notes: Optional[str] = Field(default=None)
    tags: Optional[list[str]] = Field(default=None)


class ScanController:
    def __init__(self):
        self.status = ScanStatus()
        self._lock = threading.Lock()
        self._busy = threading.Event()
        self._stop = threading.Event()

        # --- LED Button (adjust pin as needed) ---
        self.ledbtn = GroveLedButton(26)
        self.led_state = {"on": False}

        # --- Ring light ---
        self.pixels = neopixel.NeoPixel_SPI(
            board.SPI(),
            NUM_PIXELS,
            pixel_order=neopixel.GRB,
            brightness=0.0,
            auto_write=False,
        )
        self.pixels.fill((0, 0, 0))
        self.pixels.show()

        # --- Camera placeholder ---
        # self.cam = Picamera2()
        # self.cam.configure(self.cam.create_still_configuration())
        # self.cam.start()

        # Button callback
        self.ledbtn.on_event = self._handle_button_event

        ensure_dir(SCAN_ROOT)

    # ---------- Public API ----------
    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return asdict(self.status)

    def start_scan(self) -> str:
        with self._lock:
            if self._busy.is_set():
                raise RuntimeError("Scan already in progress")
            scan_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            self.status = ScanStatus(state="ARMING", scan_id=scan_id, started_at=time.time(),
                                     message="Arming scan...", progress=0.05)
            self._busy.set()

        t = threading.Thread(target=self._run_scan, args=(scan_id,), daemon=True)
        t.start()
        return scan_id

    def label_scan(self, scan_id: str, payload: LabelPayload) -> None:
        scan_dir = os.path.join(SCAN_ROOT, scan_id)
        meta_path = os.path.join(scan_dir, "label.json")
        if not os.path.isdir(scan_dir):
            raise FileNotFoundError("Unknown scan_id")

        import json
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(payload.model_dump(), f, indent=2)

    # ---------- Button handling ----------
    def _set_button_led(self, on: bool) -> None:
        # GroveLedButton exposes ledbtn.led.light(on)
        try:
            self.ledbtn.led.light(on)
            self.led_state["on"] = on
        except Exception as e:
            print("LED set error:", e)

    def _handle_button_event(self, index, code, t):
        if code == NOISE:
            return
        if code & CLICK:
            # click starts scan
            try:
                self.start_scan()
            except RuntimeError:
                pass  # ignore if already scanning
        elif code & LONGPRESS:
            # longpress = emergency stop / clear
            self._set_button_led(False)

    # ---------- Ring light ----------
    def _ring_off(self):
        self.pixels.brightness = 0.0
        self.pixels.fill((0, 0, 0))
        self.pixels.show()

    def _ring_set(self, rgb, brightness=MAX_BRIGHTNESS):
        self.pixels.brightness = clamp(brightness, 0.0, MAX_BRIGHTNESS)
        self.pixels.fill(rgb)
        self.pixels.show()

    # ---------- Core scan pipeline ----------
    def _run_scan(self, scan_id: str):
        scan_dir = os.path.join(SCAN_ROOT, scan_id)
        ensure_dir(scan_dir)

        def update(state, msg, prog):
            with self._lock:
                self.status.state = state
                self.status.message = msg
                self.status.progress = prog

        try:
            # ---- EVERYTHING THAT CAN FAIL GOES HERE ----

            self._set_button_led(True)

            self._ring_set((255, 255, 255), brightness=MAX_BRIGHTNESS)
            update("ARMING", "Preparing scan...", 0.10)
            time.sleep(0.8)

            # ===============================
            # CAPTURE BLOCK (YOUR ERROR LINE)
            # ===============================
            update("CAPTURING", "Capturing 3s window...", 0.25)

            audio_raw = os.path.join(scan_dir, "audio_raw.wav")
            audio_nodc = os.path.join(scan_dir, "audio_nodc.wav")
            spec_png = os.path.join(scan_dir, "audio_nodc.png")

            t0 = time.time()

            def light_and_snapshots():
                schedule = [
                    (0.0, (255, 120, 30), "dawn"),
                    (1.0, (255, 255, 255), "noon"),
                    (2.0, (80, 120, 255), "dusk"),
                ]
                for offset, rgb, name in schedule:
                    while time.time() - t0 < offset:
                        time.sleep(0.005)
                    self._ring_set(rgb, brightness=MAX_BRIGHTNESS)
                    # camera capture later

            lt = threading.Thread(target=light_and_snapshots, daemon=True)
            lt.start()

            arecord_log = record_audio_wav(audio_raw, duration_s=3)
            lt.join(timeout=5)

            update("PROCESSING", "Processing audio...", 0.75)

            sox_dc_log = sox_remove_dc(audio_raw, audio_nodc)
            raw_stats = sox_stat(audio_raw)
            nodc_stats = sox_stat(audio_nodc)

            try:
                sox_spectrogram(audio_nodc, spec_png)
                spec_ok = True
            except Exception:
                spec_ok = False

            with open(os.path.join(scan_dir, "results.json"), "w") as f:
                json.dump({
                    "scan_id": scan_id,
                    "audio": {
                        "raw": "audio_raw.wav",
                        "nodc": "audio_nodc.wav",
                        "stats_raw": raw_stats,
                        "stats_nodc": nodc_stats,
                    }
                }, f, indent=2)

            update("DONE", "Scan complete", 1.0)

        except Exception as e:
            # ---- ANY FAILURE ENDS UP HERE ----
            update("ERROR", str(e), 1.0)
            print("Scan failed:", e)

        finally:
            # ---- ALWAYS CLEAN UP ----
            self._ring_off()
            self._set_button_led(False)
            self._busy.clear()

            with self._lock:
                last_id = self.status.scan_id
                last_msg = self.status.message

            time.sleep(0.2)

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

