#!/usr/bin/env python3
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)
"""
ESP32 Control - ALL-IN-ONE (Flask web app, shown in a kiosk-mode browser)
---------------------------------------------------------------------------------
Runs as a single process on the Raspberry Pi:
    - Opens ONE serial connection to the ESP32 (no port-sharing conflicts).
    - Serves the entire touchscreen interface as a web app (Flask), with:
        * Camera page (/): optional Live Feed preview for camera position,
          plus automation that counts shrimp from stills after the gate closes.
        * Controls page (/controls): ONE single scrollable page with the
          Actuator, both Servos (as OPEN/CLOSE toggles), the Relays, and
          Custom Automation, all centered on the page.
        * Actuator UP/DOWN are press-and-hold: moves continuously while held,
          stops the instant you release. No duration setting.
        * A persistent nav bar (Camera / Controls / Gallery) stays visible
          at the top of every page, so switching pages is a single tap.
        * A splash page (/splash) shows assets/images/landing.png on a white
          background for a few seconds on startup, then redirects to "/".
    - On launch, opens a kiosk-mode browser (chromium-browser or similar,
      whichever is found on the system) pointed at the splash page, giving
      a full-screen touchscreen app with no browser chrome.
    - The exact same Flask app is reachable from any other device on the
      network too, at the same time, using the same serial connection.
    - Auto-connects as soon as a USB serial device appears (prefers
      /dev/ttyUSB0), and reconnects if the device is unplugged and plugged
      back in. Manual Connect/Disconnect still works as an override.

    ESP32 <--serial--> THIS APP -- Flask web app, shown in:
                                     - a kiosk-mode browser on the Pi's own LCD
                                     - any other browser on the network

CAMERA CAPTURE:
    Frames are captured with Picamera2 (PiCamCapture below), NOT
    cv2.VideoCapture. On a Raspberry Pi 5, CSI/ribbon cameras only
    deliver frames through libcamera/Picamera2; OpenCV's VideoCapture
    "opens" but returns no frames. Detection uses Ultralytics YOLO on
    models/best.pt after each automation set, not on the live preview.

SERVO POSITIONS (must match the ESP32 sketch):
    Servo 1: CLOSE = 160 degrees (default / startup position), OPEN = 100 degrees
    Servo 2: CLOSE = 160 degrees (default / startup position), OPEN = 0 degrees

    Both servos are treated as simple OPEN/CLOSE gates rather than free-angle
    sliders: the UI shows a single toggle switch per servo. Flipping it to
    OPEN sends the servo's open angle; flipping it back sends its close angle.
    Both start CLOSED by default.

ACTUATOR (press-and-hold, no duration):
    Pressing UP sends "AU:99" (move up); releasing sends "AS" (stop) right away.
    Pressing DOWN sends "AD:99"; releasing sends "AS". A STOP button is also
    available as a manual fallback. The ESP32 sketch's own AU/AD/AS commands
    are unchanged - this app just starts a long move and cuts it short on release.

SERIAL COMMANDS SENT (must match the ESP32 sketch):
    AU:99      (start moving up, stopped early by AS on release)
    AD:99      (start moving down, stopped early by AS on release)
    AS         (stop)
    S1:<deg>   (100 = open, 160 = close)
    S2:<deg>   (0 = open, 160 = close)
    R1ON/R1OFF   R2ON/R2OFF   R3ON/R3OFF

REQUIREMENTS (install once on the Pi):
    sudo apt install python3-pil python3-picamera2 python3-libcamera \
        python3-opencv python3-numpy chromium-browser
    pip install flask pyserial ultralytics
    (Use the apt versions of picamera2, numpy and opencv. Do NOT pip-install
    picamera2, numpy>=2 or opencv-python into the venv - they break the
    system picamera2/libcamera stack on Raspberry Pi OS Bookworm. The venv
    must be created with --system-site-packages.)

RUN:
    python3 main.py

ACCESS:
    LCD touchscreen: a kiosk-mode browser opens automatically, full-screen,
    starting at the splash page and then the Camera page.
    Web (same Pi):          http://localhost:5000
    Web (other devices):    http://<raspberry-pi-ip>:5000   (find IP with: hostname -I)
    Serial: auto-connects when a USB serial device is detected (prefers
    /dev/ttyUSB0); use the port dropdown + Connect button to pick another port.
"""

import threading
import time
import os
import subprocess
import shutil
import tempfile
import traceback
import glob
import io
import json
import math
import re
import queue
from flask import Flask, request, jsonify, Response, send_from_directory
import serial
import serial.tools.list_ports

from camera import create_camera_blueprint
from controls import create_controls_blueprint
from gallery import create_gallery_blueprint
from splash import create_splash_blueprint
import numpy as np
from PIL import Image, ImageDraw

try:
    import cv2
    CV2_AVAILABLE = True
except Exception:
    print("[Camera] Could not import cv2 - full traceback below:")
    traceback.print_exc()
    CV2_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except Exception:
    print("[Camera] Ultralytics YOLO unavailable - detection will be disabled.")
    print("[Camera] Reason (full traceback below):")
    traceback.print_exc()
    YOLO = None
    YOLO_AVAILABLE = False

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except Exception:
    print("[Camera] Could not import picamera2 - full traceback below:")
    traceback.print_exc()
    PICAMERA2_AVAILABLE = False


class PiCamCapture:
    """
    Drop-in replacement for cv2.VideoCapture using Picamera2.

    On a Raspberry Pi 5, CSI cameras only deliver frames through
    libcamera/Picamera2 - cv2.VideoCapture(0) opens but never returns
    real frames. This class exposes the same small API the preview and
    still-capture paths use (isOpened / read / release / set / get).

    "RGB888" in Picamera2 is BGR byte order in memory, so frames come
    out ready for OpenCV and Ultralytics YOLO.
    """
    def __init__(self, size=(640, 480), buffer_count=3):
        if not PICAMERA2_AVAILABLE:
            raise RuntimeError("picamera2 is not available")
        self.picam2 = Picamera2()
        self.picam2.configure(self.picam2.create_video_configuration(
            main={"size": size, "format": "RGB888"},
            buffer_count=buffer_count))
        self.picam2.start()
        self._open = True
        print(f"[Camera] Picamera2 capture started at {size}, {buffer_count} buffers")

    def isOpened(self):
        return self._open

    def read(self):
        if not self._open:
            return False, None
        try:
            return True, self.picam2.capture_array()
        except Exception as exc:
            print(f"[Camera] Picamera2 capture failed: {exc}")
            return False, None

    def release(self):
        if self._open:
            try:
                self.picam2.stop()
                self.picam2.close()
            except Exception:
                pass
            self._open = False

    def set(self, *args):
        return False

    def get(self, *args):
        return 0


# ---------------------------------------------------------------------------
# Camera configuration
# ---------------------------------------------------------------------------
CAMERA_RESOLUTION = (640, 640)
SNAPSHOT_DIR = os.path.expanduser("~/esp32_snapshots")
CAMERA_FPS_INTERVAL_MS = 50             # ~20 fps refresh of the live feed

# ---------------------------------------------------------------------------
# Model selection (Ultralytics YOLO .pt)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
YOLO_WEIGHTS_PATH = os.path.join(_PROJECT_ROOT, "models", "best.pt")
YOLO_TRACKER_PATH = os.path.join(_PROJECT_ROOT, "models", "shrimp_bytetrack.yaml")
YOLO_LABELS_PATH = os.path.join(_PROJECT_ROOT, "models", "labels.txt")

# The model was trained on images made by capture.py, which saves them with
# red and blue swapped (it treats Picamera2's BGR "RGB888" array as RGB).
# So the model must be shown red/blue-swapped frames. Only the model input is
# swapped; the live view, ROI drawing and gallery stills keep normal colors.
# Set this to False if you retrain on correctly colored images.
MODEL_EXPECTS_SWAPPED_RB = True

DETECTION_THRESHOLD = 0.437
DETECTION_IOU = 0.80
DETECTION_MAX_DETECTIONS = 100
BURST_FRAME_COUNT = 8
BURST_INTERVAL_S = 0.25
BURST_GALLERY_COUNT = 3
MISSING_ID_IOU = 0.50

CAMERA_BUFFER_COUNT = 3     # Picamera2 frame buffers (each ~0.9 MB at 640x480)
STREAM_JPEG_QUALITY = 70    # JPEG quality for the live MJPEG stream

CAMERA_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "camera_defaults.json"
)

# Region of interest (ROI): only detections whose CENTER is inside this box
# are counted and drawn on gallery stills. Stored as fractions of the frame
# (0.0 = left/top edge, 1.0 = right/bottom edge). Editable from the "ROI"
# button in the navbar; "Save as default" writes it to camera_defaults.json.
DEFAULT_ROI = {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
ROI_MIN_SIZE = 0.05                    # ROI can't be smaller than 5% per side
ROI_COLOR = (255, 200, 0)              # RGB amber outline

DETECTION_BOX_COLOR = (0, 255, 0)        # green
DETECTION_CENTROID_COLOR = (255, 0, 0)   # red
DETECTION_LABEL_COLOR = (255, 255, 255)  # white
DETECTED_COUNT_TEXT_COLOR = (0, 255, 255)  # cyan - unique IDs in this frame


AUTOMATION_DEFAULT_STATE = [
    {"device": "servo1", "action": "close"},
    {"device": "servo2", "action": "close"},
    {"device": "relay1", "action": "off"},
    {"device": "relay2", "action": "off"},
]

# ---------------------------------------------------------------------------
# Configuration - keep these in sync with the ESP32 sketch
# ---------------------------------------------------------------------------
BAUD_RATE = 115200
MAX_LOG_LINES = 300
WEB_PORT = 5000

# Serial write timeout (seconds). Without this, pyserial's write() can block
# indefinitely if the ESP32 stops draining its input (e.g. it's stuck inside
# a blocking delay() on its end) - and since every write is serialized behind
# one lock, a single stuck write freezes ALL controls on both the LCD and the
# web page until the device catches up. A timeout turns that into a fast,
# recoverable error instead of a silent multi-second (or longer) stall.
SERIAL_WRITE_TIMEOUT = 0.5

# Preferred USB serial port for auto-connect. If it isn't present, the
# watcher will use the first USB serial device it finds (ttyUSB/ttyACM,
# or usbserial/usbmodem on macOS). Manual Connect/Disconnect still works.
AUTO_CONNECT_PORT = "/dev/ttyUSB0"
SERIAL_AUTO_CONNECT_INTERVAL = 1.0
_USB_SERIAL_HINTS = ("ttyusb", "ttyacm", "usbserial", "usbmodem", "cu.usb")

# Servo 1: OPEN = 100 degrees, CLOSE = 160 degrees. Starts CLOSED.
SERVO1_OPEN_DEG = 100
SERVO1_CLOSE_DEG = 180

# Servo 2: OPEN = 0 degrees, CLOSE = 160 degrees. Starts CLOSED.
SERVO2_OPEN_DEG = 0
SERVO2_CLOSE_DEG = 140

# Splash screen shown on startup, before the main interface loads. Path is
# relative to this file's own directory, so it works regardless of the
# current working directory the app is launched from. Served by Flask at
# /assets/images/landing.png (see the static_folder= setting on Flask(...)
# below), and shown full-screen in the kiosk browser before it redirects
# to "/".
SPLASH_IMAGE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "images", "landing.png"
)
SPLASH_DURATION_MS = 2500
SPLASH_BG_COLOR = "white"

# Kiosk mode: launches whichever of these is found first, in fullscreen
# kiosk mode, pointed at the splash page on startup.
KIOSK_BROWSER_CANDIDATES = [
    "chromium-browser",
    "chromium",
    "google-chrome",
    "google-chrome-stable",
]


