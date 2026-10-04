# Shrimp Counting App — Raspberry Pi 5 (8 GB) Setup

A Flask web app that counts shrimp with **Ultralytics YOLO** (`models/best.pt`)
on a Raspberry Pi 5. YOLO runs only on a short burst of still frames captured
**after** each automation set finishes (pump off, gate closed) — never on the
live preview. The burst is tracked with ByteTrack and the shrimp are counted by
the **peak number of unique track IDs** inside the ROI.

This guide takes a freshly flashed Raspberry Pi 5 (8 GB) to a running app.

---

## 1. What you need

| Item | Notes |
| --- | --- |
| Raspberry Pi 5, **8 GB** | 4 GB works but 8 GB is recommended for torch + Chromium |
| microSD card, 32 GB+ (A2) or USB SSD/NVMe | A faster card shortens the first install |
| Raspberry Pi Camera Module | Camera Module 3 / v2 / HQ, or a USB webcam |
| Raspberry Pi OS, **64-bit**, with Desktop | Bookworm or newer |
| ESP32 board + USB cable | *Optional* — only for feeder / pump / gate control |
| Internet connection | Required for the first install (downloads `torch`, ~1 GB) |

> The app does **not** use the IMX500 AI Camera NPU. Any libcamera-compatible
> camera works; all inference runs on the Pi's CPU.

---

## 2. Flash the OS and update

1. Use **Raspberry Pi Imager** to write **Raspberry Pi OS (64-bit)** with the
   **Desktop** environment to your card.
2. In Imager's ⚙ settings, pre-configure the hostname, your username, Wi-Fi and
   enable SSH, then write the card and boot.
3. Update the system:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

---

## 3. Enable the camera

On Raspberry Pi OS Bookworm the camera is usually auto-detected. To be sure:

```bash
sudo raspi-config      # Interface Options -> Camera -> Enable
```

or edit `/boot/firmware/config.txt` and confirm this line is present:

```ini
camera_auto_detect=1
```

Reboot, then test the camera:

```bash
rpicam-hello -t 5000            # Bookworm and newer
# libcamera-hello -t 5000       # older images
```

You should get a 5-second preview. If it fails, fix the camera before
continuing — the app's camera loop will not start otherwise.

> **AI Camera (IMX500) owners:** add `dtoverlay=imx500` to
> `/boot/firmware/config.txt`. The app ignores the sensor's NPU and runs YOLO on
> the CPU, but the camera still works as a normal libcamera source.

---

## 4. Copy the project onto the Pi

Put the project in your home directory as `~/hiponpt`.

**Option A — git:**

```bash
cd ~
git clone <your-repo-url> hiponpt
```

**Option B — copy from your PC** (run this on the PC; adjust user/ip):

```bash
scp -r hiponpt pi@raspberrypi.local:/home/pi/
```

Confirm the model files arrived:

```bash
cd ~/hiponpt
ls -l models/best.pt models/shrimp_bytetrack.yaml
```

`models/best.pt` is required. Without it the UI still runs, but nothing is
counted.

---

## 5. Automated setup (recommended)

`install.sh` does everything in one go:

```bash
cd ~/hiponpt
chmod +x install.sh run_kiosk.sh create_rpk.sh
./install.sh
```

It will:

1. copy `assets/landing.png` to `assets/images/landing.png` (splash logo),
2. `apt install` the camera stack (`python3-picamera2`, `python3-libcamera`,
   `python3-pil`, `python3-numpy`, `python3-opencv`, `chromium-browser`, …),
3. create the virtual environment `~/hiponpt/.venv` **with
   `--system-site-packages`**,
4. run `pip install -r requirements.txt` (downloads `ultralytics` + `torch` —
   this is the slow step, allow 10–30 minutes on a Pi 5),
5. create a Desktop shortcut named **“Shrimp Farm Control”**.

> The script still runs the legacy IMX500 `.rpk` packaging step. If it prints
> *“create_rpk.sh did not finish”*, you can safely ignore it — the app no longer
> uses the `.rpk`.

---

## 6. Manual setup (if you skip `install.sh`)

### 6.1 System packages

```bash
sudo apt install -y \
  python3 python3-pip python3-venv python3-dev \
  python3-pil python3-numpy python3-opencv \
  python3-picamera2 python3-libcamera libcamera-apps \
  libcap-dev chromium-browser
```

### 6.2 Create the virtual environment

```bash
cd ~/hiponpt
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
```

`--system-site-packages` lets the venv reuse the apt-installed `picamera2`,
`numpy`, `opencv` and `PIL`, which keeps the numpy ABI consistent. **Do not**
`pip install numpy` / `opencv` / `picamera2` inside the venv on the Pi.

### 6.3 Python dependencies

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

`requirements.txt` includes `ultralytics` (which pulls in `torch`) and
`pyserial`. If the install runs out of memory, retry without the pip cache:

```bash
python3 -m pip install --no-cache-dir -r requirements.txt
```

### 6.4 Verify the install

