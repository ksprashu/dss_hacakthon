# Piezo Texture Sensor — Hardware & Signal Guide

## Purpose

Use a piezo disc as a **texture vibration sensor** by capturing surface-induced vibrations as audio.

---

## Signal Architecture

```
Surface → Plastic coupling disc → Piezo → 3.5mm mic jack → USB sound card → ALSA → WAV
```

Texture is treated as **vibration**, not pressure.

---

## Electrical Wiring

### Polarity

* Ceramic side → Signal (+)
* Brass side → Ground (–)

### Protection & Stability

* **1 MΩ resistor across piezo + and –** (mandatory)
* Optional: **22–47 kΩ series resistor** on signal if clipping occurs

### TRS Jack Mapping

* Tip → Piezo + (ceramic)
* Sleeve → Piezo – (brass)
* Ring → Not connected

Do not short Tip and Ring unless explicitly required by the sound card.

---

## Mechanical Mounting (Critical)

* Mount piezo to a **thin, mildly flexible plastic disc**
* Glue **only the rim** (B7000 or tape)
* Center must remain free to flex
* Texture contacts plastic, not ceramic

The piezo should behave like a **drum skin**, not a rigid plate.

---

## Verification (CLI)

### Record

```bash
arecord -D plughw:2,0 -f S16_LE -r 44100 -d 5 /tmp/piezo.wav
```

### Inspect

```bash
sox /tmp/piezo.wav -n stat
```

Healthy reference:

* Peak amplitude ≈ 0.5–0.6
* RMS ≈ 0.05

### Remove DC Bias

```bash
sox /tmp/piezo.wav /tmp/piezo_nodc.wav highpass 20
```

Minor SoX clipping warnings are normal for piezo impulses.