# ---------------------------------------------------------------------------
# Shared HTML shell for the web UI: page style, the shared nav bar (with the
# active page highlighted), and the top-bar JS common to every page.
# camera.py / controls.py / gallery.py each get render_page passed into
# their create_*_blueprint() factory rather than importing it directly, so
# they have no dependency on main.py (avoids a circular import, and avoids
# main.py being accidentally imported a second time under a different name).
# ---------------------------------------------------------------------------
PAGE_STYLE = """
<style>
  body{
    font-family: 'Lato', sans-serif;
    background-color: #ffffff;
  }
  .content-wrapper{
    background-color: #ffffff;
    position: relative;
  }
  .content-wrapper::before{
    content: "";
    position: absolute;
    inset: 0;
    background-image: url('/assets/images/landing.png');
    background-repeat: no-repeat;
    background-position: center;
    background-size: contain;
    opacity: 0.08;
    pointer-events: none;
    z-index: 0;
  }
  .content-wrapper > .content{
    position: relative;
    z-index: 1;
  }
  .wrapper{
    background-color: #ffffff;
  }

  /* Camera viewfinder overlay - drawn on top of the live video image itself,
     so it stays legible regardless of the page's light/dark theme. */
  .camera-frame{ position:relative; border-radius:6px; overflow:hidden; background:#fff; margin-bottom:1rem; }
  .camera-frame .camera-stage{ position:relative; display:inline-block; max-width:100%; }
  .camera-frame img{ display:block; width:100%; height:auto; }
  .camera-frame .live-badge{ position:absolute; top:12px; left:12px; display:flex; align-items:center; gap:6px;
    background:rgba(0,0,0,0.55); color:#fff; padding:4px 10px; border-radius:20px; font-size:11px; font-weight:700; z-index:6; }
  .live-dot{ width:8px; height:8px; border-radius:50%; background:#dc3545; }
  /* The old black "Live feed off" placeholder box is removed entirely. */
  .camera-frame .feed-off{ display:none !important; }
  .camera-frame.feed-on .feed-off{ display:none !important; }

  /* Process status (current automation step, countdown, shrimp progress),
     centered in the middle of the camera area while the live feed is off. */
  #processCenter{
    position:absolute; inset:0; display:none; flex-direction:column;
    align-items:center; justify-content:center; text-align:center;
    padding:16px; z-index:4; pointer-events:none; }
  #processCenter.show{ display:flex; }
  #processCenter .process-step{ font-size:2rem; font-weight:900; color:#212529; line-height:1.2; }
  #processCenter .process-time{ font-size:3.2rem; font-weight:900; color:#007bff; line-height:1.1; margin-top:6px; }
  #processCenter .process-progress{ font-size:1.4rem; font-weight:700; color:#495057; margin-top:6px; }

  .gallery-item{ cursor:pointer; }
  .gallery-item img{ width:100%; height:120px; object-fit:cover; border-radius:4px; }
  .gallery-item .caption{ font-size:11px; color:#6c757d; margin-top:2px; }

  .lightbox{ position:fixed; inset:0; background:rgba(0,0,0,0.9); display:flex; align-items:center;
    justify-content:center; z-index:1050; }
  .lightbox.hidden{ display:none; }
  .lightbox img{ max-width:92%; max-height:82%; border-radius:6px; }
  .lightbox .lightbox-close{ position:absolute; top:16px; right:24px; font-size:32px; color:#fff; cursor:pointer; }
  .lightbox .lightbox-caption{ position:absolute; bottom:24px; left:0; right:0; text-align:center; color:#ddd; font-size:12px; }

  #captureToast{ position:fixed; top:70px; left:50%; transform:translateX(-50%); z-index:1060;
    opacity:0; transition:opacity 0.3s; pointer-events:none; }
  #captureToast.show{ opacity:1; }

  .status-dot{ width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:5px; background:#dc3545; }

  .feeder-section{
    gap:6px; flex-wrap:wrap; padding-left:12px; border-left:1px solid #dee2e6;
  }
  .feeder-section .feeder-label{ font-weight:700; font-size:13px; white-space:nowrap; }
  .feeder-section input{ width:88px; height:31px; }
  .feeder-section #feederLiveStatus{ font-size:12px; max-width:280px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

  /* Bootstrap's .modal CSS is loaded, but its JS (which needs jQuery) isn't -
     visibility here is toggled manually via a plain "show" class instead of
     Bootstrap's data-toggle/jQuery plugin. */
  #shrimpTargetModal{ display:none; position:fixed; inset:0; z-index:1060;
    background:rgba(0,0,0,0.5); align-items:center; justify-content:center; }
  #shrimpTargetModal.show{ display:flex; }
  #shrimpTargetModal .modal-dialog{ margin:0; }
  #powerModal{ display:none; position:fixed; inset:0; z-index:1080;
    background:rgba(0,0,0,0.5); align-items:center; justify-content:center; }
  #calibrationModal{ display:none; position:fixed; inset:0; z-index:1080;
    background:rgba(0,0,0,0.5); align-items:center; justify-content:center; }
  #calibrationModal.show{ display:flex; }
  #calibrationModal .modal-dialog{ margin:0; max-width:420px; width:94%; }
  #calibrationModal .modal-body{ max-height:70vh; overflow-y:auto; }
  #feedDispenseModal{ display:none !important; }
  #feedDispenseModal .modal-dialog{ margin:0; }
  #feederModal{ display:none; position:fixed; inset:0; z-index:1070;
    background:rgba(0,0,0,0.5); align-items:center; justify-content:center; }
  #feederModal.show{ display:flex !important; }
  .close, .close-modal-btn{ min-width:44px; min-height:44px; font-size:28px; line-height:1; z-index:2; }
  #feederCountInput{
    font-size:2.2rem; font-weight:800; text-align:center; height:56px;
    letter-spacing:1px; padding:4px;
  }
  #feederCountInput:disabled{ background:#e9ecef; color:#111; }
  .feeder-stat{ font-size:1.15rem; margin:0 0 0.5rem; line-height:1.3; font-weight:600; }
  .feeder-stat strong{ font-size:1.5rem; font-weight:800; }
  .camera-split{ display:flex !important; flex-direction:row !important; flex:1 1 auto; min-height:0; gap:8px; align-items:stretch; }
  .camera-split-left{ flex:1 1 auto; min-width:0; display:flex; flex-direction:column; }
  .camera-split-right{
    flex:0 0 280px !important; width:280px !important; max-width:280px !important;
    display:flex !important; flex-direction:column; justify-content:flex-start;
    padding:8px 10px; background:#f8f9fa; border:1px solid #dee2e6; border-radius:6px;
    overflow-x:hidden; overflow-y:auto;
  }
  .feed-side-title{ font-weight:800; font-size:1.4rem; margin-bottom:8px; }
  .feed-side-label{ font-weight:800; font-size:1.15rem; margin-bottom:4px; }
  .feeder-action-btn{ font-size:1.25rem; font-weight:800; min-height:48px; }

  /* "Fit to screen, no scrolling" mode - used by the Camera page so the
     live feed always fills the 7" LCD without a scrollbar, regardless of
     the exact navbar/header heights (pure flexbox, no hardcoded pixels). */
  body.no-scroll-page, body.no-scroll-page .wrapper{ height:100vh; overflow:hidden; }
  body.no-scroll-page .wrapper{ display:flex; flex-direction:column; }
  body.no-scroll-page .main-header{ flex:0 0 auto; }
  body.no-scroll-page .content-wrapper{ flex:1 1 auto; min-height:0; overflow:hidden;
    display:flex; flex-direction:column; }
  body.no-scroll-page .content{ flex:1 1 auto; min-height:0; display:flex; flex-direction:column;
    padding-top:.5rem !important; padding-bottom:.5rem !important; }
  body.no-scroll-page .content .container-fluid{ flex:1 1 auto; min-height:0;
    display:flex; flex-direction:column; }
  body.no-scroll-page .card{ flex:1 1 auto; min-height:0; margin-bottom:0 !important; }
  body.no-scroll-page .card-body{ flex:1 1 auto; min-height:0; display:flex;
    flex-direction:column; padding:.5rem !important; }
  body.no-scroll-page .card-body.camera-split{ flex-direction:row !important; }
  body.no-scroll-page .camera-frame{ flex:1 1 auto; margin-bottom:0;
    display:flex; align-items:center; justify-content:center; overflow:hidden;
    max-height:none; min-height:0; }
  body.no-scroll-page .camera-frame .camera-stage{ max-height:100%; }
  body.no-scroll-page .camera-frame img{ width:auto; height:auto;
    max-width:100%; max-height:calc(100vh - 150px); object-fit:contain; }
  .status-dot.on{ background:#28a745; }

  #roiModal{ display:none; position:fixed; inset:0; z-index:1080;
    background:rgba(0,0,0,0.5); align-items:center; justify-content:center; }
  #roiModal.show{ display:flex; }
  #roiModal .modal-dialog{ margin:0; max-width:520px; width:96%; }
  #roiModal .modal-body{ max-height:78vh; overflow-y:auto; }
  .roi-preview{ position:relative; width:100%; background:#111; border-radius:4px; overflow:hidden; margin-bottom:10px; min-height:60px; }
  .roi-preview img{ display:block; width:100%; height:auto; }
  .roi-box{ position:absolute; border:3px solid #ffc800; box-shadow:0 0 0 9999px rgba(0,0,0,0.45); pointer-events:none; }
  .roi-slider-label{ display:flex; justify-content:space-between; font-weight:700; margin-top:4px; }

  #osk{
    display:none; position:fixed; left:0; right:0; bottom:0; z-index:2000;
    background:#2b3035; padding:10px 12px 14px; box-shadow:0 -6px 18px rgba(0,0,0,0.35);
  }
  #osk.show{ display:block; }
  #osk .osk-keys{ display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; max-width:420px; margin:0 auto; }
  #osk .osk-wide{ grid-column: span 2; }
  #osk button{
    min-height:48px; font-size:22px; font-weight:700; border:0; border-radius:8px;
    background:#495057; color:#fff;
  }
  #osk button.osk-action{ background:#6c757d; }
  #osk button.osk-ok{ background:#28a745; }
</style>
"""

NAV_TABS = [
    ("camera", "/", "&#128248; Camera"),
    ("controls", "/controls", "&#9881; Controls"),
    ("gallery", "/gallery", "&#128247; Gallery"),
]


def render_nav_links(active):
    links = []
    for key, href, label in NAV_TABS:
        cls = "nav-link active" if key == active else "nav-link"
        links.append(
            f'<li class="nav-item"><a class="{cls}" href="{href}">{label}</a></li>'
        )
    return "\n        ".join(links)