```bash
python3 -c "import cv2, numpy, PIL, serial, flask; print('deps ok')"
python3 -c "from ultralytics import YOLO; YOLO('models/best.pt'); print('model ok')"
```

---

## 7. Run the app

```bash
cd ~/hiponpt
source .venv/bin/activate
python3 main.py
```

You can also double-click the **Shrimp Farm Control** Desktop shortcut, or run
`./run_kiosk.sh`.

Expected startup output:

```text
[Startup] Initializing camera pipeline (Picamera2 preview + YOLO burst count).
[Camera] Ultralytics YOLO model loaded: models/best.pt
[Kiosk] Launched kiosk browser -> http://127.0.0.1:5000/splash
```

Then open the UI:

| Where | URL |
| --- | --- |
| The Pi's own screen | the app auto-opens Chromium in kiosk mode |
| A browser on the Pi | `http://localhost:5000` |
| Any device on the network | `http://<pi-ip>:5000` (find it with `hostname -I`) |

The splash page (`/splash`) shows for a few seconds, then redirects to the
Camera page (`/`).

---

## 8. Using the Camera page

The top bar has **Camera · Controls · Gallery**, plus **Calibration** and **ROI**.

- **Live Feed** — opt-in MJPEG preview. Off by default so the browser never
  streams; the app forces it off during a count cycle and won't let you turn it
  back on until the set finishes.
- **Start Loop** — opens the target modal and runs the automation until
  `Counted` reaches `To Count`. While running, the status line shows progress
  such as `(2/30 shrimp - Detected 5)`.
- **Cancel** — stops the loop immediately.
- **Flush** — runs the flush sequence.
- **ROI** — draws the counting box. Only shrimp whose **centre** falls inside the
  box are counted. Click **ROI**, drag the box, then **Save as default** (stored
  in `camera_defaults.json`).

> The ROI editor's preview comes from `/api/snapshot`, which grabs a fresh frame
> even when Live Feed is off, so you can set the ROI without streaming.

---

## 9. Kiosk mode and auto-start

`main.py` launches a full-screen browser by itself — the first of
`chromium-browser`, `chromium`, `google-chrome`, `google-chrome-stable` found on
`PATH` — pointed at `http://127.0.0.1:5000/splash`. If none is installed it
prints the URL and keeps serving, so you can open the page from another device.

To launch the app automatically at login, create
`~/.config/autostart/shrimp.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Shrimp Farm Control
Exec=%h/hiponpt/run_kiosk.sh
Path=%h/hiponpt
X-GNOME-Autostart-enabled=true
```

Then make sure the launcher is executable:

```bash
chmod +x ~/hiponpt/run_kiosk.sh
```

---

## 10. ESP32 / serial (optional)

The app auto-connects to the first USB serial device it finds
(`/dev/ttyUSB0`, `/dev/ttyACM0`, …) at **115200 baud**. You can also pick a port
manually on the **Controls** page and press **Connect**; status, calibration and
logs are on that page too.

Flash `esp.ino` to the ESP32 with the Arduino IDE for the hardware side
(gates / pump / feeder).

---

## 11. Troubleshooting

### `bad interpreter` or `$'\r': command not found` when running a `*.sh`

The scripts picked up Windows (CRLF) line endings. Fix:

```bash
sudo apt install -y dos2unix
cd ~/hiponpt
dos2unix *.sh
```

### Model not loading

```bash
ls -l models/best.pt
```

If it is missing, copy your trained weights there. The log prints
`[Camera] Ultralytics YOLO unavailable` when the model cannot be loaded.

### Camera not opening

```bash
rpicam-hello -t 5000     # CSI camera
ls /dev/video*           # USB webcam
```

Make sure the camera is enabled (section 3) and the ribbon cable is reseated.

### `pip install` fails or the Pi runs out of memory

```bash
python3 -m pip install --no-cache-dir -r requirements.txt
```

Close Chromium while installing, and confirm you are running the **64-bit** OS.

### Port 5000 already in use

```bash
sudo ss -ltnp | grep 5000     # or: sudo lsof -i :5000
```

Stop the other process, or change `WEB_PORT` near the top of `main.py`.

### Kiosk browser does not open

```bash
which chromium-browser chromium google-chrome
sudo apt install -y chromium-browser      # or: chromium
```

### Serial device not connecting

```bash
ls /dev/ttyUSB* /dev/ttyACM*
sudo usermod -aG dialout "$USER"          # then log out and back in
```

---

## 12. Useful notes

- Counting runs on stills captured after the gate closes, so the Live Feed does
  not need to stay on during a set.
- The burst reports the **peak unique ByteTrack ID count**, which is steadier
  than a single-frame detection count.
- Each set saves 3 annotated stills (start / peak / end) to the Gallery, using
  guaranteed-unique filenames so stills are never overwritten.
- The detector (single class `ShrimpFry`) lives in `models/best.pt`; the tracker
  settings live in `models/shrimp_bytetrack.yaml`.
- `run.sh` is a **legacy** launcher with a hard-coded path from an older
  deployment; use `run_kiosk.sh` (or `python3 main.py`) instead.


