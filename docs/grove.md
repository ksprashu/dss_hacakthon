# Grove Base HAT & Sensors — Bring-Up Guide

## Hardware

* Grove Base HAT for Raspberry Pi
* Grove 16×2 LCD (I²C)
* Grove DHT Temp/Humidity Sensor (Digital)
* Grove Button + LED (Digital)

---

## I²C Baseline Check

With **no sensors connected**:

```bash
sudo i2cdetect -y 1
```

Expected:

```
0x08
```

`0x08` confirms the Grove Base HAT controller is present.

---

## LCD (16×2 Grove)

### Detection

```bash
sudo i2cdetect -y 1
```

Expected additional address:

```
0x3e
```

### Known Timing Gotcha

The LCD may drop the first character if written immediately after `clear()`.

**Correct pattern:**

```python
lcd.clear()
time.sleep(0.05)
lcd.setCursor(0, 0)
lcd.write("Hello Grove!   ")
```

This is a hardware timing quirk.

---

## Temp / Humidity Sensor (DHT)

* Port: **D5**
* GPIO: **BCM GPIO5**
* Protocol: **Digital (not I²C)**

Important:

* Will **not** appear in `i2cdetect`
* This is expected behavior

---

## Button + LED

* Digital GPIO
* Not visible in I²C scans

CLI testing:

```bash
gpioinfo
gpioget gpiochip0 <pin>
gpioset gpiochip0 <pin>=1
```

---

## Hot-Plug Notes

* I²C sensors: generally safe to hot-plug (no active transactions)
* Digital GPIO: power down before plugging (recommended)