COMMON_SCRIPT = """
async function refreshPorts(){
  const res = await fetch('/api/ports');
  const data = await res.json();
  const select = document.getElementById('portSelect');
  const current = select.value;
  select.innerHTML = '';
  data.ports.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p; opt.textContent = p;
    select.appendChild(opt);
  });
  const status = await (await fetch('/api/status')).json();
  if (status.connected && data.ports.includes(status.port)){
    select.value = status.port;
  } else if (data.ports.includes(current)){
    select.value = current;
  }
}

async function refreshStatus(){
  const res = await fetch('/api/status');
  const data = await res.json();
  const btn = document.getElementById('connectBtn');
  const dot = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  if (data.connected){
    btn.textContent = 'Disconnect';
    btn.classList.remove('btn-success'); btn.classList.add('btn-danger');
    dot.classList.add('on'); text.textContent = 'Connected: ' + data.port;
  } else {
    btn.textContent = 'Connect';
    btn.classList.remove('btn-danger'); btn.classList.add('btn-success');
    dot.classList.remove('on'); text.textContent = 'Disconnected';
  }
}

document.getElementById('refreshBtn').addEventListener('click', refreshPorts);

document.getElementById('connectBtn').addEventListener('click', async () => {
  const status = await (await fetch('/api/status')).json();
  if (status.connected){
    await fetch('/api/disconnect', {method:'POST'});
  } else {
    const port = document.getElementById('portSelect').value;
    if (!port){ alert('No serial port selected.'); return; }
    const res = await fetch('/api/connect', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({port})
    });
    const data = await res.json();
    if (!data.ok) alert('Connect failed: ' + data.error);
  }
  refreshStatus();
});

document.getElementById('shutdownBtn').addEventListener('click', () => openPowerModal());

const powerModal = document.getElementById('powerModal');
function openPowerModal(){
  if (!powerModal) return;
  powerModal.classList.add('show');
  powerModal.style.display = 'flex';
}
function closePowerModal(){
  if (!powerModal) return;
  powerModal.classList.remove('show');
  powerModal.style.display = 'none';
}
async function requestPowerAction(url, failLabel){
  closePowerModal();
  if (typeof closeFeederManualModal === 'function') closeFeederManualModal();
  try{
    const res = await fetch(url, {method:'POST'});
    const data = await res.json();
    if (!data.ok) alert(failLabel + ': ' + (data.error || 'failed'));
  } catch(e){}
}
if (document.getElementById('powerModalClose')){
  document.getElementById('powerModalClose').addEventListener('click', closePowerModal);
}
if (document.getElementById('powerModalCancel')){
  document.getElementById('powerModalCancel').addEventListener('click', closePowerModal);
}
if (powerModal){
  powerModal.addEventListener('click', (e) => { if (e.target === powerModal) closePowerModal(); });
}
if (document.getElementById('powerExitAppBtn')){
  document.getElementById('powerExitAppBtn').addEventListener('click', () => requestPowerAction('/api/exit-app', 'Exit app failed'));
}
if (document.getElementById('powerShutdownPiBtn')){
  document.getElementById('powerShutdownPiBtn').addEventListener('click', () => requestPowerAction('/api/shutdown', 'Shutdown failed'));
}

let calibShrimpWeight = 0.00333;
let calibFeederMultiplier = 0.15;
const calibrationModal = document.getElementById('calibrationModal');
function openCalibrationModal(){
  if (!calibrationModal) return;
  calibrationModal.classList.add('show');
  calibrationModal.style.display = 'flex';
}
function closeCalibrationModal(){
  if (!calibrationModal) return;
  calibrationModal.classList.remove('show');
  calibrationModal.style.display = 'none';
  if (typeof hideOsk === 'function') hideOsk();
}
function applyCalibrationToUi(data){
  if (!data) return;
  if (data.shrimp_weight_g != null) calibShrimpWeight = Number(data.shrimp_weight_g);
  if (data.feeder_multiplier != null) calibFeederMultiplier = Number(data.feeder_multiplier);
  const setVal = (id, v) => {
    const el = document.getElementById(id);
    if (el && v != null) el.value = String(v);
  };
  setVal('calibConfidence', data.confidence);
  setVal('calibFeederMultiplier', data.feeder_multiplier);
  setVal('calibShrimpWeight', data.shrimp_weight_g);
  setVal('calibFeederPulse', data.feeder_pulse_seconds);
  setVal('calibFlushPump', data.flush_pump_seconds);
  if (typeof updateFeederCountLabels === 'function') updateFeederCountLabels();
}
async function loadCalibration(){
  try{
    const res = await fetch('/api/calibration');
    applyCalibrationToUi(await res.json());
  } catch(e){}
}
if (document.getElementById('calibrationBtn')){
  document.getElementById('calibrationBtn').addEventListener('click', async () => {
    await loadCalibration();
    openCalibrationModal();
  });
}
if (document.getElementById('calibrationModalClose')){
  document.getElementById('calibrationModalClose').addEventListener('click', closeCalibrationModal);
}
if (document.getElementById('calibrationModalCancel')){
  document.getElementById('calibrationModalCancel').addEventListener('click', closeCalibrationModal);
}
if (calibrationModal){
  calibrationModal.addEventListener('click', (e) => { if (e.target === calibrationModal) closeCalibrationModal(); });
}
if (document.getElementById('calibrationModalSave')){
  document.getElementById('calibrationModalSave').addEventListener('click', async () => {
    const num = (id) => parseFloat(document.getElementById(id) && document.getElementById(id).value);
    try{
      const res = await fetch('/api/calibration', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          confidence: num('calibConfidence'),
          feeder_multiplier: num('calibFeederMultiplier'),
          shrimp_weight_g: num('calibShrimpWeight'),
          feeder_pulse_seconds: num('calibFeederPulse'),
          flush_pump_seconds: num('calibFlushPump')
        })
      });
      const data = await res.json();
      if (!data.ok){
        alert(data.error || 'Could not save calibration');
        return;
      }
      applyCalibrationToUi(data.settings);
      closeCalibrationModal();
    } catch(e){
      alert('Could not save calibration');
    }
  });
}

// ---- Automation Start/Stop Loop (fixed preset sequence) - lives in the
// shared top navbar next to the Gallery link, so it's visible and stays in
// sync on every page. Starting always asks for a target shrimp count via
// the modal below; the loop stops itself once the live counting-line
// detector reaches that count. ----
const DEVICE_LABELS = { relay1:'Pump', relay2:'Feeder', servo1:'Gate 1', servo2:'Gate 2' };

let automationRunning = false;

const automationToggleBtn = document.getElementById('automationToggleBtn');
const automationStatusEl = document.getElementById('automationStatus');
const shrimpTargetModal = document.getElementById('shrimpTargetModal');
const shrimpTargetInput = document.getElementById('shrimpTargetInput');

function openShrimpTargetModal(){
  shrimpTargetInput.value = '';
  shrimpTargetModal.classList.add('show');
  setTimeout(() => shrimpTargetInput.focus(), 50);
}

function closeShrimpTargetModal(){
  shrimpTargetModal.classList.remove('show');
}

document.getElementById('shrimpModalClose').addEventListener('click', closeShrimpTargetModal);
document.getElementById('shrimpModalCancel').addEventListener('click', closeShrimpTargetModal);
shrimpTargetModal.addEventListener('click', (e) => { if (e.target === shrimpTargetModal) closeShrimpTargetModal(); });

document.getElementById('shrimpModalSubmit').addEventListener('click', async () => {
  const value = parseInt(shrimpTargetInput.value, 10);
  if (!value || value <= 0){
    alert('Enter a valid total number of shrimp (greater than 0).');
    return;
  }
  closeShrimpTargetModal();
  try{
    const res = await fetch('/api/automation/start', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({target_count: value})
    });
    const data = await res.json();
    if (!data.ok){ if (automationStatusEl) automationStatusEl.textContent = data.error || 'Could not start'; }
  } catch(e){ /* next poll will resync */ }
  pollAutomationStatus();
});

shrimpTargetInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('shrimpModalSubmit').click();
});

// Centered process panel inside the camera area (Camera page only).
function getProcessPanel(){
  const frame = document.querySelector('.camera-frame');
  if (!frame) return null;
  let el = document.getElementById('processCenter');
  if (!el || el.parentElement !== frame){
    if (el) el.remove();
    el = document.createElement('div');
    el.id = 'processCenter';
    frame.appendChild(el);
  }
  return el;
}

function renderProcessPanel(show, label, secondsLeft, countText){
  const panel = getProcessPanel();
  if (!panel) return;
  const feedOn = panel.parentElement.classList.contains('feed-on');
  if (!show || feedOn){
    panel.classList.remove('show');
    return;
  }
  let html = '<div class="process-step">' + label + '</div>';
  if (secondsLeft) html += '<div class="process-time">' + secondsLeft + 's</div>';
  if (countText) html += '<div class="process-progress">' + countText + '</div>';
  panel.innerHTML = html;
  panel.classList.add('show');
}

function renderAutomationStatus(data, currentCount){
  automationRunning = data.running;
  if (automationToggleBtn){
    automationToggleBtn.textContent = automationRunning ? '\\u23F9 Stop Loop' : '\\u25B6 Start Loop';
    automationToggleBtn.classList.toggle('btn-success', !automationRunning);
    automationToggleBtn.classList.toggle('btn-danger', automationRunning);
  }
  const step = (data.steps || [])[data.current_index];
  const running = !!(automationRunning && step);
  let label = '', secondsLeft = 0, countText = '';
  if (running){
    label = (DEVICE_LABELS[step.device] || step.device) + ' \\u2192 ' + step.action.toUpperCase();
    secondsLeft = data.seconds_left || 0;
    if (data.target_count != null && currentCount != null){
      countText = currentCount + ' / ' + data.target_count + ' shrimp';
    }
  }
  renderProcessPanel(running, label, secondsLeft, countText);
  if (!automationStatusEl) return;
  if (running){
    const tail = secondsLeft ? ' \\u2014 ' + secondsLeft + 's' : '';
    const progress = countText ? ' (' + currentCount + '/' + data.target_count + ' shrimp)' : '';
    automationStatusEl.innerHTML = '<strong>' + label + '</strong>' + tail + progress;
  } else {
    automationStatusEl.textContent = 'Idle';
  }
}

// Hide the camera <img> whenever it has nothing to show (feed off, or the
// stream hasn't loaded), so the browser's broken-image icon and the
// "Live camera feed" alt text never appear. It shows again by itself as soon
// as a real image/stream is loaded.
function hideBrokenCameraImages(){
  document.querySelectorAll('.camera-frame img').forEach((img) => {
    const broken = img.complete && img.naturalWidth === 0;
    img.style.visibility = broken ? 'hidden' : 'visible';
  });
}
hideBrokenCameraImages();
setInterval(hideBrokenCameraImages, 300);

async function pollAutomationStatus(){
  try{
    const [autoRes, countRes] = await Promise.all([
      fetch('/api/automation'),
      fetch('/api/shrimp_count'),
    ]);
    const autoData = await autoRes.json();
    const countData = await countRes.json();
    renderAutomationStatus(autoData, countData.count);
    if (typeof syncFeederAutoTarget === 'function') syncFeederAutoTarget(autoData);
    maybeOpenFeedReadyModal(autoData);
  } catch(e){ /* ignore transient network errors */ }
}

if (automationToggleBtn) automationToggleBtn.addEventListener('click', async () => {
  if (automationRunning){
    try{
      const res = await fetch('/api/automation/stop', {method:'POST'});
      const data = await res.json();
      if (!data.ok){ if (automationStatusEl) automationStatusEl.textContent = data.error || 'Could not stop'; }
    } catch(e){ /* next poll will resync */ }
    pollAutomationStatus();
  } else {
    openShrimpTargetModal();
  }
});

// ---- Feed dispense (popup appears once detection completes) ----
const feedModal = document.getElementById('feedDispenseModal');
const feedLiveStatus = document.getElementById('feedLiveStatus');
const feedToCountValue = document.getElementById('feedToCountValue');
const feedBiomassValue = document.getElementById('feedBiomassValue');
const feedDispenseValue = document.getElementById('feedDispenseValue');
const feedCurrentWeightValue = document.getElementById('feedCurrentWeightValue');
const feedStartBtn = document.getElementById('feedStartBtn');
const feedStopBtn = document.getElementById('feedStopBtn');
let feedPollInterval = null;
let feedCompletedCount = null;
let feedModalUserClosed = false;

function openFeedModal(){
  return;
}

function closeFeedModal(){
  if (!feedModal) return;
  feedModalUserClosed = true;
  feedModal.classList.remove('show');
  feedModal.style.display = 'none';
  if (feedPollInterval){ clearInterval(feedPollInterval); feedPollInterval = null; }
  if (typeof hideOsk === 'function') hideOsk();
}

function maybeOpenFeedReadyModal(autoData){
  if (!autoData) return;
  const pending = autoData.feed_popup_pending || autoData.just_completed;
  if (!pending){
    feedModalUserClosed = false;
    return;
  }
  if (feedModalUserClosed) return;
  if (autoData.completed_count == null) return;
  openFeedReadyModal(
    autoData.completed_count,
    autoData.completed_feed_grams,
    autoData.completed_target
  );
}

function setFeederCountLocked(locked){
  const input = document.getElementById('feederCountInput');
  if (!input) return;
  input.disabled = !!locked;
  if (locked && typeof hideOsk === 'function') hideOsk();
}

function setFeederCountLabel(text){
  const label = document.getElementById('feederCountLabel');
  if (label) label.textContent = text;
}

function showFeederAutoTarget(count){
  const wrap = document.getElementById('feederTargetCountWrap');
  const val = document.getElementById('feederTargetCountValue');
  if (!wrap || !val) return;
  if (count == null || count === ''){
    wrap.style.display = 'none';
    return;
  }
  val.textContent = String(count);
  wrap.style.display = '';
}

function hideFeederAutoTarget(){
  showFeederAutoTarget(null);
}

function syncFeederAutoTarget(autoData){
  if (!autoData) return;
  if (autoData.running && autoData.target_count != null){
    showFeederAutoTarget(autoData.target_count);
    return;
  }
  const label = document.getElementById('feederCountLabel');
  const detectedMode = label && label.textContent === 'Detected Count';
  if (detectedMode && autoData.completed_target != null){
    showFeederAutoTarget(autoData.completed_target);
    return;
  }
  if (!detectedMode && !autoData.running) hideFeederAutoTarget();
}

function openFeedReadyModal(count, targetGrams, toCount){
  const detected = parseInt(count, 10);
  if (!detected || detected < 1) return;
  feedCompletedCount = detected;
  setFeederCountLabel('Detected Count');
  const input = document.getElementById('feederCountInput');
  if (input){
    input.value = String(detected);
    setFeederCountLocked(true);
  }
  const userTarget = (toCount != null && toCount !== '') ? parseInt(toCount, 10) : null;
  if (userTarget && userTarget > 0) showFeederAutoTarget(userTarget);
  if (typeof updateFeederCountLabels === 'function') updateFeederCountLabels();
  const weightEl = document.getElementById('feederCurrentWeightValue');
  if (weightEl) weightEl.textContent = '0.00 g';
  if (feedToCountValue) feedToCountValue.textContent = String(detected);
  const grams = (typeof feederTargetGrams === 'function')
    ? feederTargetGrams(detected)
    : Number(targetGrams);
  if (feedBiomassValue && typeof feederBiomassGrams === 'function'){
    feedBiomassValue.textContent = feederBiomassGrams(detected).toFixed(2) + ' g';
  }
  if (feedDispenseValue){
    feedDispenseValue.textContent = (Number.isFinite(grams) ? grams : 0).toFixed(2) + ' g';
  }
  if (feedCurrentWeightValue) feedCurrentWeightValue.textContent = '0.00 g';
  if (feedLiveStatus) feedLiveStatus.textContent = '';
  if (feedStartBtn) feedStartBtn.disabled = false;
  if (feedStopBtn) feedStopBtn.disabled = false;
  const live = document.getElementById('feederLiveStatus');
  if (live) live.textContent = 'Detected Count ' + detected + ' - press Start';
  fetch('/api/automation/feed-popup-ack', {method:'POST'}).catch(() => {});
}

function renderFeedRunning(status){
  if (!feedLiveStatus) return;
  const weight = (status.current_weight != null) ? Number(status.current_weight) : 0;
  if (feedCurrentWeightValue) feedCurrentWeightValue.textContent = weight.toFixed(2) + ' g';
  const phase = status.phase || 'idle';
  if (phase === 'waiting_zero'){
    feedLiveStatus.textContent = status.message || '';
  } else if (phase === 'dispensing'){
    feedLiveStatus.textContent = 'Dispensing...';
  } else if (phase === 'weighing'){
    feedLiveStatus.textContent = '';
  } else if (phase === 'done'){
    feedLiveStatus.textContent = 'Done';
  } else if (phase === 'error'){
    feedLiveStatus.textContent = status.message || 'Feeder error';
  } else if (status.message){
    feedLiveStatus.textContent = status.message;
  }
}

async function startFeedDispense(){
  const count = feedCompletedCount;
  if (!count){
    if (feedLiveStatus) feedLiveStatus.textContent = 'No shrimp count available.';
    return;
  }
  if (feedStartBtn) feedStartBtn.disabled = true;
  if (feedLiveStatus) feedLiveStatus.textContent = 'Starting...';
  try{
    const res = await fetch('/api/feed/start', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({shrimp_count: count})
    });
    const data = await res.json();
    if (!data.ok){
      if (feedLiveStatus) feedLiveStatus.textContent = data.error || 'Could not start';
      if (feedStartBtn) feedStartBtn.disabled = false;
      return;
    }
    renderFeedRunning(data.status);
    if (feedPollInterval) clearInterval(feedPollInterval);
    feedPollInterval = setInterval(pollFeedStatus, 400);
  } catch(e){
    if (feedLiveStatus) feedLiveStatus.textContent = 'Could not start dispensing.';
    if (feedStartBtn) feedStartBtn.disabled = false;
  }
}

async function stopFeedDispense(){
  if (feedPollInterval){
    clearInterval(feedPollInterval);
    feedPollInterval = null;
  }
  try{ await fetch('/api/feed/stop', {method:'POST'}); } catch(e){}
  if (feedStartBtn) feedStartBtn.disabled = false;
  if (feedLiveStatus) feedLiveStatus.textContent = 'Stopped';
}

async function pollFeedStatus(){
  try{
    const res = await fetch('/api/feed/status');
    const status = await res.json();
    renderFeedRunning(status);
    if (status.phase === 'done'){
      if (feedPollInterval){
        clearInterval(feedPollInterval);
        feedPollInterval = null;
      }
      if (feedStartBtn) feedStartBtn.disabled = false;
    } else if (status.phase === 'error'){
      if (feedPollInterval){
        clearInterval(feedPollInterval);
        feedPollInterval = null;
      }
      if (feedStartBtn) feedStartBtn.disabled = false;
    }
  } catch(e){ /* ignore transient network errors */ }
}

if (feedStartBtn) feedStartBtn.addEventListener('click', startFeedDispense);
if (feedStopBtn) feedStopBtn.addEventListener('click', stopFeedDispense);

document.getElementById('feedModalClose').addEventListener('click', (e) => {
  e.preventDefault();
  e.stopPropagation();
  closeFeedModal();
  stopFeedDispense();
});

pollAutomationStatus();
setInterval(pollAutomationStatus, 1000);

const feederCountInput = document.getElementById('feederCountInput');
const feederStartBtn = document.getElementById('feederStartBtn');
const feederStopBtn = document.getElementById('feederStopBtn');
const feederManualBtn = document.getElementById('feederManualBtn');
const feederModal = document.getElementById('feederModal');
const feederModalClose = document.getElementById('feederModalClose');
const feederManualOnBtn = document.getElementById('feederManualOnBtn');
const feederManualOffBtn = document.getElementById('feederManualOffBtn');
const feederResetBtn = document.getElementById('feederResetBtn');
const feederLiveStatus = document.getElementById('feederLiveStatus');
let feederPollInterval = null;
let feederResetTimer = null;

function feederTargetGrams(count){
  return Math.round(count * calibShrimpWeight * calibFeederMultiplier * 1000) / 1000;
}
function feederBiomassGrams(count){
  return Math.round(count * calibShrimpWeight * 1000) / 1000;
}

function updateFeederCountLabels(){
  const count = parseInt(feederCountInput && feederCountInput.value, 10) || 0;
  const biomassEl = document.getElementById('feederBiomassValue');
  const dispenseEl = document.getElementById('feederDispenseValue');
  if (biomassEl) biomassEl.textContent = feederBiomassGrams(count).toFixed(2) + ' g';
  if (dispenseEl) dispenseEl.textContent = feederTargetGrams(count).toFixed(2) + ' g';
}
if (feederCountInput){
  feederCountInput.addEventListener('input', updateFeederCountLabels);
}
loadCalibration();

function setFeederManualEnabled(enabled){
  if (feederManualOnBtn) feederManualOnBtn.disabled = !enabled;
  if (feederManualOffBtn) feederManualOffBtn.disabled = !enabled;
}

function resetFeederUi(){
  if (feederCountInput) feederCountInput.value = '';
  setFeederCountLabel('To Count');
  hideFeederAutoTarget();
  setFeederCountLocked(false);
  if (feederStartBtn){
    feederStartBtn.disabled = false;
    feederStartBtn.textContent = 'Start';
  }
  setFeederManualEnabled(true);
  if (feederLiveStatus) feederLiveStatus.textContent = '';
  const weightEl = document.getElementById('feederCurrentWeightValue');
  if (weightEl) weightEl.textContent = '0.00 g';
  updateFeederCountLabels();
}

async function sendFeederRelay(command){
  const res = await fetch('/api/send', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({command})
  });
  const data = await res.json();
  if (!data.ok){
    if (feederLiveStatus) feederLiveStatus.textContent = data.error || ('Failed ' + command);
    return false;
  }
  if (feederLiveStatus) feederLiveStatus.textContent = command === 'R2ON' ? 'Feeder ON' : 'Feeder OFF';
  return true;
}

function renderFeederStatus(status){
  if (!feederLiveStatus) return;
  const weight = (status.current_weight != null) ? Number(status.current_weight) : 0;
  const weightEl = document.getElementById('feederCurrentWeightValue');
  if (weightEl) weightEl.textContent = weight.toFixed(2) + ' g';
  const target = (status.target_grams != null) ? Number(status.target_grams) : 0;
  const phase = status.phase || 'idle';
  if (phase === 'waiting_zero'){
    feederLiveStatus.textContent = status.message || 'Stabilizing default weight...';
  } else if (phase === 'dispensing'){
    feederLiveStatus.textContent = 'R2 ON 5s (pulse ' + (status.cycle || 0) + ')  now ' + weight.toFixed(1) + ' g / ' + target.toFixed(2) + ' g';
  } else if (phase === 'weighing'){
    feederLiveStatus.textContent = 'Weight: ' + weight.toFixed(1) + ' g / target ' + target.toFixed(2) + ' g';
  } else if (phase === 'done'){
    feederLiveStatus.textContent = 'Done: ' + weight.toFixed(1) + ' g (target ' + target.toFixed(2) + ' g)';
  } else if (phase === 'error'){
    feederLiveStatus.textContent = status.message || 'Feeder error';
  } else if (status.message){
    feederLiveStatus.textContent = status.message;
  }
}

async function defaultFeederAfterDone(){
  try{ await fetch('/api/feed/stop', {method:'POST'}); } catch(e){}
  resetFeederUi();
}

async function pollNavbarFeeder(){
  try{
    const res = await fetch('/api/feed/status');
    const status = await res.json();
    renderFeederStatus(status);
    if (status.phase === 'done' || status.phase === 'error'){
      if (feederPollInterval){
        clearInterval(feederPollInterval);
        feederPollInterval = null;
      }
      if (feederStartBtn) feederStartBtn.disabled = true;
      setFeederCountLocked(false);
      setFeederManualEnabled(false);
      if (!feederResetTimer){
        feederResetTimer = setTimeout(() => {
          feederResetTimer = null;
          defaultFeederAfterDone();
        }, 4000);
      }
    } else if (!status.running && status.phase === 'idle'){
      if (feederPollInterval){
        clearInterval(feederPollInterval);
        feederPollInterval = null;
      }
      if (feederStartBtn){
        feederStartBtn.disabled = false;
        feederStartBtn.textContent = 'Start';
      }
      setFeederManualEnabled(true);
    }
  } catch(e){}
}

if (feederStartBtn){
  feederStartBtn.addEventListener('click', async () => {
    const count = parseInt(feederCountInput && feederCountInput.value, 10);
    if (!count || count < 1){
      feederLiveStatus.textContent = 'Enter shrimp count';
      return;
    }
    const target = feederTargetGrams(count);
    feederLiveStatus.textContent = 'Starting - target ' + target.toFixed(2) + ' g';
    feederStartBtn.disabled = true;
    setFeederCountLocked(true);
    setFeederManualEnabled(false);
    try{
      const res = await fetch('/api/feed/start', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({shrimp_count: count})
      });
      const data = await res.json();
      if (!data.ok){
        feederLiveStatus.textContent = data.error || 'Could not start feeder';
        feederStartBtn.disabled = false;
        setFeederCountLocked(false);
        setFeederManualEnabled(true);
        return;
      }
      if (feederPollInterval) clearInterval(feederPollInterval);
      feederPollInterval = setInterval(pollNavbarFeeder, 400);
      pollNavbarFeeder();
    } catch(e){
      feederLiveStatus.textContent = 'Could not start feeder';
      feederStartBtn.disabled = false;
      setFeederCountLocked(false);
      setFeederManualEnabled(true);
    }
  });
}

if (feederStopBtn){
  feederStopBtn.addEventListener('click', async () => {
    try{ await fetch('/api/feed/stop', {method:'POST'}); } catch(e){}
    if (feederPollInterval){
      clearInterval(feederPollInterval);
      feederPollInterval = null;
    }
    if (feederStartBtn){
      feederStartBtn.disabled = false;
      feederStartBtn.textContent = 'Start';
    }
    setFeederCountLabel('To Count');
    hideFeederAutoTarget();
    setFeederCountLocked(false);
    setFeederManualEnabled(true);
    if (feederLiveStatus) feederLiveStatus.textContent = 'Stopped';
  });
}

function openFeederManualModal(){
  if (!feederModal) return;
  feederModal.classList.add('show');
  feederModal.style.display = 'flex';
}
function closeFeederManualModal(){
  if (!feederModal) return;
  feederModal.classList.remove('show');
  feederModal.style.display = 'none';
}

if (feederManualBtn){
  feederManualBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    openFeederManualModal();
  });
}
if (feederModalClose){
  feederModalClose.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    closeFeederManualModal();
  });
}
if (feederModal){
  feederModal.addEventListener('click', (e) => {
    if (e.target === feederModal) closeFeederManualModal();
  });
}

if (feederManualOnBtn){
  feederManualOnBtn.addEventListener('click', () => sendFeederRelay('R2ON'));
}
if (feederManualOffBtn){
  feederManualOffBtn.addEventListener('click', () => sendFeederRelay('R2OFF'));
}
if (feederResetBtn){
  feederResetBtn.addEventListener('click', async () => {
    if (feederPollInterval){
      clearInterval(feederPollInterval);
      feederPollInterval = null;
    }
    if (feederResetTimer){
      clearTimeout(feederResetTimer);
      feederResetTimer = null;
    }
    try{ await fetch('/api/feed/stop', {method:'POST'}); } catch(e){}
    try{ await sendFeederRelay('R2OFF'); } catch(e){}
    resetFeederUi();
    if (feederLiveStatus) feederLiveStatus.textContent = 'Reset';
  });
}

refreshPorts();
refreshStatus();
setInterval(() => { refreshPorts(); refreshStatus(); }, 2000);

// ---- ROI (region of interest) editor ----
const roiModal = document.getElementById('roiModal');
const roiSliders = {
  left: document.getElementById('roiLeft'),
  right: document.getElementById('roiRight'),
  top: document.getElementById('roiTop'),
  bottom: document.getElementById('roiBottom'),
};
const ROI_MIN_PCT = 5;

function roiClamp(changed){
  // Sliders are insets (% trimmed from each side). Keep >= 5% of the view.
  const L = roiSliders.left, R = roiSliders.right, T = roiSliders.top, B = roiSliders.bottom;
  const maxSum = 100 - ROI_MIN_PCT;
  if (+L.value + +R.value > maxSum){
    if (changed === 'left') L.value = maxSum - +R.value; else R.value = maxSum - +L.value;
  }
  if (+T.value + +B.value > maxSum){
    if (changed === 'top') T.value = maxSum - +B.value; else B.value = maxSum - +T.value;
  }
}

function roiRender(){
  const l = +roiSliders.left.value, r = +roiSliders.right.value;
  const t = +roiSliders.top.value, b = +roiSliders.bottom.value;
  document.getElementById('roiLeftVal').textContent = l + '%';
  document.getElementById('roiRightVal').textContent = r + '%';
  document.getElementById('roiTopVal').textContent = t + '%';
  document.getElementById('roiBottomVal').textContent = b + '%';
  const box = document.getElementById('roiBox');
  box.style.left = l + '%';
  box.style.top = t + '%';
  box.style.width = (100 - l - r) + '%';
  box.style.height = (100 - t - b) + '%';
}

function roiApply(data){
  if (!data || !data.roi) return;
  roiSliders.left.value = Math.round(data.roi.left * 100);
  roiSliders.top.value = Math.round(data.roi.top * 100);
  roiSliders.right.value = Math.round((1 - data.roi.right) * 100);
  roiSliders.bottom.value = Math.round((1 - data.roi.bottom) * 100);
  roiRender();
}

let roiPreviewTimer = null;

function refreshRoiPreview(){
  const el = document.getElementById('roiPreviewImg');
  if (!el) return;
  el.src = '/api/snapshot?t=' + Date.now();
}

async function openRoiModal(){
  if (!roiModal) return;
  try{ roiApply(await (await fetch('/api/roi')).json()); } catch(e){}
  refreshRoiPreview();
  roiPreviewTimer = setInterval(refreshRoiPreview, 1000);
  roiModal.classList.add('show');
  roiModal.style.display = 'flex';
}

function closeRoiModal(){
  if (!roiModal) return;
  roiModal.classList.remove('show');
  roiModal.style.display = 'none';
  if (roiPreviewTimer){ clearInterval(roiPreviewTimer); roiPreviewTimer = null; }
  document.getElementById('roiPreviewImg').src = '';   // stop the refresh loop
  if (typeof hideOsk === 'function') hideOsk();
}

if (roiModal){
  Object.keys(roiSliders).forEach((side) => {
    roiSliders[side].addEventListener('input', () => { roiClamp(side); roiRender(); });
  });
  document.getElementById('roiBtn').addEventListener('click', openRoiModal);
  document.getElementById('roiModalClose').addEventListener('click', closeRoiModal);
  document.getElementById('roiModalCancel').addEventListener('click', closeRoiModal);
  roiModal.addEventListener('click', (e) => { if (e.target === roiModal) closeRoiModal(); });
  document.getElementById('roiResetBtn').addEventListener('click', async () => {
    try{ roiApply(await (await fetch('/api/roi/reset', {method:'POST'})).json()); } catch(e){}
  });
  document.getElementById('roiSaveBtn').addEventListener('click', async () => {
    const body = {
      left: +roiSliders.left.value / 100,
      top: +roiSliders.top.value / 100,
      right: 1 - (+roiSliders.right.value / 100),
      bottom: 1 - (+roiSliders.bottom.value / 100)
    };
    try{
      const res = await fetch('/api/roi', {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
      });
      const data = await res.json();
      if (!data.ok){ alert(data.error || 'Could not save ROI'); return; }
      closeRoiModal();
    } catch(e){ alert('Could not save ROI'); }
  });
}

const osk = document.getElementById('osk');
let oskTarget = null;

function showOsk(input){
  if (!input || input.disabled) return;
  oskTarget = input;
  osk.classList.add('show');
}
function hideOsk(){
  osk.classList.remove('show');
  oskTarget = null;
}
function oskType(ch){
  if (!oskTarget) return;
  if (ch === 'back'){
    oskTarget.value = String(oskTarget.value || '').slice(0, -1);
  } else if (ch === 'clear'){
    oskTarget.value = '';
  } else if (ch === 'ok'){
    oskTarget.dispatchEvent(new Event('input', {bubbles:true}));
    oskTarget.dispatchEvent(new Event('change', {bubbles:true}));
    hideOsk();
    return;
  } else {
    oskTarget.value = String(oskTarget.value || '') + ch;
  }
  oskTarget.dispatchEvent(new Event('input', {bubbles:true}));
}

osk.addEventListener('mousedown', (e) => e.preventDefault());
osk.addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-osk]');
  if (!btn) return;
  oskType(btn.getAttribute('data-osk'));
});

function bindOskInputs(){
  document.querySelectorAll('input[type="number"], input[type="text"], input:not([type])').forEach((input) => {
    if (input.dataset.oskBound) return;
    input.dataset.oskBound = '1';
    input.setAttribute('inputmode', 'none');
    input.setAttribute('autocomplete', 'off');
    input.addEventListener('focus', () => showOsk(input));
    input.addEventListener('pointerdown', () => showOsk(input));
    input.addEventListener('click', (e) => {
      e.stopPropagation();
      showOsk(input);
    });
  });
}
bindOskInputs();
const oskObserver = new MutationObserver(bindOskInputs);
oskObserver.observe(document.body, {childList:true, subtree:true});
document.addEventListener('click', (e) => {
  if (!osk.classList.contains('show')) return;
  if (e.target.closest('#osk')) return;
  if (e.target.closest('input')) return;
  if (e.target.closest('#cameraFeederBtn')) return;
  hideOsk();
});
"""


