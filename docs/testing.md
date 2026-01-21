# Hardware Bring-Up — Known-Good Test Checklist

Use this checklist **in order** to verify hardware correctness before writing application code.

---

## Power & Bus

* [ ] `sudo i2cdetect -y 1` shows `0x08`
* [ ] LCD address (`0x3e`) visible

---

## LCD

* [ ] Backlight ON
* [ ] Text prints using `clear()` + delay

---

## Digital IO

* [ ] Button readable via `gpioget`
* [ ] LED toggles via `gpioset`

---

## Piezo Audio

* [ ] WAV file recorded via `arecord`
* [ ] RMS amplitude ≈ 0.05
* [ ] DC bias removable via SoX

---

## GPIO & Python (Pi 5)

### Mandatory

* [ ] `python3-rpi-lgpio` installed
* [ ] `RPi.GPIO` imported from `/usr/lib/python3/dist-packages`

Verify:

```bash
python -c "import RPi.GPIO as GPIO; print(GPIO.__file__)"
```

---

## Python Environment

* [ ] Venv created with `--system-site-packages`
* [ ] `grove.py` installed with `--no-deps`

---

## Pass Criteria

If all boxes are checked, the system is **hardware-known-good** and safe to proceed to ML and application logic.

