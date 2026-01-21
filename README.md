# Texture Sensing on Raspberry Pi 5

This project builds a **multi‑modal texture sensing system** on **Raspberry Pi 5**, combining:

* A **piezo‑based vibration sensor** (captured as audio)
* **Grove Base HAT** peripherals (LCD, button, temp/humidity)
* A clean, reproducible **hardware bring‑up process** suitable for ML experiments

The goal is to treat *texture as signal*, not as a one‑off electronics demo.

---

## Start Here (Order Matters)

If you are setting this up on a fresh Pi, read the docs **in this order**:

1. **`docs/piezo.md`**
   Electrical + mechanical setup of the piezo texture sensor, audio capture, and signal sanity checks.

2. **`docs/grove.md`**
   Grove Base HAT bring‑up, LCD quirks, digital vs I²C sensors, and correct port usage.

3. **`docs/testing.md`**
   Known‑good checklist to confirm hardware, GPIO, audio, and Python are all working *before* writing application code.

Only after these pass should you move on to feature extraction, ML, or vision integration.

---

## Why This Repo Is Structured This Way

Raspberry Pi 5 introduces real changes:

* GPIO access is different
* `RPi.GPIO` behaves differently
* Python packaging is PEP‑668 locked
* Many Grove tutorials target obsolete OS versions

This repository documents **what actually works** on modern Pi 5 + Debian/Trixie, without relying on outdated assumptions.

---

## Scope (What This Repo Is *Not*)

* Not a beginner GPIO tutorial
* Not a copy of the Grove wiki
* Not a one‑off electronics hack

This is a **repeatable sensing platform** meant to support data collection and ML experimentation.

---

## High‑Level Architecture

```
Surface texture
   ↓
Piezo vibration
   ↓
Audio waveform
   ↓
DSP / Feature extraction
   ↓
ML classification

(With LCD + button + env sensors for labeling and context)
```

---

## Quick Sanity Check

If you’re unsure whether your setup is healthy:

→ Go directly to **`docs/testing.md`** and run the checklist top to bottom.

If it passes, the hardware is known‑good.

---

End of README.