def render_page(active, body, page_script, extra_body="", full_height=False):
    body_class = "hold-transition layout-top-nav" + (" no-scroll-page" if full_height else "")
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Cache-Control" content="no-store">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Shrimp Farm Control</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lato:wght@400;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/admin-lte@3.2.0/dist/css/adminlte.min.css">
{PAGE_STYLE}
</head>
<body class="{body_class}">
<div class="wrapper">

  <nav class="main-header navbar navbar-expand navbar-white navbar-light border-bottom">
    <div class="container-fluid">
      <ul class="navbar-nav">
        {render_nav_links(active)}
        <li class="nav-item d-flex align-items-center pl-3">
          <button id="calibrationBtn" class="btn btn-outline-primary btn-sm mr-2">Calibration</button>
          <button id="roiBtn" class="btn btn-outline-warning btn-sm mr-2">ROI</button>
          <span id="automationStatus" class="text-muted small d-none"></span>
        </li>
      </ul>

      <ul class="navbar-nav ml-auto align-items-center flex-nowrap">
        <li class="nav-item px-1">
          <select id="portSelect" class="custom-select custom-select-sm" style="width:auto;"></select>
        </li>
        <li class="nav-item px-1">
          <button id="refreshBtn" class="btn btn-sm btn-outline-secondary" title="Refresh ports">&#8635;</button>
        </li>
        <li class="nav-item px-1">
          <button id="connectBtn" class="btn btn-sm btn-success">Connect</button>
        </li>
        <li class="nav-item px-2 d-flex align-items-center">
          <span id="statusDot" class="status-dot"></span>
          <small id="statusText" class="text-muted">Disconnected</small>
        </li>
        <li class="nav-item px-1">
          <button id="shutdownBtn" class="btn btn-sm btn-outline-danger" title="Exit app or shut down the Raspberry Pi">&#9211; Power</button>
        </li>
      </ul>
    </div>
  </nav>

  <div class="content-wrapper">
    <div class="content pt-3 pb-4">
      <div class="container-fluid">
{body}
      </div>
    </div>
  </div>

</div>

<div class="modal" id="calibrationModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Calibration</h5>
        <button type="button" class="close" id="calibrationModalClose" aria-label="Close"><span aria-hidden="true">&times;</span></button>
      </div>
      <div class="modal-body">
        <label for="calibConfidence">Confidence level</label>
        <input id="calibConfidence" type="text" inputmode="none" autocomplete="off" class="form-control mb-2" placeholder="0.55">
        <label for="calibFeederMultiplier">Feeder multiplier</label>
        <input id="calibFeederMultiplier" type="text" inputmode="none" autocomplete="off" class="form-control mb-2" placeholder="15">
        <label for="calibShrimpWeight">Weight of shrimp (g)</label>
        <input id="calibShrimpWeight" type="text" inputmode="none" autocomplete="off" class="form-control mb-2" placeholder="0.00333">
        <label for="calibFeederPulse">R2 ON / feeder duration each turn (s)</label>
        <input id="calibFeederPulse" type="text" inputmode="none" autocomplete="off" class="form-control mb-2" placeholder="5">
        <label for="calibFlushPump">Flush pump duration (s)</label>
        <input id="calibFlushPump" type="text" inputmode="none" autocomplete="off" class="form-control mb-2" placeholder="10">
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" id="calibrationModalCancel">Cancel</button>
        <button type="button" class="btn btn-primary" id="calibrationModalSave">Save</button>
      </div>
    </div>
  </div>
</div>

<div class="modal" id="roiModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">ROI</h5>
        <button type="button" class="close" id="roiModalClose" aria-label="Close"><span aria-hidden="true">&times;</span></button>
      </div>
      <div class="modal-body">
        <div class="roi-preview">
          <img id="roiPreviewImg" alt="Camera preview">
          <div class="roi-box" id="roiBox"></div>
        </div>
        <div class="roi-slider-label"><span>Left edge</span><span id="roiLeftVal">0%</span></div>
        <input type="range" id="roiLeft" min="0" max="95" step="1" value="0" class="custom-range">
        <div class="roi-slider-label"><span>Right edge</span><span id="roiRightVal">0%</span></div>
        <input type="range" id="roiRight" min="0" max="95" step="1" value="0" class="custom-range">
        <div class="roi-slider-label"><span>Top edge</span><span id="roiTopVal">0%</span></div>
        <input type="range" id="roiTop" min="0" max="95" step="1" value="0" class="custom-range">
        <div class="roi-slider-label"><span>Bottom edge</span><span id="roiBottomVal">0%</span></div>
        <input type="range" id="roiBottom" min="0" max="95" step="1" value="0" class="custom-range">
        <small class="text-muted d-block mb-2">Each slider trims that side of the camera view. Only shrimp whose center is inside the box are counted in a burst.</small>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline-secondary mr-auto" id="roiResetBtn">Reset</button>
        <button type="button" class="btn btn-secondary" id="roiModalCancel">Cancel</button>
        <button type="button" class="btn btn-warning" id="roiSaveBtn">Save as default</button>
      </div>
    </div>
  </div>
</div>

<div class="modal" id="powerModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Power</h5>
        <button type="button" class="close" id="powerModalClose" aria-label="Close"><span aria-hidden="true">&times;</span></button>
      </div>
      <div class="modal-body">
        <p class="mb-3">Choose how to stop this session.</p>
        <button type="button" id="powerExitAppBtn" class="btn btn-secondary btn-block feeder-action-btn mb-2">Exit desktop app</button>
        <button type="button" id="powerShutdownPiBtn" class="btn btn-danger btn-block feeder-action-btn mb-2">Shutdown Raspberry Pi</button>
        <button type="button" id="powerModalCancel" class="btn btn-outline-secondary btn-block feeder-action-btn">Cancel</button>
      </div>
    </div>
  </div>
</div>

<div class="modal" id="shrimpTargetModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Start Automation</h5>
        <button type="button" class="close" id="shrimpModalClose" aria-label="Close"><span aria-hidden="true">&times;</span></button>
      </div>
      <div class="modal-body">
        <label for="shrimpTargetInput">Total number of shrimp to process</label>
        <input type="number" min="1" step="1" class="form-control" id="shrimpTargetInput" placeholder="e.g. 500">
        <small class="text-muted"></small>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" id="shrimpModalCancel">Cancel</button>
        <button type="button" class="btn btn-success" id="shrimpModalSubmit">&#9654; Start</button>
      </div>
    </div>
  </div>
</div>

<div class="modal" id="feedDispenseModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Feeder</h5>
        <button type="button" class="close" id="feedModalClose" aria-label="Close"><span aria-hidden="true">&times;</span></button>
      </div>
      <div class="modal-body" id="feedDispenseBody">
        <p class="feeder-stat" style="font-size:1.8rem; font-weight:800; margin-bottom:0.8rem;">
          To Count: <span id="feedToCountValue">0</span>
        </p>
        <p class="feeder-stat mb-1">Total Biomass: <strong id="feedBiomassValue">0.00 g</strong></p>
        <p class="feeder-stat mb-1">Recommended Feed: <strong id="feedDispenseValue">0.00 g</strong></p>
        <p class="feeder-stat mb-3">Total current weight: <strong id="feedCurrentWeightValue">0.00 g</strong></p>
        <p id="feedLiveStatus" class="text-center" style="min-height:24px;"></p>
        <div class="d-flex justify-content-center flex-wrap" style="gap:10px;">
          <button type="button" id="feedStartBtn" class="btn btn-warning btn-lg">Start</button>
          <button type="button" id="feedStopBtn" class="btn btn-outline-danger btn-lg">Stop</button>
        </div>
      </div>
    </div>
  </div>
</div>

{extra_body}

<div id="osk" aria-hidden="true">
  <div class="osk-keys">
    <button type="button" data-osk="1">1</button>
    <button type="button" data-osk="2">2</button>
    <button type="button" data-osk="3">3</button>
    <button type="button" data-osk="4">4</button>
    <button type="button" data-osk="5">5</button>
    <button type="button" data-osk="6">6</button>
    <button type="button" data-osk="7">7</button>
    <button type="button" data-osk="8">8</button>
    <button type="button" data-osk="9">9</button>
    <button type="button" data-osk=".">.</button>
    <button type="button" data-osk="0">0</button>
    <button type="button" class="osk-action" data-osk="back">&#9003;</button>
    <button type="button" class="osk-action osk-wide" data-osk="clear">Clear</button>
    <button type="button" class="osk-ok" data-osk="ok">OK</button>
  </div>
</div>

