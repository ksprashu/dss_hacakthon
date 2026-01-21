# Audio Validation & Signal Sanity — Piezo Texture Sensor

This document captures the **exact command-line steps** used to validate the piezo-based texture sensor using ALSA and SoX. These steps establish *ground truth* before any Python, DSP, or ML work.

---

## 0) Prerequisites

Install required tools once:

```bash
sudo apt update
sudo apt install -y alsa-utils sox
```

(Optional, for Grove/I²C work):

```bash
sudo apt install -y i2c-tools
```

---

## 1) Confirm USB Audio Device

List USB devices:

```bash
lsusb
```

List ALSA capture devices:

```bash
arecord -l
```

Example output:

```
card 2: Device [USB Audio Device], device 0: USB Audio [USB Audio]
```

This means the capture device is:

```
plughw:2,0
```

---

## 2) Record a Reference Sample (WAV)

Record 5 seconds at 44.1 kHz, 16-bit, mono:

```bash
arecord -D plughw:2,0 -f S16_LE -r 44100 -d 5 /tmp/piezo.wav
```

During recording:

* Tap the piezo lightly
* Rub across known textures (cotton, wood, felt, etc.)

Verify file creation:

```bash
ls -lh /tmp/piezo.wav
```

---

## 3) Numerical Signal Validation (SoX)

Inspect statistics:

```bash
sox /tmp/piezo.wav -n stat
```

Healthy reference values observed:

* Maximum amplitude ≈ 0.5–0.6
* RMS amplitude ≈ 0.05
* No constant hard clipping

This step confirms:

* Signal presence
* Reasonable gain
* No wiring faults

---

## 4) Remove DC Bias (Mandatory)

Piezo + mic inputs often introduce DC offset. Remove it with a high-pass filter:

```bash
sox /tmp/piezo.wav /tmp/piezo_nodc.wav highpass 20
```

Re-check stats:

```bash
sox /tmp/piezo_nodc.wav -n stat
```

Expected outcome:

* Mean amplitude ≈ 0
* RMS amplitude largely unchanged

### Note on Warnings

If you see:

```
highpass clipped N samples; decrease volume?
```

This is normal for piezo impulse spikes.

Optional cleanup:

```bash
sox /tmp/piezo.wav /tmp/piezo_nodc.wav gain -1 highpass 20
```

---

## 5) Generate Spectrogram (Visual Validation)

Create a spectrogram image:

```bash
sox /tmp/piezo_nodc.wav -n spectrogram -o /tmp/piezo_nodc.png
```

Use this to visually compare textures. Look for:

* Energy distribution differences
* Broadband vs narrowband patterns
* Temporal consistency

---

## 6) Batch Processing Multiple Textures

From a directory of WAV files:

```bash
cd /tmp/textures
for f in *.wav; do
  sox "$f" "${f%.wav}_nodc.wav" gain -1 highpass 20
  sox "${f%.wav}_nodc.wav" -n spectrogram -o "${f%.wav}_nodc.png"
done
```

This produces:

* `<texture>_nodc.wav`
* `<texture>_nodc.png`

---

## 7) Copy Files Off the Pi

### SCP (zsh wildcard-safe)

```bash
scp "pipipi@pipipi:/tmp/textures/*.png" .
```

### WSL2 → Windows

```bash
cp /tmp/textures/*.png /mnt/c/Users/<WINDOWS_USER>/Desktop/
cp /tmp/textures/*.wav /mnt/c/Users/<WINDOWS_USER>/Desktop/
```

---

## 8) Quick Per-File Comparison (Optional)

```bash
cd /tmp/textures
for f in *_nodc.wav; do
  echo "---- $f ----"
  sox "$f" -n stat 2>&1 | egrep "RMS.*amplitude|Maximum amplitude|Rough.*frequency"
done
```

Useful for spotting texture-dependent differences without plots.

---

## Why This Step Exists

These steps establish:

* Correct wiring
* Correct gain
* Correct coupling mechanics
* Texture-dependent signal variation

Only after this passes should Python streaming, DSP, or ML be attempted.

---

End of document.

