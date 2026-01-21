# Hardware Bring‑Up Guide — Raspberry Pi 5 Texture Sensing Stack

This document is the **ground‑truth setup and troubleshooting guide** for bringing up a mixed‑signal sensing stack on **Raspberry Pi 5**:

> This document captures the full bring-up context and reasoning.
> For setup instructions, see _README.md_ and _docs/_.

* Piezo‑based **texture sensor** via USB audio
* **Grove Base HAT**
* **16×2 Grove LCD (I²C)**
* **Grove DHT Temp/Humidity sensor (Digital)**
* **Grove Button + LED (Digital)**

It is written to prevent re‑learning painful lessons caused by outdated tutorials, Pi 5 GPIO changes, and modern Debian Python constraints.

---

## Repository Structure (Recommended)

```
project-root/
├── HARDWARE_BRINGUP.md        # This document
├── README.md                  # Project overview (ML + sensing)
├── docs/
│   ├── piezo.md               # Piezo sensor theory + wiring
│   ├── grove.md               # Grove Base HAT + sensors
│   ├── gpio.md                # GPIO model on Pi 5
│   └── testing.md             # Known‑good test checklist
├── scripts/
│   ├── lcd_test.py
│   ├── dht_test.py
│   └── button_led_test.py
└── data/
    └── textures/
```

---

# PART A — Piezo Texture Sensor

## A1. Signal Architecture

```
Surface
  ↓
Plastic coupling disc
  ↓
Piezo disc
  ↓
3.5mm mic jack
  ↓
USB audio dongle
  ↓
ALSA (arecord)
  ↓
WAV → DSP / ML
```

This design treats **texture as vibration**, not pressure.

---

## A2. Piezo Wiring (Electrical)

### Polarity

* **Ceramic side → signal (+)**
* **Brass side → ground (–)**

### Protection & Stability

* **1 MΩ resistor across piezo + and –** (mandatory)
* Optional: **22–47 kΩ series resistor** on signal line if clipping occurs

### TRS Jack Mapping

```
Tip     → Piezo + (ceramic)
Sleeve → Piezo – (brass)
Ring   → Not connected
```

Do **not** short Tip and Ring unless a sound card explicitly requires it.

---

## A3. Mechanical Mounting (Critical)

**Do NOT glue the entire piezo flat.**

Correct approach:

* Mount piezo to a **thin, mildly flexible plastic disc**
* Glue **only the rim** (B7000 or tape)
* Center must remain free to flex
* Texture contacts plastic, *not* ceramic

The piezo must behave like a **drum skin**, not a rigid plate.

---

## A4. Verifying Piezo Signal (CLI)

### Record

```bash
arecord -D plughw:2,0 -f S16_LE -r 44100 -d 5 /tmp/piezo.wav
```

### Inspect

```bash
sox /tmp/piezo.wav -n stat
```

Healthy reference values observed:

* Peak amplitude ≈ 0.5–0.6
* RMS ≈ 0.05
* No hard clipping

### Remove DC bias

```bash
sox /tmp/piezo.wav /tmp/piezo_nodc.wav highpass 20
```

Small SoX clipping warnings are normal for piezo impulse spikes.

---

# PART B — Grove Base HAT + Sensors

## B1. Baseline I²C Sanity Check

With **no sensors connected**:

```bash
sudo i2cdetect -y 1
```

Expected:

```
0x08
```

`0x08` = Grove Base HAT controller. This confirms:

* I²C enabled
* HAT seated correctly
* Power + SDA/SCL OK

---

## B2. LCD (Grove 16×2)

### Detection

After plugging into any I²C port:

```bash
sudo i2cdetect -y 1
```

Expected:

```
0x08  0x3e
```

* `0x3e` = LCD backpack
* Backlight ON confirms power

### Known LCD Gotcha

The first character is **often dropped** if written immediately after `clear()`.

**Correct pattern:**

```python
lcd.clear()
time.sleep(0.05)
lcd.setCursor(0, 0)
lcd.write("Hello Grove!   ")
```

This is a controller timing quirk, not a software bug.

---

## B3. Temp / Humidity Sensor (DHT)

* Port: **D5**
* GPIO: **BCM GPIO5**
* Protocol: **Digital (timing‑based)**

Important:

* DHT sensors are **NOT I²C**
* They will **never appear** in `i2cdetect`
* This is correct behavior

---

## B4. Button + LED

* Digital GPIO
* Not visible in I²C scans

CLI testing:

```bash
gpioinfo
gpioget gpiochip0 <pin>
gpioset gpiochip0 <pin>=1
```

---

# PART C — GPIO + Python on Raspberry Pi 5

## C1. The Rule

> **Never install `RPi.GPIO` via pip on Pi 5**

Pi 5 blocks `/dev/mem` GPIO access.

---

## C2. Correct GPIO Backend

```bash
sudo apt install python3-rpi-lgpio
```

This provides `RPi.GPIO` backed by **lgpio**.

Verify:

```bash
python -c "import RPi.GPIO as GPIO; print(GPIO.__file__)"
```

Must point to `/usr/lib/python3/dist-packages/...`

---

## C3. Python Environment (Safe Pattern)

```bash
python3 -m venv --system-site-packages ~/venvs/grove_sys
source ~/venvs/grove_sys/bin/activate
```

This allows:

* System GPIO libraries
* Local project packages

---

## C4. Installing grove.py (Correctly)

**Do NOT use Seeed install scripts.** They add obsolete Debian repos.

Correct install:

```bash
pip install --no-deps git+https://github.com/Seeed-Studio/grove.py
```

`--no-deps` prevents pip from pulling broken GPIO packages.

---

# PART D — Known‑Good Test Checklist

Use this checklist **in order**.

### Power + Bus

* [ ] `i2cdetect` shows `0x08`
* [ ] LCD address (`0x3e`) visible

### LCD

* [ ] Backlight on
* [ ] Text prints with `clear() + delay`

### Digital IO

* [ ] Button readable via `gpioget`
* [ ] LED toggles via `gpioset`

### Piezo Audio

* [ ] WAV file recorded
* [ ] RMS amplitude ~0.05
* [ ] DC bias removed cleanly

If all checks pass, hardware is **known‑good**.

---

# PART E — Why This Matters

This setup is intentionally **boring and deterministic**:

* No magic libraries
* No implicit assumptions
* Every subsystem testable independently

This is the correct foundation for:

* Texture classification
* Multi‑modal ML (audio + vision + env data)
* Long‑running experiments without mystery failures

---

End of document.