<script>
{COMMON_SCRIPT}
{page_script}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Serial communication handler (shared by every Flask request/thread)
# ---------------------------------------------------------------------------
class SerialManager:
    """
    All outgoing commands go through a single background writer thread and a
    queue, rather than being written directly on the caller's thread. This is
    the key fix for controls intermittently freezing/lagging on BOTH the LCD
    and the web page at once: previously, send() called self.ser.write(...)
    directly while holding write_lock, and pyserial's write() can block if
    the ESP32 isn't draining its input fast enough (e.g. it's inside a
    blocking delay() while moving a servo/actuator). Since every command -
    from either interface - funneled through that same lock, one stuck write
    stalled everything else behind it, with no way to tell the two symptoms
    apart ("not working" vs "delay") because they were the same underlying
    freeze at different durations.

    Now: send() just puts the command on a queue and returns immediately, so
    a button press on the LCD or a click on the web page is never blocked by
    a slow/stuck write. A single writer thread drains the queue in order
    (preserving command ordering, which matters for e.g. AU:99 followed by
    AS), and the actual serial.Serial is opened with a write timeout so even
    the writer thread can't hang forever on one bad write - it logs the
    timeout and moves on to the next queued command instead.
    """
    def __init__(self):
        self.ser = None
        self.port_name = None
        self.read_thread = None
        self.write_thread = None
        self.stop_flag = threading.Event()
        self.log = []          # list of {"id", "dir": in/out/sys, "text", "ts"}
        self.log_lock = threading.Lock()
        self.write_queue = queue.Queue()
        self.next_id = 1
        self._lock = threading.RLock()
        self._skip_ports = set()
        self._watcher_stop = threading.Event()
        self._watcher_thread = None

    def start_watcher(self):
        if self._watcher_thread is not None:
            return
        self._watcher_stop.clear()
        self._watcher_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watcher_thread.start()

    def list_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]

    def _is_auto_port(self, device):
        name = (device or "").lower()
        if device == AUTO_CONNECT_PORT:
            return True
        return any(hint in name for hint in _USB_SERIAL_HINTS)

    def _candidate_ports(self, ports=None):
        ports = ports if ports is not None else self.list_ports()
        candidates = [p for p in ports if self._is_auto_port(p)]
        candidates.sort(key=lambda p: (p != AUTO_CONNECT_PORT, p))
        return candidates

    def connect(self, port, manual=False):
        with self._lock:
            if manual:
                self._skip_ports.discard(port)
            self.disconnect()
            self.ser = serial.Serial(port, BAUD_RATE, timeout=1, write_timeout=SERIAL_WRITE_TIMEOUT)
            self.port_name = port
            time.sleep(2)  # allow ESP32 to reset after opening the serial port
            self.stop_flag.clear()
            # Drain any commands queued while disconnected so a stale command
            # doesn't fire the instant a new connection opens.
            while not self.write_queue.empty():
                try:
                    self.write_queue.get_nowait()
                except queue.Empty:
                    break
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            self.write_thread = threading.Thread(target=self._write_loop, daemon=True)
            self.write_thread.start()
            self._add_log("sys", f"Connected to {port} @ {BAUD_RATE} baud")

    def disconnect(self, manual=False):
        with self._lock:
            if manual and self.port_name:
                self._skip_ports.add(self.port_name)
            self.stop_flag.set()
            if self.read_thread is not None:
                self.read_thread.join(timeout=1)
                self.read_thread = None
            if self.write_thread is not None:
                # Wake the writer thread if it's blocked on an empty queue.
                self.write_queue.put(None)
                self.write_thread.join(timeout=1)
                self.write_thread = None
            if self.ser is not None and self.ser.is_open:
                self.ser.close()
            if self.port_name:
                self._add_log("sys", f"Disconnected from {self.port_name}")
            self.ser = None
            self.port_name = None

    def shutdown(self):
        self._watcher_stop.set()
        if self._watcher_thread is not None:
            self._watcher_thread.join(timeout=2)
            self._watcher_thread = None
        self.disconnect()

    def _watch_loop(self):
        while not self._watcher_stop.is_set():
            try:
                self._auto_connect_tick()
            except Exception as exc:
                print(f"[Serial] Auto-connect error: {exc}")
            self._watcher_stop.wait(SERIAL_AUTO_CONNECT_INTERVAL)

    def _auto_connect_tick(self):
        with self._lock:
            ports = self.list_ports()
            self._skip_ports = {p for p in self._skip_ports if p in ports}

            if self.is_connected():
                if self.port_name not in ports:
                    print(f"[Serial] Port {self.port_name} disappeared; disconnecting")
                    self.disconnect()
                return

            if self.ser is not None or self.port_name is not None:
                self.disconnect()

            for port in self._candidate_ports(ports):
                if port in self._skip_ports:
                    continue
                try:
                    print(f"[Serial] Auto-connecting to {port}...")
                    self.connect(port)
                    return
                except Exception as exc:
                    print(f"[Serial] Auto-connect to {port} failed: {exc}")
                    self._add_log("sys", f"Auto-connect to {port} failed: {exc}")

    def is_connected(self):
        return self.ser is not None and self.ser.is_open

    def send(self, command):
        """
        Enqueues `command` for the writer thread and returns immediately -
        never blocks on the actual serial write, so callers on any Flask
        request thread stay responsive even if the ESP32
        is momentarily slow to drain its input.
        """
        if not self.is_connected():
            raise RuntimeError("Not connected to any serial port.")
        self.write_queue.put(command.strip())

    def _write_loop(self):
        while not self.stop_flag.is_set():
            try:
                command = self.write_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if command is None:  # sentinel used to unblock on disconnect
                continue
            line = command + "\n"
            try:
                if self.ser is not None:
                    self.ser.write(line.encode("utf-8"))
                    self._add_log("out", command)
            except serial.SerialTimeoutException:
                self._add_log("sys", f"Write timed out (device busy?): {command}")
                print(f"[Serial] Write timed out sending '{command}' - device may be busy/unresponsive.")
            except (OSError, serial.SerialException) as exc:
                self._add_log("sys", f"Write failed: {exc}")
                print(f"[Serial] Write failed sending '{command}': {exc}")

    def _read_loop(self):
        while not self.stop_flag.is_set():
            try:
                if self.ser and self.ser.in_waiting:
                    raw = self.ser.readline().decode("utf-8", errors="replace").strip()
                    if raw:
                        self._add_log("in", raw)
                else:
                    time.sleep(0.05)
            except (OSError, serial.SerialException):
                self._add_log("sys", "Serial connection lost")
                try:
                    if self.ser is not None:
                        self.ser.close()
                except Exception:
                    pass
                break

    def _add_log(self, direction, text):
        with self.log_lock:
            entry = {"id": self.next_id, "dir": direction, "text": text, "ts": time.time()}
            self.next_id += 1
            self.log.append(entry)
            if len(self.log) > MAX_LOG_LINES:
                self.log = self.log[-MAX_LOG_LINES:]

    def get_log_since(self, since_id):
        with self.log_lock:
            return [e for e in self.log if e["id"] > since_id]

    def get_latest_log_id(self):
        with self.log_lock:
            return self.next_id - 1


serial_mgr = SerialManager()


# ---------------------------------------------------------------------------
# Automation manager - a single fixed, repeating preset sequence
# ---------------------------------------------------------------------------
DEVICE_LABELS = {
    "relay1": "Pump",
    "relay2": "Feeder",
    "servo1": "Gate 1",
    "servo2": "Gate 2",
}


def _device_command(device, action):
    """Translates a {device, action} step into the exact serial command string."""
    if device in ("relay1", "relay2", "relay3"):
        num = device[-1]
        return f"R{num}{'ON' if action == 'on' else 'OFF'}"
    if device == "servo1":
        deg = SERVO1_OPEN_DEG if action == "open" else SERVO1_CLOSE_DEG
        return f"S1:{deg}"
    if device == "servo2":
        deg = SERVO2_OPEN_DEG if action == "open" else SERVO2_CLOSE_DEG
        return f"S2:{deg}"
    return None


# The fixed automation sequence (not user-editable):
#   1. Servo 1 -> OPEN
#   2. Relay 1 (pump) -> ON, hold 7s
#   3. Relay 1 -> OFF
#   4. Servo 1 -> CLOSE, then capture + count stills
#   5. Servo 2 -> OPEN, hold 3s
#   6. Servo 2 -> CLOSE
#   7. add peak unique-ID count; loop until To Count
# Each step's "duration" is how long to hold AFTER sending that step's
# command before moving on to the next one.
PRESET_AUTOMATION_STEPS = [
    {"device": "servo1", "action": "open",  "duration": 0},
    {"device": "relay1", "action": "on",    "duration": 7},
    {"device": "relay1", "action": "off",   "duration": 0},
    {"device": "servo1", "action": "close", "duration": 0, "capture": True},
    {"device": "servo2", "action": "open",  "duration": 3},
    {"device": "servo2", "action": "close", "duration": 0},
]

# Factory default for how long Relay 2 (Feeder) stays ON each dispense pulse.
# Editable on the Controls page and persisted as the system default.
DEFAULT_FEEDER_SECONDS = 5.0
AUTOMATION_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "automation_defaults.json"
)

# Feed dispense formula: grams of feed = shrimp count * 0.00333 * 0.15
FEED_GRAMS_PER_SHRIMP = 0.00333
FEED_MULTIPLIER = 0.15
FEED_PULSE_SECONDS = 5.0
FEED_TARE_SECONDS = 5.0
FEED_TARE_STABLE_SPAN = 0.3
FEED_TARE_MIN_SAMPLES = 3
FEED_ZERO_TOLERANCE = 0.05
FEED_ZERO_TIMEOUT_SECONDS = 60
FEED_WEIGH_SECONDS = 3
DEFAULT_FLUSH_PUMP_SECONDS = 10.0
CALIBRATION_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "calibration_defaults.json"
)


class CalibrationSettings:
    def __init__(self):
        self._lock = threading.Lock()
        self._confidence = DETECTION_THRESHOLD
        self._feeder_multiplier = FEED_MULTIPLIER
        self._shrimp_weight_g = FEED_GRAMS_PER_SHRIMP
        self._feeder_pulse_seconds = FEED_PULSE_SECONDS
        self._flush_pump_seconds = DEFAULT_FLUSH_PUMP_SECONDS
        self._load()

    def as_dict(self):
        with self._lock:
            return {
                "confidence": self._confidence,
                "feeder_multiplier": self._feeder_multiplier,
                "shrimp_weight_g": self._shrimp_weight_g,
                "feeder_pulse_seconds": self._feeder_pulse_seconds,
                "flush_pump_seconds": self._flush_pump_seconds,
            }

    def get_confidence(self):
        with self._lock:
            return self._confidence

    def get_feeder_multiplier(self):
        with self._lock:
            return self._feeder_multiplier

    def get_shrimp_weight_g(self):
        with self._lock:
            return self._shrimp_weight_g

    def get_feeder_pulse_seconds(self):
        with self._lock:
            return self._feeder_pulse_seconds

    def get_flush_pump_seconds(self):
        with self._lock:
            return self._flush_pump_seconds

    def update(self, data):
        if not isinstance(data, dict):
            return False, "Invalid calibration payload"
        try:
            confidence = float(data.get("confidence", self.get_confidence()))
            multiplier = float(data.get("feeder_multiplier", self.get_feeder_multiplier()))
            shrimp_weight = float(data.get("shrimp_weight_g", self.get_shrimp_weight_g()))
            pulse = float(data.get("feeder_pulse_seconds", self.get_feeder_pulse_seconds()))
            flush_pump = float(data.get("flush_pump_seconds", self.get_flush_pump_seconds()))
        except (TypeError, ValueError):
            return False, "All calibration values must be numbers"
        if not 0.01 <= confidence <= 0.99:
            return False, "Confidence must be between 0.01 and 0.99"
        if multiplier <= 0:
            return False, "Feeder multiplier must be greater than 0"
        if shrimp_weight <= 0:
            return False, "Shrimp weight must be greater than 0"
        if pulse < 0:
            return False, "Feeder duration cannot be negative"
        if flush_pump < 0:
            return False, "Flush pump duration cannot be negative"
        with self._lock:
            self._confidence = round(confidence, 4)
            self._feeder_multiplier = round(multiplier, 6)
            self._shrimp_weight_g = round(shrimp_weight, 8)
            self._feeder_pulse_seconds = round(pulse, 3)
            self._flush_pump_seconds = round(flush_pump, 3)
        self._save()
        return True, None

    def _load(self):
        try:
            with open(CALIBRATION_SETTINGS_PATH, "r") as f:
                data = json.load(f)
        except (OSError, ValueError, TypeError):
            return
        if isinstance(data, dict):
            self.update(data)

    def _save(self):
        try:
            with open(CALIBRATION_SETTINGS_PATH, "w") as f:
                json.dump(self.as_dict(), f, indent=2)
        except OSError as exc:
            print(f"[Calibration] Could not save: {exc}")


calibration_mgr = CalibrationSettings()


