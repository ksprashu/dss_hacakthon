#!/usr/bin/env python3

import time
import threading
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from seeed_dht import DHT
from grove.display.jhd1802 import JHD1802

app = FastAPI(title="Pi Sensor Service", version="0.3.0")

sensor = DHT("11", 5)
lcd = JHD1802()

data_lock = threading.Lock()
lcd_lock = threading.Lock()

latest_data = {"temperature": None, "humidity": None, "timestamp": None}


def _fit_16(s: str) -> str:
    s = (s or "")
    return s[:16].ljust(16)


def lcd_write_16x2(line1: str, line2: str) -> None:
    l1, l2 = _fit_16(line1), _fit_16(line2)
    with lcd_lock:
        lcd.setCursor(0, 0)
        lcd.write(l1)
        lcd.setCursor(1, 0)
        lcd.write(l2)


def read_sensor_once():
    humi, temp = sensor.read()
    if humi is None or temp is None:
        raise RuntimeError("DHT read returned None")
    return humi, temp


def sensor_loop(poll_interval=2):
    while True:
        try:
            humi, temp = read_sensor_once()
            with data_lock:
                latest_data["temperature"] = temp
                latest_data["humidity"] = humi
                latest_data["timestamp"] = time.time()
        except Exception as e:
            # Keep loop alive even if DHT flakes out
            print("Sensor read error:", e)
        time.sleep(poll_interval)


@app.on_event("startup")
def start_sensor_thread():
    t = threading.Thread(target=sensor_loop, daemon=True)
    t.start()
    lcd_write_16x2("Ready...", "")


@app.get("/temp")
def get_temp(
    fresh: bool = Query(False, description="If true, force a fresh sensor read now"),
    max_age_s: int = Query(10, description="Reject cached readings older than this (unless fresh=true)"),
):
    # Optionally force a fresh read
    if fresh:
        try:
            humi, temp = read_sensor_once()
            with data_lock:
                latest_data["temperature"] = temp
                latest_data["humidity"] = humi
                latest_data["timestamp"] = time.time()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Sensor read failed: {e}")

    with data_lock:
        temp = latest_data["temperature"]
        humi = latest_data["humidity"]
        ts = latest_data["timestamp"]

    if temp is None or humi is None or ts is None:
        raise HTTPException(status_code=503, detail="Sensor not ready")

    age = time.time() - ts
    if not fresh and age > max_age_s:
        raise HTTPException(status_code=503, detail=f"Sensor data stale ({age:.1f}s old)")

    # Update LCD only when /temp is called (your requirement)
    lcd_write_16x2(f"Temp: {temp} C", f"Humi: {humi} %")

    return {
        "temperature_c": temp,
        "humidity_percent": humi,
        "timestamp": ts,
        "age_s": round(age, 2),
    }


class LCDPayload(BaseModel):
    line1: str = Field(default="")
    line2: str = Field(default="")


@app.post("/lcd")
def post_lcd(payload: LCDPayload):
    try:
        lcd_write_16x2(payload.line1, payload.line2)
        return {"ok": True, "written": {"line1": _fit_16(payload.line1), "line2": _fit_16(payload.line2)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LCD write failed: {e}")


@app.get("/health")
def health():
    return {"status": "ok"}