class AutomationManager:
    """
    Runs the fixed PRESET_AUTOMATION_STEPS sequence in an endless loop until
    stopped, driving the same shared SerialManager the manual controls use.
    Each step's command is sent immediately, then the manager holds for that
    step's `duration` seconds (interruptible, checked every second) before
    moving to the next one; after the last step it starts again from the
    first.

    Starting requires a target shrimp count. During each full pass of the
    preset (one set), Detected holds the highest simultaneous box count.
    That peak is added to Counted only when the loop starts the next set.
    The loop keeps running until Counted reaches the target, then stops
    so the UI can show the feeder popup.

    Start/Stop is idempotent and thread-safe, so multiple browser tabs/
    devices (the Start Loop control in the shared navbar) can all
    start/stop/observe it at once.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._steps = [dict(s) for s in PRESET_AUTOMATION_STEPS]
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._current_index = -1
        self._seconds_left = 0
        self._target_count = None
        self._last_completed_count = None
        self._last_target_count = None
        self._just_completed = False
        self._feed_popup_pending = False
        self._feeder_seconds = DEFAULT_FEEDER_SECONDS
        self._load_saved_defaults()

    def get_feeder_seconds(self):
        with self._lock:
            return self._feeder_seconds

    def _load_saved_defaults(self):
        try:
            with open(AUTOMATION_SETTINGS_PATH, "r") as f:
                data = json.load(f)
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        durations = data.get("durations")
        if isinstance(durations, list) and len(durations) == len(self._steps):
            try:
                cleaned = [max(0.0, float(d)) for d in durations]
            except (TypeError, ValueError):
                cleaned = None
            if cleaned is not None and len(cleaned) == len(self._steps):
                for step, duration in zip(self._steps, cleaned):
                    step["duration"] = duration
        raw_feeder = data.get("feeder_seconds")
        if raw_feeder is not None:
            try:
                self._feeder_seconds = max(0.0, float(raw_feeder))
            except (TypeError, ValueError):
                pass

    def _save_defaults(self):
        payload = {
            "durations": [s["duration"] for s in self._steps],
            "feeder_seconds": self._feeder_seconds,
        }
        try:
            with open(AUTOMATION_SETTINGS_PATH, "w") as f:
                json.dump(payload, f, indent=2)
        except OSError as exc:
            print(f"[Automation] Could not save timing defaults: {exc}")

    def get_target_count(self):
        """Target shrimp count while the loop is running; None otherwise."""
        with self._lock:
            if self._running:
                return self._target_count
            return None

    def _set_default_state(self):
        """
        Force the hardware into the safe/default state before automation begins.
        """
        print("[Automation] Setting default hardware state...")

        for item in AUTOMATION_DEFAULT_STATE:
            self._send(item["device"], item["action"])

        # Give the ESP32 a short moment to receive/process the commands.
        time.sleep(0.5)

        print("[Automation] Default state established:")
        print("  Gate 1: CLOSED")
        print("  Gate 2: CLOSED")
        print("  Pump: OFF")
        print("  Feeder: OFF")

    def get_steps(self):
        return [dict(s) for s in self._steps]

    def set_durations(self, durations, feeder_seconds=None):
        """
        Updates each step's hold time in place (device/action stay fixed -
        only how long each step holds before the next one is adjustable).
        Optionally updates the feeder ON pulse used after a completed run.
        Saved values become the system default for later automation runs
        (including after restart). Returns False without changing anything
        if the input doesn't validate.
        """
        if not isinstance(durations, list) or len(durations) != len(self._steps):
            return False
        try:
            cleaned = [max(0.0, float(d)) for d in durations]
        except (TypeError, ValueError):
            return False
        cleaned_feeder = None
        if feeder_seconds is not None:
            try:
                cleaned_feeder = max(0.0, float(feeder_seconds))
            except (TypeError, ValueError):
                return False
        with self._lock:
            for step, duration in zip(self._steps, cleaned):
                step["duration"] = duration
            if cleaned_feeder is not None:
                self._feeder_seconds = cleaned_feeder
            self._save_defaults()
        return True

    def is_running(self):
        with self._lock:
            return self._running

    def get_status(self):
        """
        feed_popup_pending stays True after Counted >= To Count until the
        UI opens the feeder modal and acknowledges it. just_completed is
        kept in sync with that flag so two pollers cannot miss the popup.
        """
        with self._lock:
            completed_count = self._last_completed_count
            completed_feed_grams = (
                round(
                    completed_count
                    * calibration_mgr.get_shrimp_weight_g()
                    * calibration_mgr.get_feeder_multiplier(),
                    3,
                )
                if completed_count is not None else None
            )
            return {
                "running": self._running,
                "steps": [dict(s) for s in self._steps],
                "current_index": self._current_index,
                "seconds_left": self._seconds_left,
                "target_count": self._target_count,
                "just_completed": self._feed_popup_pending,
                "feed_popup_pending": self._feed_popup_pending,
                "completed_count": completed_count,
                "completed_target": self._last_target_count,
                "completed_feed_grams": completed_feed_grams,
                "feeder_seconds": self._feeder_seconds,
            }

    def acknowledge_feed_popup(self):
        with self._lock:
            self._feed_popup_pending = False
            self._just_completed = False
            return True

    def get_last_completed_count(self):
        with self._lock:
            return self._last_completed_count

    def start(self, target_count):
        with self._lock:
            if self._running:
                return False

            self._running = True
            self._target_count = target_count
            self._just_completed = False
            self._feed_popup_pending = False
            self._stop_event.clear()

        # Reset shrimp counter before starting the automation cycle.
        camera_mgr.reset_shrimp_count()

        # IMPORTANT:
        # Always force hardware into the safe/default state first.
        self._set_default_state()

        # Now start the actual automation loop.
        with self._lock:
            self._thread = threading.Thread(
                target=self._run,
                daemon=True
            )
            self._thread.start()

        return True

    def stop(self):
        with self._lock:
            if not self._running:
                already_idle = True
            else:
                self._stop_event.set()
                already_idle = False

        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)

        with self._lock:
            self._running = False
            self._current_index = -1
            self._seconds_left = 0
            self._target_count = None

        # Always return hardware to the safe/default state.
        self._set_default_state()

        return not already_idle

    def _send(self, device, action):
        command = _device_command(device, action)
        if command is None:
            return
        try:
            serial_mgr.send(command)
        except Exception as exc:
            print(f"[Automation] Send failed ({command}): {exc}")

    def _target_reached(self):
        with self._lock:
            target = self._target_count
        return target is not None and camera_mgr.get_shrimp_count() >= target

    def _hold(self, seconds):
        """Counts down `seconds` in <=1s ticks; True unless stopped early."""
        remaining = seconds
        while remaining > 0:
            if self._stop_event.is_set():
                return False
            tick = min(1.0, remaining)
            with self._lock:
                self._seconds_left = round(remaining, 1)
            if self._stop_event.wait(tick):
                return False
            remaining -= tick
        with self._lock:
            self._seconds_left = 0
        return True

    def _run(self):
        completed = False
        try:
            while not self._stop_event.is_set():
                camera_mgr.begin_detection_cycle()
                for index, step in enumerate(self._steps):
                    if self._stop_event.is_set():
                        return
                    with self._lock:
                        self._current_index = index
                        self._seconds_left = 0
                    self._send(step["device"], step["action"])
                    if step.get("capture"):
                        if not camera_mgr.capture_count_burst(self._stop_event):
                            return
                    if step["duration"] > 0:
                        if not self._hold(step["duration"]):
                            return
                if self._stop_event.is_set():
                    return
                camera_mgr.commit_cycle_count()
                if self._target_reached():
                    completed = True
                    return
        finally:
            with self._lock:
                self._running = False
                self._current_index = -1
                self._seconds_left = 0
                if completed:
                    self._last_completed_count = camera_mgr.get_shrimp_count()
                    self._last_target_count = self._target_count
                    self._just_completed = True
                    self._feed_popup_pending = True
                self._target_count = None
            if completed:
                camera_mgr.reset_shrimp_count()


automation_mgr = AutomationManager()


# ---------------------------------------------------------------------------
# Feed dispense manager - runs after detection completes: repeatedly pulses
# Relay 2 and checks the load-cell weight over serial, until the computed
# feed weight target is reached.
# ---------------------------------------------------------------------------
HX_WEIGHT_PATTERN = re.compile(r"HX:STREAM:WEIGHT:?\s*([-+]?[0-9]*\.?[0-9]+)", re.IGNORECASE)
WEIGHT_LINE_PATTERN = re.compile(r"^\s*([-+]?\d+\.\d+)\s*$")


def parse_serial_weight(text):
    """ESP printWeight() sends a bare decimal like '0.0' or '10.5'."""
    if not text:
        return None
    match = HX_WEIGHT_PATTERN.search(text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    match = WEIGHT_LINE_PATTERN.match(text.strip())
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def compute_feed_grams(shrimp_count):
    return round(
        int(shrimp_count)
        * calibration_mgr.get_shrimp_weight_g()
        * calibration_mgr.get_feeder_multiplier(),
        3,
    )


class FeedDispenseManager:
    """
    Manual feeder from the Camera page:

        1. Send ESP `W` so weight detection is ON
        2. Read the default scale value. If it is already 0.0, use that.
           If not, wait until the reading stays consistent for 5 seconds,
           treat that stable value as software-zero, then subtract a
           positive default (or add a negative default) from later readings.
        3. R2ON for 5 seconds, then R2OFF
        4. Read live (tare-corrected) weight; if still below the formula
           target, pulse R2 again
        5. Stop when corrected weight >= target (overshoot is allowed)
        6. Show the final result, then restore defaults (R2OFF, W off)
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._phase = "idle"
        self._cycle = 0
        self._target_grams = None
        self._current_weight = 0.0
        self._shrimp_count = None
        self._zero_streak = 0
        self._tare_offset = 0.0
        self._message = ""
        self._weight_detection_on = False

    def is_running(self):
        with self._lock:
            return self._running

    def get_status(self):
        with self._lock:
            return {
                "running": self._running,
                "phase": self._phase,
                "cycle": self._cycle,
                "target_grams": self._target_grams,
                "current_weight": self._current_weight,
                "shrimp_count": self._shrimp_count,
                "zero_streak": self._zero_streak,
                "tare_offset": self._tare_offset,
                "message": self._message,
            }

    def start(self, target_grams, shrimp_count=None):
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._target_grams = target_grams
            self._shrimp_count = shrimp_count
            self._current_weight = 0.0
            self._cycle = 0
            self._zero_streak = 0
            self._tare_offset = 0.0
            self._message = "Starting weight detection"
            self._phase = "waiting_zero"
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return True

    def stop(self):
        with self._lock:
            if not self._running:
                already_idle = True
            else:
                self._stop_event.set()
                already_idle = False
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3)
        self._restore_defaults()
        with self._lock:
            self._running = False
            self._phase = "idle"
            self._message = ""
            self._zero_streak = 0
            self._tare_offset = 0.0
            self._cycle = 0
            self._target_grams = None
            self._shrimp_count = None
            self._current_weight = 0.0
        return not already_idle

    def _set_state(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key if key.startswith("_") else f"_{key}", value)

    def _send(self, command):
        try:
            serial_mgr.send(command)
            return True
        except Exception as exc:
            print(f"[Feed] Send failed ({command}): {exc}")
            return False

    def _restore_defaults(self):
        self._send("R2OFF")
        if self._weight_detection_on:
            self._ensure_weight_detection(False)
        self._weight_detection_on = False

    def _ensure_weight_detection(self, want_on):
        deadline = time.time() + 5
        since_id = serial_mgr.get_latest_log_id()
        toggles = 0
        if not self._send("W"):
            return False
        toggles += 1
        while time.time() < deadline:
            if self._stop_event.is_set() and want_on:
                return False
            for entry in serial_mgr.get_log_since(since_id):
                since_id = max(since_id, entry["id"])
                if entry["dir"] != "in":
                    continue
                text = entry["text"] or ""
                if "HX711 not found" in text:
                    self._set_state(_phase="error", _message="HX711 not found")
                    return False
                if "Weight detection ON" in text:
                    self._weight_detection_on = True
                    if want_on:
                        return True
                    if toggles < 3:
                        self._send("W")
                        toggles += 1
                elif "Weight detection OFF" in text:
                    self._weight_detection_on = False
                    if not want_on:
                        return True
                    if toggles < 3:
                        self._send("W")
                        toggles += 1
            if self._stop_event.wait(0.1):
                if want_on:
                    return False
                break
        return self._weight_detection_on == want_on

    def _corrected_weight(self, raw):
        """Software-zero: subtract a positive default, add a negative default."""
        return round(float(raw) - self._tare_offset, 3)

    def _establish_tare(self):
        """
        Watch the scale for 5 seconds, then treat the average of those
        readings as 0.0. A positive default is subtracted later; a
        negative default is added.
        """
        self._set_state(
            _phase="waiting_zero",
            _message="Reading default weight",
            _zero_streak=0,
            _tare_offset=0.0,
        )
        samples = []
        started = time.time()
        since_id = serial_mgr.get_latest_log_id()
        deadline = started + FEED_ZERO_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self._stop_event.is_set():
                return False
            now = time.time()
            elapsed = now - started
            for entry in serial_mgr.get_log_since(since_id):
                since_id = max(since_id, entry["id"])
                if entry["dir"] != "in":
                    continue
                text = entry["text"] or ""
                if "HX711 not found" in text:
                    self._set_state(_phase="error", _message="HX711 not found")
                    return False
                weight = parse_serial_weight(text)
                if weight is None:
                    continue
                samples.append(weight)
                self._set_state(
                    _current_weight=weight,
                    _message=f"Default {weight:.1f} g - stabilizing {min(elapsed, FEED_TARE_SECONDS):.1f} of {FEED_TARE_SECONDS:.0f} sec",
                )

            now = time.time()
            elapsed = now - started
            if elapsed >= FEED_TARE_SECONDS and len(samples) >= FEED_TARE_MIN_SAMPLES:
                window = samples[-20:] if len(samples) > 20 else samples
                offset = sum(window) / len(window)
                if abs(offset) <= FEED_ZERO_TOLERANCE:
                    offset = 0.0
                self._tare_offset = offset
                self._set_state(
                    _tare_offset=offset,
                    _current_weight=0.0,
                    _zero_streak=3,
                    _message=(
                        "Already 0.0"
                        if offset == 0.0
                        else f"Zeroed at {offset:+.2f} g (removed from later readings)"
                    ),
                )
                return True

            if elapsed >= FEED_TARE_SECONDS and len(samples) < FEED_TARE_MIN_SAMPLES:
                self._set_state(_message="Waiting for scale readings...")

            if self._stop_event.wait(0.1):
                return False
        self._set_state(_phase="error", _message="No stable scale reading")
        return False

    def _dispense(self, seconds):
        self._send("R2ON")
        stopped_early = self._stop_event.wait(seconds)
        self._send("R2OFF")
        return not stopped_early

    def _watch_weight(self, seconds):
        since_id = serial_mgr.get_latest_log_id()
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self._stop_event.is_set():
                return False
            for entry in serial_mgr.get_log_since(since_id):
                since_id = max(since_id, entry["id"])
                if entry["dir"] != "in":
                    continue
                weight = parse_serial_weight(entry["text"])
                if weight is None:
                    continue
                corrected = self._corrected_weight(weight)
                with self._lock:
                    self._current_weight = corrected
            if self._stop_event.wait(0.1):
                return False
        return True

    def _weight_reached(self):
        with self._lock:
            if self._target_grams is None:
                return False
            return self._current_weight >= self._target_grams

    def _run(self):
        try:
            if not self._ensure_weight_detection(True):
                with self._lock:
                    if self._phase != "error":
                        self._phase = "error"
                        self._message = "Could not turn weight detection ON"
                return

            if not self._establish_tare():
                return

            while not self._stop_event.is_set():
                with self._lock:
                    self._cycle += 1
                    self._phase = "dispensing"
                    self._message = f"Dispensing pulse {self._cycle}"

                if not self._dispense(calibration_mgr.get_feeder_pulse_seconds()):
                    return

                with self._lock:
                    self._phase = "weighing"
                    self._message = "Checking weight"

                if not self._watch_weight(FEED_WEIGH_SECONDS):
                    return

                if self._weight_reached():
                    with self._lock:
                        self._phase = "done"
                        self._message = (
                            f"Done {self._current_weight:.1f} g / target {self._target_grams:.2f} g"
                        )
                    # Leave done visible until the UI calls stop() to default all.
                    return
        finally:
            with self._lock:
                still_done = self._phase == "done"
                still_error = self._phase == "error"
                self._running = still_done or still_error
            if not still_done:
                self._restore_defaults()
                if not still_error:
                    with self._lock:
                        self._running = False
                        self._phase = "idle"


feed_mgr = FeedDispenseManager()


# ---------------------------------------------------------------------------
# Flush manager - a one-shot (not looped) sequence triggered by the Flush
# button: close both gates, run the Pump for 10s, open both gates and hold
# 5s (pump still running), then stop the pump.
# ---------------------------------------------------------------------------
FLUSH_STEPS = [
    {"device": "servo1", "action": "close", "duration": 0},
    {"device": "servo2", "action": "close", "duration": 0},
    {"device": "relay1", "action": "on",    "duration": 10},
    {"device": "servo1", "action": "open",  "duration": 0},
    {"device": "servo2", "action": "open",  "duration": 5},
    {"device": "relay1", "action": "off",   "duration": 0},
]


class FlushManager:
    """
    Runs FLUSH_STEPS exactly once (not looped) when started. Cancelling
    (stop()) mid-run leaves the hardware wherever it was in the sequence -
    the same "stop where it is" behavior as AutomationManager's manual
    stop, rather than trying to guess a safe state to snap back to.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._current_index = -1
        self._seconds_left = 0

    def is_running(self):
        with self._lock:
            return self._running

    def _flush_steps(self):
        steps = [dict(s) for s in FLUSH_STEPS]
        pump = calibration_mgr.get_flush_pump_seconds()
        for step in steps:
            if step.get("device") == "relay1" and step.get("action") == "on":
                step["duration"] = pump
        return steps

    def get_status(self):
        with self._lock:
            return {
                "running": self._running,
                "steps": self._flush_steps(),
                "current_index": self._current_index,
                "seconds_left": self._seconds_left,
            }

    def start(self):
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._current_index = -1
            self._seconds_left = 0
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return True

    def stop(self):
        with self._lock:
            if not self._running:
                already_idle = True
            else:
                self._stop_event.set()
                already_idle = False
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        with self._lock:
            self._running = False
            self._current_index = -1
            self._seconds_left = 0
        return not already_idle

    def _send(self, device, action):
        command = _device_command(device, action)
        if command is None:
            return
        try:
            serial_mgr.send(command)
        except Exception as exc:
            print(f"[Flush] Send failed ({command}): {exc}")

    def _hold(self, seconds):
        remaining = seconds
        while remaining > 0:
            if self._stop_event.is_set():
                return False
            tick = min(1.0, remaining)
            with self._lock:
                self._seconds_left = round(remaining, 1)
            if self._stop_event.wait(tick):
                return False
            remaining -= tick
        with self._lock:
            self._seconds_left = 0
        return True

    def _run(self):
        try:
            for index, step in enumerate(self._flush_steps()):
                if self._stop_event.is_set():
                    return
                with self._lock:
                    self._current_index = index
                    self._seconds_left = 0
                self._send(step["device"], step["action"])
                if step["duration"] > 0:
                    if not self._hold(step["duration"]):
                        return
        finally:
            with self._lock:
                self._running = False
                self._current_index = -1
                self._seconds_left = 0


flush_mgr = FlushManager()


# ---------------------------------------------------------------------------
# Camera handler - Picamera2 preview + Ultralytics YOLO still-frame counting
# ---------------------------------------------------------------------------
class CameraManager:
    """
    Captures frames with Picamera2 for a YOLO-free live preview. After each
    automation set (pump off, gate closed), runs a ByteTrack burst and adds
    the peak unique-ID count. If the camera or weights are missing, the UI
    still runs with a placeholder frame.
    """
    def __init__(self, resolution=CAMERA_RESOLUTION):
        self.resolution = resolution
        self.available = False
        self.camera_cap = None
        self.yolo_model = None
        self.labels = ["shrimp"]
        self.total_shrimp_count = 0
        self.live_detection_count = 0
        self.peak_detection_count = 0
        self._cycle_lock = threading.Lock()
        self._burst_lock = threading.Lock()
        self._burst_running = False
        self._live_lock = threading.Lock()
        self._live_feed_enabled = False
        self._frame_lock = threading.Lock()
        self._roi_lock = threading.Lock()
        self._roi = dict(DEFAULT_ROI)
        self._frame_is_bgr = True
        self._fallback_id = 10000
        self._load_camera_settings()

    def start(self):
        if self.available:
            return True
        if not CV2_AVAILABLE:
            print("[Camera] opencv not available - showing placeholder feed.")
            return False
        if not PICAMERA2_AVAILABLE:
            print("[Camera] picamera2 not available - showing placeholder feed.")
            return False
        try:
            self._setup_camera()
            self._setup_yolo()
            self.available = True
            return True
        except Exception as exc:
            print(f"[Camera] Could not start camera: {exc}")
            traceback.print_exc()
            self.available = False
            return False

    def _setup_camera(self):
        self.camera_cap = PiCamCapture(
            size=CAMERA_RESOLUTION, buffer_count=CAMERA_BUFFER_COUNT
        )
        if not self.camera_cap.isOpened():
            raise RuntimeError("Could not open Picamera2 capture.")
        print("[Camera] Picamera2 capture ready.")

    def _setup_yolo(self):
        if os.path.isfile(YOLO_LABELS_PATH):
            with open(YOLO_LABELS_PATH, "r", encoding="utf-8") as fh:
                self.labels = [line.strip() for line in fh if line.strip()] or ["shrimp"]
        if not YOLO_AVAILABLE:
            print("[Camera] Ultralytics is not installed; burst counting is disabled.")
            return
        if not os.path.isfile(YOLO_WEIGHTS_PATH):
            print(
                f"[Camera] YOLO weights not found: {YOLO_WEIGHTS_PATH}. "
                "Place models/best.pt before running a count cycle."
            )
            return
        self.yolo_model = YOLO(YOLO_WEIGHTS_PATH)
        print(f"[Camera] YOLO loaded from {YOLO_WEIGHTS_PATH}")

    def is_bursting(self):
        with self._burst_lock:
            return self._burst_running

    def live_feed_enabled(self):
        with self._live_lock:
            return self._live_feed_enabled

    def set_live_feed(self, enabled):
        """
        Turn the YOLO-free preview grabber on/off. During automation the
        preview is always treated as off, so the browser never streams
        mid-cycle. Returns True if the feed is actually on afterwards.
        """
        with self._live_lock:
            self._live_feed_enabled = bool(enabled)
            requested = self._live_feed_enabled
        if requested and automation_mgr.is_running():
            return False
        return requested

    def live_feed_status(self):
        enabled = self.live_feed_enabled() and not automation_mgr.is_running()
        return {
            "enabled": enabled,
            "automation_running": automation_mgr.is_running(),
            "available": self.available,
        }

    def _grab_bgr(self):
        with self._frame_lock:
            if self.camera_cap is None or not self.camera_cap.isOpened():
                return None
            ok, frame = self.camera_cap.read()
            if not ok or frame is None:
                return None
            return frame

    def pump_preview(self):
        """Grab a preview frame with ROI only (no YOLO). True if pushed."""
        if not self.available:
            return False
        if self.is_bursting():
            return False
        frame = self._grab_bgr()
        if frame is None:
            return False
        self._draw_roi_only(frame)
        latest_frame.set(self._to_pil(frame))
        return True

    def get_frame(self):
        img = latest_frame.get()
        if img is not None:
            return img
        if self.available:
            return self._placeholder_image("Waiting for first camera frame...")
        return self._placeholder_image("Camera not available")

    def begin_detection_cycle(self):
        with self._cycle_lock:
            self.peak_detection_count = 0
            self.live_detection_count = 0
        self._fallback_id = 10000
        if self.yolo_model is not None:
            self.yolo_model.predictor = None

    def capture_count_burst(self, stop_event=None):
        """
        Track ~8 frames after the gate closes. Count for this set is the
        maximum number of unique ROI track IDs in any one frame. Saves 3
        annotated stills to the gallery. Returns False if stopped early.
        """
        with self._burst_lock:
            self._burst_running = True
        try:
            if self.yolo_model is None:
                print("[Camera] YOLO model not loaded; burst count is 0.")
                with self._cycle_lock:
                    self.peak_detection_count = 0
                return True

            self.yolo_model.predictor = None
            self._fallback_id = 10000
            frames_meta = []

            for i in range(BURST_FRAME_COUNT):
                if stop_event is not None and stop_event.is_set():
                    return False
                frame = self._grab_bgr()
                if frame is None:
                    time.sleep(BURST_INTERVAL_S)
                    continue
                dets = self._track_frame(frame)
                dets = self._filter_to_roi(dets, frame.shape[1], frame.shape[0])
                dets = self._assign_missing_ids(dets)
                ids = {d["id"] for d in dets if d.get("id") is not None}
                n = len(ids)
                annotated = frame.copy()
                self._draw_annotations(annotated, dets, n)
                frames_meta.append((n, annotated))
                with self._cycle_lock:
                    self.live_detection_count = n
                    if n > self.peak_detection_count:
                        self.peak_detection_count = n
                latest_frame.set(self._to_pil(annotated))
                if i + 1 < BURST_FRAME_COUNT:
                    time.sleep(BURST_INTERVAL_S)

            self._save_burst_gallery(frames_meta)
            print(
                f"[Camera] Burst done: peak unique IDs = "
                f"{self.peak_detection_count} over {len(frames_meta)} frames"
            )
            return True
        except Exception as exc:
            print(f"[Camera] Burst capture failed: {exc}")
            traceback.print_exc()
            return True
        finally:
            with self._burst_lock:
                self._burst_running = False

    def _track_frame(self, frame_bgr):
        tracker = YOLO_TRACKER_PATH if os.path.isfile(YOLO_TRACKER_PATH) else "bytetrack.yaml"
        # Box coordinates are the same for either channel order, so detections
        # still line up with the original frame_bgr used for drawing.
        if MODEL_EXPECTS_SWAPPED_RB:
            model_input = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        else:
            model_input = frame_bgr
        results = self.yolo_model.track(
            model_input,
            persist=True,
            tracker=tracker,
            conf=calibration_mgr.get_confidence(),
            iou=DETECTION_IOU,
            max_det=DETECTION_MAX_DETECTIONS,
            verbose=False,
        )
        dets = []
        if not results:
            return dets
        r = results[0]
        if r.boxes is None or len(r.boxes) == 0:
            return dets
        boxes = r.boxes
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy() if boxes.conf is not None else [0.0] * len(xyxy)
        clss = boxes.cls.cpu().numpy() if boxes.cls is not None else [0] * len(xyxy)
        has_ids = boxes.id is not None
        ids = boxes.id.cpu().numpy() if has_ids else [None] * len(xyxy)
        for i, box in enumerate(xyxy):
            x1, y1, x2, y2 = [float(v) for v in box]
            tid = int(ids[i]) if has_ids and ids[i] is not None else None
            dets.append({
                "box": (x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)),
                "conf": float(confs[i]),
                "category": int(clss[i]),
                "id": tid,
            })
        return dets

    @staticmethod
    def _box_iou(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ax2, ay2 = ax + aw, ay + ah
        bx2, by2 = bx + bw, by + bh
        ix1, iy1 = max(ax, bx), max(ay, by)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
        inter = iw * ih
        union = aw * ah + bw * bh - inter
        if union <= 0:
            return 0.0
        return inter / union

    def _assign_missing_ids(self, dets):
        identified = [d for d in dets if d.get("id") is not None]
        for d in dets:
            if d.get("id") is not None:
                continue
            if any(self._box_iou(d["box"], o["box"]) > MISSING_ID_IOU for o in identified):
                continue
            d["id"] = self._fallback_id
            self._fallback_id += 1
            identified.append(d)
        return dets

    def _save_burst_gallery(self, frames_meta):
        if not frames_meta:
            return
        n = len(frames_meta)
        peak_i = max(range(n), key=lambda i: frames_meta[i][0])
        indices = {0, peak_i, n - 1}
        if len(indices) < BURST_GALLERY_COUNT and n >= BURST_GALLERY_COUNT:
            indices.add(n // 2)
        extra = 0
        while len(indices) < min(BURST_GALLERY_COUNT, n):
            if extra not in indices:
                indices.add(extra)
            extra += 1
        for i in sorted(indices)[:BURST_GALLERY_COUNT]:
            count, arr = frames_meta[i]
            try:
                filename = save_snapshot(self._to_pil(arr))
                print(f"[Camera] Gallery still saved: {filename} (ids={count})")
            except Exception as exc:
                print(f"[Camera] Could not save burst still: {exc}")

    def _draw_roi_only(self, arr):
        height, width = arr.shape[:2]
        rx1, ry1, rx2, ry2 = self._roi_pixels(width, height)
        if (rx1, ry1, rx2, ry2) != (0, 0, width - 1, height - 1):
            cv2.rectangle(arr, (rx1, ry1), (rx2, ry2), self._c(ROI_COLOR), 2)
            cv2.putText(
                arr, "ROI", (rx1 + 6, min(height - 6, ry1 + 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, self._c(ROI_COLOR), 2
            )

    def _draw_annotations(self, arr, detections, unique_count):
        height, width = arr.shape[:2]
        self._draw_roi_only(arr)
        for det in detections:
            x, y, w, h = det["box"]
            cx, cy = int(x + w / 2), int(y + h / 2)
            cv2.rectangle(
                arr, (int(x), int(y)), (int(x + w), int(y + h)),
                self._c(DETECTION_BOX_COLOR), 2
            )
            cv2.circle(arr, (cx, cy), 3, self._c(DETECTION_CENTROID_COLOR), -1)
            tid = det.get("id")
            label = f"shrimp #{tid}" if tid is not None else "shrimp"
            cv2.putText(
                arr, label,
                (int(x), max(16, int(y) - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, self._c(DETECTION_LABEL_COLOR), 1
            )
        text = f"Detected: {unique_count}"
        cv2.putText(
            arr, text, (20, 30), cv2.FONT_HERSHEY_SIMPLEX,
            0.8, self._c(DETECTED_COUNT_TEXT_COLOR), 2
        )

    def get_shrimp_count(self):
        with self._cycle_lock:
            return self.total_shrimp_count

    def get_live_detection_count(self):
        with self._cycle_lock:
            return self.peak_detection_count

    def commit_cycle_count(self):
        with self._cycle_lock:
            added = int(self.peak_detection_count)
            self.total_shrimp_count += added
            total = self.total_shrimp_count
        print(f"[Camera] Automation set finished: +{added} -> Counted {total}")
        return total

    def reset_shrimp_count(self):
        with self._cycle_lock:
            self.total_shrimp_count = 0
            self.live_detection_count = 0
            self.peak_detection_count = 0
        self._fallback_id = 10000
        if self.yolo_model is not None:
            self.yolo_model.predictor = None

    def _load_camera_settings(self):
        try:
            with open(CAMERA_SETTINGS_PATH, "r") as f:
                data = json.load(f)
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        roi = data.get("roi")
        if isinstance(roi, dict):
            cleaned, _err = self._validate_roi(roi)
            if cleaned is not None:
                self._roi = cleaned

    def _save_camera_settings(self):
        with self._roi_lock:
            payload = {"roi": dict(self._roi)}
        try:
            with open(CAMERA_SETTINGS_PATH, "w") as f:
                json.dump(payload, f, indent=2)
        except OSError as exc:
            print(f"[Camera] Could not save camera defaults: {exc}")

    @staticmethod
    def _validate_roi(data):
        try:
            left = float(data.get("left", 0.0))
            top = float(data.get("top", 0.0))
            right = float(data.get("right", 1.0))
            bottom = float(data.get("bottom", 1.0))
        except (TypeError, ValueError, AttributeError):
            return None, "ROI values must be numbers between 0 and 1."
        left, top = min(1.0, max(0.0, left)), min(1.0, max(0.0, top))
        right, bottom = min(1.0, max(0.0, right)), min(1.0, max(0.0, bottom))
        if right - left < ROI_MIN_SIZE or bottom - top < ROI_MIN_SIZE:
            return None, "ROI is too small (or left/right, top/bottom are swapped)."
        return {
            "left": round(left, 4), "top": round(top, 4),
            "right": round(right, 4), "bottom": round(bottom, 4),
        }, None

    def get_roi_settings(self):
        with self._roi_lock:
            return {"roi": dict(self._roi)}

    def set_roi_settings(self, data):
        if not isinstance(data, dict):
            return False, "Invalid ROI payload."
        roi = None
        if any(k in data for k in ("left", "top", "right", "bottom")):
            with self._roi_lock:
                merged = dict(self._roi)
            merged.update({k: data[k] for k in ("left", "top", "right", "bottom") if k in data})
            roi, err = self._validate_roi(merged)
            if roi is None:
                return False, err
        with self._roi_lock:
            if roi is not None:
                self._roi = roi
        self._save_camera_settings()
        return True, None

    def reset_roi(self):
        with self._roi_lock:
            self._roi = dict(DEFAULT_ROI)
        self._save_camera_settings()

    def _roi_pixels(self, width, height):
        with self._roi_lock:
            roi = dict(self._roi)
        x1 = int(round(roi["left"] * (width - 1)))
        y1 = int(round(roi["top"] * (height - 1)))
        x2 = int(round(roi["right"] * (width - 1)))
        y2 = int(round(roi["bottom"] * (height - 1)))
        return x1, y1, x2, y2

    def _filter_to_roi(self, detections, width, height):
        x1, y1, x2, y2 = self._roi_pixels(width, height)
        if (x1, y1, x2, y2) == (0, 0, width - 1, height - 1):
            return detections
        kept = []
        for det in detections:
            bx, by, bw, bh = det["box"]
            cx, cy = bx + bw / 2, by + bh / 2
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                kept.append(det)
        return kept

    def _c(self, rgb):
        return tuple(reversed(rgb)) if self._frame_is_bgr else rgb

    def _to_pil(self, arr):
        if self._frame_is_bgr:
            return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))
        return Image.fromarray(arr.copy())

    def _placeholder_image(self, message):
        img = Image.new("RGB", self.resolution, color=(20, 22, 28))
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), message)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((self.resolution[0] - tw) / 2, (self.resolution[1] - th) / 2),
            message, fill=(139, 143, 163)
        )
        return img

    def stop(self):
        if self.camera_cap is not None:
            try:
                self.camera_cap.release()
            except Exception:
                pass
            self.camera_cap = None


camera_mgr = CameraManager()
_kiosk_process = None


def _stop_app_services():
    automation_mgr.stop()
    feed_mgr.stop()
    flush_mgr.stop()
    serial_mgr.shutdown()
    camera_mgr.stop()


class LatestFrame:
    """
    Thread-safe holder for the most recent camera frame. A single background
    thread (camera_capture_loop) is the only thing that touches the camera -
    the Flask video stream and the snapshot/capture routes just read the
    cached result here, so the camera hardware is only ever accessed from
    one thread at a time.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._image = None
        self._jpeg = None
        self._version = 0

    def set(self, img):
        with self._lock:
            self._image = img
            self._jpeg = None      # old JPEG is freed; re-encoded on demand
            self._version += 1

    def get(self):
        with self._lock:
            return self._image

    def get_jpeg(self, quality=STREAM_JPEG_QUALITY):
        """
        JPEG bytes of the latest frame, encoded ONCE per frame and shared by
        every browser watching the stream (instead of each viewer encoding
        its own copy). Returns (bytes or None, version).
        """
        with self._lock:
            if self._jpeg is None and self._image is not None:
                self._jpeg = encode_jpeg(self._image, quality=quality)
            return self._jpeg, self._version


latest_frame = LatestFrame()
CAMERA_CAPTURE_FPS = 15


def camera_capture_loop():
    """
    Preview-only grabber. YOLO is NOT run here - it only runs inside
    CameraManager.capture_count_burst() after the pump stops and the gate
    closes. Frames are pushed to latest_frame only while the Live Feed
    toggle is on (and automation is not running), so the browser does not
    stream during a count cycle.
    """
    interval = 1.0 / CAMERA_CAPTURE_FPS
    placeholder_set = False
    while True:
        if not camera_mgr.available:
            if not placeholder_set:
                # Build the placeholder once instead of a new image every tick.
                latest_frame.set(
                    camera_mgr._placeholder_image("Camera not available")
                )
                placeholder_set = True
            time.sleep(0.5)
            continue
        placeholder_set = False
        try:
            if camera_mgr.live_feed_enabled() and not automation_mgr.is_running():
                if not camera_mgr.pump_preview():
                    time.sleep(0.2)
                    continue
        except Exception as exc:
            print(f"[Camera] Preview grab failed: {exc}")
            time.sleep(0.5)
            continue
        time.sleep(interval)


def encode_jpeg(img, quality=85):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def save_snapshot(img):
    """Saves img to SNAPSHOT_DIR with a unique timestamped filename; returns the filename."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    base = time.strftime('%Y%m%d_%H%M%S')
    filename = f"snapshot_{base}.jpg"
    # The burst saves up to 3 stills within a second, so guarantee uniqueness
    # instead of letting same-second stills overwrite each other.
    suffix = 1
    while os.path.exists(os.path.join(SNAPSHOT_DIR, filename)):
        filename = f"snapshot_{base}_{suffix}.jpg"
        suffix += 1
    path = os.path.join(SNAPSHOT_DIR, filename)
    img.save(path, quality=92)
    return filename


# ---------------------------------------------------------------------------
# Flask web server (runs in a background thread)
# ---------------------------------------------------------------------------
flask_app = Flask(
    __name__,
    static_folder="assets",
    static_url_path="/assets",
)


@flask_app.route("/api/ports", methods=["GET"])
def api_ports():
    return jsonify({"ports": serial_mgr.list_ports()})


@flask_app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({"connected": serial_mgr.is_connected(), "port": serial_mgr.port_name})


@flask_app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    """
    Powers off the Raspberry Pi, after cleanly stopping any running
    automation, closing the serial connection, and stopping the camera.
    Requires passwordless sudo for shutdown (sudo visudo -> add:
    yourusername ALL=(ALL) NOPASSWD: /sbin/shutdown).
    """
    _stop_app_services()
    try:
        subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


@flask_app.route("/api/exit-app", methods=["POST"])
def api_exit_app():
    """
    Closes the kiosk desktop app and stops this Python process without
    powering off the Raspberry Pi.
    """
    def later():
        time.sleep(0.25)
        proc = _kiosk_process
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            return
        _stop_app_services()
        os._exit(0)

    threading.Thread(target=later, daemon=True).start()
    return jsonify({"ok": True})


@flask_app.route("/api/calibration", methods=["GET"])
def api_calibration_get():
    return jsonify(calibration_mgr.as_dict())


@flask_app.route("/api/calibration", methods=["POST"])
def api_calibration_set():
    data = request.get_json(silent=True) or {}
    ok, err = calibration_mgr.update(data)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "settings": calibration_mgr.as_dict()})


@flask_app.route("/api/connect", methods=["POST"])
def api_connect():
    data = request.get_json(force=True)
    port = data.get("port")
    if not port:
        return jsonify({"ok": False, "error": "No port specified"}), 400
    try:
        serial_mgr.connect(port, manual=True)
        return jsonify({"ok": True, "port": port})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@flask_app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    serial_mgr.disconnect(manual=True)
    return jsonify({"ok": True})


@flask_app.route("/api/send", methods=["POST"])
def api_send():
    data = request.get_json(force=True)
    command = data.get("command", "")
    if not command:
        return jsonify({"ok": False, "error": "No command specified"}), 400
    try:
        serial_mgr.send(command)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@flask_app.route("/api/log", methods=["GET"])
def api_log():
    since = request.args.get("since", default=0, type=int)
    return jsonify({"entries": serial_mgr.get_log_since(since)})


def _generate_mjpeg():
    interval = 1.0 / 12  # never stream faster than this
    last_version = -1
    while True:
        frame_bytes, version = latest_frame.get_jpeg()
        if frame_bytes is None or version == last_version:
            time.sleep(0.05)   # no new frame yet - don't resend the same one
            continue
        last_version = version
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        time.sleep(interval)


@flask_app.route("/video_feed")
def video_feed():
    return Response(_generate_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@flask_app.route("/api/shrimp_count", methods=["GET"])
def api_shrimp_count():
    return jsonify({
        "count": camera_mgr.get_shrimp_count(),
        "detected": camera_mgr.get_live_detection_count(),
    })


@flask_app.route("/api/shrimp_count/reset", methods=["POST"])
def api_shrimp_count_reset():
    camera_mgr.reset_shrimp_count()
    return jsonify({"ok": True, "count": camera_mgr.get_shrimp_count()})


@flask_app.route("/api/live_feed", methods=["GET"])
def api_live_feed_get():
    return jsonify(camera_mgr.live_feed_status())


@flask_app.route("/api/live_feed", methods=["POST"])
def api_live_feed_set():
    """
    Body: {"enabled": bool} (optional; toggles when omitted).
    Live Feed is forced off while automation runs.
    """
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        wanted = bool(data.get("enabled"))
    else:
        wanted = not camera_mgr.live_feed_enabled()
    enabled = camera_mgr.set_live_feed(wanted)
    return jsonify({"ok": True, "enabled": enabled, **camera_mgr.live_feed_status()})


@flask_app.route("/api/snapshot", methods=["GET"])
def api_snapshot():
    """
    One JPEG still of the most recent camera frame (ROI outline drawn).
    Used by the ROI modal preview without keeping the MJPEG stream open:
    it grabs a fresh frame even when the Live Feed toggle is off, and only
    skips grabbing while a count cycle is running.
    """
    if not automation_mgr.is_running():
        try:
            camera_mgr.pump_preview()
        except Exception as exc:
            print(f"[Camera] Snapshot preview grab failed: {exc}")
    img = latest_frame.get()
    if img is None:
        return Response(status=503)
    return Response(encode_jpeg(img, quality=85), mimetype="image/jpeg")


@flask_app.route("/api/roi", methods=["GET"])
def api_roi_get():
    return jsonify(camera_mgr.get_roi_settings())


@flask_app.route("/api/roi", methods=["POST"])
def api_roi_set():
    """
    Body (any subset): {"left":0-1, "top":0-1, "right":0-1, "bottom":0-1}.
    Saved as default. Unique-ID counting uses this box; no live detection
    runs against it any more.
    """
    data = request.get_json(silent=True) or {}
    ok, err = camera_mgr.set_roi_settings(data)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, **camera_mgr.get_roi_settings()})


@flask_app.route("/api/roi/reset", methods=["POST"])
def api_roi_reset():
    camera_mgr.reset_roi()
    return jsonify({"ok": True, **camera_mgr.get_roi_settings()})


@flask_app.route("/api/capture", methods=["POST"])
def api_capture():
    img = latest_frame.get()
    if img is None:
        return jsonify({"ok": False, "error": "No camera frame available yet."}), 503
    try:
        filename = save_snapshot(img)
        return jsonify({"ok": True, "filename": filename})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@flask_app.route("/api/automation", methods=["GET"])
def api_automation_get():
    return jsonify(automation_mgr.get_status())


@flask_app.route("/api/automation/feed-popup-ack", methods=["POST"])
def api_automation_feed_popup_ack():
    automation_mgr.acknowledge_feed_popup()
    return jsonify({"ok": True})


@flask_app.route("/api/automation/durations", methods=["POST"])
def api_automation_set_durations():
    """
    Adjusts how long (seconds) each step of the fixed preset sequence holds
    before moving to the next one. The steps themselves (which device, which
    action, and their order) are fixed - only the durations are editable.
    """
    data = request.get_json(force=True)
    durations = data.get("durations") if isinstance(data, dict) else None
    if not automation_mgr.set_durations(durations):
        return jsonify({
            "ok": False,
            "error": f"Expected a list of {len(automation_mgr.get_steps())} non-negative numbers."
        }), 400
    return jsonify({"ok": True, "steps": automation_mgr.get_steps()})


@flask_app.route("/api/automation/start", methods=["POST"])
def api_automation_start():
    if flush_mgr.is_running():
        return jsonify({"ok": False, "error": "Flush is running - wait for it to finish first."}), 400

    data = request.get_json(silent=True) or {}
    raw_target = data.get("target_count")
    try:
        target_count = int(raw_target)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "target_count is required and must be a whole number."}), 400
    if target_count <= 0:
        return jsonify({"ok": False, "error": "target_count must be greater than 0."}), 400

    started = automation_mgr.start(target_count)
    return jsonify({"ok": True, "started": started, "status": automation_mgr.get_status()})


@flask_app.route("/api/automation/stop", methods=["POST"])
def api_automation_stop():
    stopped = automation_mgr.stop()
    return jsonify({"ok": True, "stopped": stopped, "status": automation_mgr.get_status()})


@flask_app.route("/api/feed/status", methods=["GET"])
def api_feed_status():
    return jsonify(feed_mgr.get_status())


@flask_app.route("/api/feed/start", methods=["POST"])
def api_feed_start():
    """
    Starts the feeder: ESP weight detection ON, software-zero from a
    5s stable default reading, then pulse R2 for 5s until tare-corrected
    grams >= shrimp_count * 0.00333 * FEED_MULTIPLIER.
    """
    if flush_mgr.is_running():
        return jsonify({"ok": False, "error": "Flush is running - wait for it to finish first."}), 400
    if automation_mgr.is_running():
        return jsonify({"ok": False, "error": "Automation is running - stop the loop first."}), 400
    if feed_mgr.is_running():
        return jsonify({"ok": False, "error": "Feeder is already running."}), 400

    data = request.get_json(silent=True) or {}
    shrimp_count = data.get("shrimp_count")
    if shrimp_count in (None, ""):
        shrimp_count = automation_mgr.get_last_completed_count()
    if not shrimp_count:
        shrimp_count = camera_mgr.get_shrimp_count()
    try:
        shrimp_count = int(shrimp_count)
    except (TypeError, ValueError):
        shrimp_count = 0
    if shrimp_count < 1:
        return jsonify({"ok": False, "error": "Enter a shrimp count first."}), 400

    target_grams = compute_feed_grams(shrimp_count)
    started = feed_mgr.start(target_grams, shrimp_count=shrimp_count)
    return jsonify({"ok": True, "started": started, "status": feed_mgr.get_status()})


@flask_app.route("/api/feed/stop", methods=["POST"])
def api_feed_stop():
    stopped = feed_mgr.stop()
    return jsonify({"ok": True, "stopped": stopped, "status": feed_mgr.get_status()})


@flask_app.route("/api/flush/status", methods=["GET"])
def api_flush_status():
    return jsonify(flush_mgr.get_status())


@flask_app.route("/api/flush/start", methods=["POST"])
def api_flush_start():
    if automation_mgr.is_running():
        return jsonify({"ok": False, "error": "Stop the automation loop first."}), 400
    if feed_mgr.is_running():
        return jsonify({"ok": False, "error": "Feed dispensing is running - wait for it to finish first."}), 400

    started = flush_mgr.start()
    return jsonify({"ok": True, "started": started, "status": flush_mgr.get_status()})


@flask_app.route("/api/flush/stop", methods=["POST"])
def api_flush_stop():
    stopped = flush_mgr.stop()
    return jsonify({"ok": True, "stopped": stopped, "status": flush_mgr.get_status()})


@flask_app.route("/api/gallery", methods=["GET"])
def api_gallery():
    files = sorted(
        glob.glob(os.path.join(SNAPSHOT_DIR, "*.jpg")),
        key=lambda p: os.path.getmtime(p), reverse=True
    )
    items = [
        {
            "filename": os.path.basename(p),
            "url": f"/snapshots/{os.path.basename(p)}",
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p))),
        }
        for p in files
    ]
    return jsonify({"items": items})


@flask_app.route("/snapshots/<path:filename>")
def serve_snapshot(filename):
    return send_from_directory(SNAPSHOT_DIR, filename)


# ---------------------------------------------------------------------------
# Web pages: Camera, Controls, Gallery, and the Splash screen each live in
# their own top-level module (camera.py, controls.py, gallery.py,
# splash.py) as Flask blueprints, sharing the HTML shell (render_page,
# defined above) for the three main pages.
# ---------------------------------------------------------------------------
flask_app.register_blueprint(create_camera_blueprint(render_page))
flask_app.register_blueprint(create_controls_blueprint(
    render_page,
    SERVO1_OPEN_DEG,
    SERVO1_CLOSE_DEG,
    SERVO2_OPEN_DEG,
    SERVO2_CLOSE_DEG,
))
flask_app.register_blueprint(create_gallery_blueprint(render_page))
flask_app.register_blueprint(create_splash_blueprint(SPLASH_DURATION_MS, SPLASH_BG_COLOR))


def run_flask():
    # threaded=True lets it serve the LCD app's own requests (if any) and
    # remote browsers at the same time. use_reloader must stay off since
    # this runs inside a background thread, not the main process.
    flask_app.run(host="0.0.0.0", port=WEB_PORT, debug=False, threaded=True, use_reloader=False)


def launch_kiosk_browser(url):
    """
    Launches whichever kiosk-capable browser is available in fullscreen
    kiosk mode, pointed at `url`. Returns the subprocess.Popen handle, or
    None if no supported browser was found (e.g. testing off a Pi).

    Uses a dedicated --user-data-dir so this always starts a genuinely new
    browser process, even if another Chromium/Chrome window is already
    running under the normal desktop profile.
    """
    browser_path = None
    for candidate in KIOSK_BROWSER_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            browser_path = found
            break

    if browser_path is None:
        return None

    profile_dir = tempfile.mkdtemp(prefix="kiosk-profile-")

    args = [
        browser_path,
        f"--user-data-dir={profile_dir}",
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--disable-session-crashed-bubble",
        "--disable-features=TranslateUI",
        "--check-for-update-interval=31536000",
        "--overscroll-history-navigation=0",
        "--no-first-run",
        # Memory savers for the kiosk browser (usually the biggest RAM user):
        "--renderer-process-limit=1",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-component-update",
        "--disable-default-apps",
        "--js-flags=--max-old-space-size=128",
        url,
    ]

    try:
        process = subprocess.Popen(args)
    except Exception as exc:
        print(f"[Kiosk] Failed to launch {browser_path}: {exc}")
        shutil.rmtree(profile_dir, ignore_errors=True)
        return None

    process._kiosk_profile_dir = profile_dir  # cleaned up after process.wait()
    return process


if __name__ == "__main__":
    # Ultralytics YOLO runs only inside the post-gate burst, never on the
    # live preview. The preview is opt-in via the Live Feed button.
    print("[Startup] Initializing camera pipeline (Picamera2 preview + YOLO burst count).")
    print("[Startup] Flask and kiosk start only after the camera reports ready.")
    camera_mgr.start()
    serial_mgr.start_watcher()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    camera_thread = threading.Thread(target=camera_capture_loop, daemon=True)
    camera_thread.start()

    # Give Flask a moment to start listening before pointing a browser at it.
    time.sleep(1.5)

    kiosk_url = f"http://127.0.0.1:{WEB_PORT}/splash"
    _kiosk_process = launch_kiosk_browser(kiosk_url)

    if _kiosk_process is not None:
        print(f"[Kiosk] Launched kiosk browser -> {kiosk_url}")
        try:
            _kiosk_process.wait()
        except KeyboardInterrupt:
            pass
        finally:
            profile_dir = getattr(_kiosk_process, "_kiosk_profile_dir", None)
            if profile_dir:
                shutil.rmtree(profile_dir, ignore_errors=True)
    else:
        print(
            "[Kiosk] No kiosk-capable browser found (tried: "
            f"{', '.join(KIOSK_BROWSER_CANDIDATES)}). "
            f"Open {kiosk_url} manually, or install chromium-browser."
        )
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    # Clean shutdown once the kiosk browser closes (or Ctrl+C on the
    # console), same clean-shutdown sequence either way.
    _stop_app_services()
