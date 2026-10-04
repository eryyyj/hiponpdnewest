#!/usr/bin/env python3
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)

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
    print("[Camera] cv2 unavailable:")
    traceback.print_exc()
    CV2_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except Exception:
    print("[Camera] Ultralytics YOLO unavailable:")
    traceback.print_exc()
    YOLO = None
    YOLO_AVAILABLE = False

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except Exception:
    print("[Camera] picamera2 unavailable:")
    traceback.print_exc()
    PICAMERA2_AVAILABLE = False


class PiCamCapture:
    def __init__(self, size=(640, 480), buffer_count=3):
        if not PICAMERA2_AVAILABLE:
            raise RuntimeError("picamera2 is not available")
        self.picam2 = Picamera2()
        self.picam2.configure(self.picam2.create_video_configuration(
            main={"size": size, "format": "RGB888"},
            buffer_count=buffer_count))
        self.picam2.start()
        self._open = True

    def isOpened(self):
        return self._open

    def read(self):
        if not self._open:
            return False, None
        try:
            return True, self.picam2.capture_array()
        except Exception:
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


CAMERA_RESOLUTION = (640, 640)
SNAPSHOT_DIR = os.path.expanduser("~/esp32_snapshots")

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
YOLO_WEIGHTS_PATH = os.path.join(_PROJECT_ROOT, "models", "best.pt")
YOLO_TRACKER_PATH = os.path.join(_PROJECT_ROOT, "models", "shrimp_bytetrack.yaml")
YOLO_LABELS_PATH = os.path.join(_PROJECT_ROOT, "models", "labels.txt")

MODEL_EXPECTS_SWAPPED_RB = True

DETECTION_THRESHOLD = 0.437
DETECTION_IOU = 0.80
DETECTION_MAX_DETECTIONS = 100
BURST_FRAME_COUNT = 8
BURST_INTERVAL_S = 0.25
BURST_GALLERY_COUNT = 3
MISSING_ID_IOU = 0.50

CAMERA_BUFFER_COUNT = 3
STREAM_JPEG_QUALITY = 70

CAMERA_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "camera_defaults.json"
)

DEFAULT_ROI = {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
ROI_MIN_SIZE = 0.05
ROI_COLOR = (241, 105, 31)

DETECTION_BOX_COLOR = (0, 255, 0)
DETECTION_CENTROID_COLOR = (216, 43, 39)
DETECTION_LABEL_COLOR = (255, 255, 255)
DETECTED_COUNT_TEXT_COLOR = (0, 0, 0)

AUTOMATION_DEFAULT_STATE = [
    {"device": "servo1", "action": "close"},
    {"device": "servo2", "action": "close"},
    {"device": "relay1", "action": "off"},
    {"device": "relay2", "action": "off"},
]

BAUD_RATE = 115200
MAX_LOG_LINES = 300
WEB_PORT = 5000
SERIAL_WRITE_TIMEOUT = 0.5

AUTO_CONNECT_PORT = "/dev/ttyUSB0"
SERIAL_AUTO_CONNECT_INTERVAL = 1.0
_USB_SERIAL_HINTS = ("ttyusb", "ttyacm", "usbserial", "usbmodem", "cu.usb")

SERVO1_OPEN_DEG = 100
SERVO1_CLOSE_DEG = 180

SERVO2_OPEN_DEG = 0
SERVO2_CLOSE_DEG = 140

SPLASH_IMAGE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "ShrimpSenseLogo.png"
)
SPLASH_DURATION_MS = 2500
SPLASH_BG_COLOR = "white"

KIOSK_BROWSER_CANDIDATES = [
    "chromium-browser",
    "chromium",
    "google-chrome",
    "google-chrome-stable",
]

PAGE_STYLE = """
<style>
  :root {
    --shrimp-red: #D82B27;
    --shrimp-orange: #F1691F;
    --marine-dark: #111827;
    --marine-light: #F4F8FA;
  }

  body {
    font-family: 'Lato', sans-serif;
    background-color: var(--marine-light);
    color: #111827;
  }
  .content-wrapper {
    background-color: var(--marine-light);
    position: relative;
  }
  .wrapper { background-color: var(--marine-light); }

  .text-marine { color: #111827 !important; }
  .text-shrimp { color: #111827 !important; }

  .btn-shrimp-primary {
    background-color: var(--shrimp-red);
    border-color: var(--shrimp-red);
    color: #fff;
  }
  .btn-shrimp-primary:hover, .btn-shrimp-primary:focus {
    background-color: #B71E1A;
    border-color: #B71E1A;
    color: #fff;
  }
  .btn-shrimp-accent {
    background-color: var(--shrimp-orange);
    border-color: var(--shrimp-orange);
    color: #fff;
  }
  .btn-shrimp-accent:hover, .btn-shrimp-accent:focus {
    background-color: #D35400;
    border-color: #D35400;
    color: #fff;
  }
  .btn-outline-marine {
    color: #111827;
    border-color: #111827;
  }
  .btn-outline-marine:hover {
    background-color: #111827;
    color: #fff;
  }

  .process-stage-container {
    background: #ffffff;
    border-radius: 10px;
    min-height: 280px;
    width: 100%;
    padding: 24px;
    box-shadow: inset 0 0 10px rgba(0,0,0,0.02);
  }
  .process-text-headline {
    font-size: 2.1rem;
    color: #111827;
    letter-spacing: 0.5px;
  }
  .process-text-sub {
    font-size: 1.25rem;
    color: #111827;
  }

  .metric-card {
    background: #ffffff;
    border-color: #E2E8F0 !important;
  }
  .metric-label {
    font-size: 11px;
    letter-spacing: 0.5px;
    color: #111827;
  }
  .metric-val {
    font-size: 2rem;
    line-height: 1.1;
    color: #111827;
  }
  .metric-val-sm {
    font-size: 1.45rem;
    line-height: 1.1;
    color: #111827;
  }

  .gallery-item { cursor: pointer; }
  .gallery-item img { width: 100%; height: 120px; object-fit: cover; border-radius: 4px; }
  .gallery-item .caption { font-size: 11px; color: #111827; margin-top: 2px; }

  .lightbox {
    position: fixed; inset: 0; background: rgba(0,0,0,0.9);
    display: flex; align-items: center; justify-content: center; z-index: 1050;
  }
  .lightbox.hidden { display: none; }
  .lightbox img { max-width: 92%; max-height: 82%; border-radius: 6px; }
  .lightbox .lightbox-close { position: absolute; top: 16px; right: 24px; font-size: 32px; color: #fff; cursor: pointer; }
  .lightbox .lightbox-caption { position: absolute; bottom: 24px; left: 0; right: 0; text-align: center; color: #ddd; font-size: 12px; }

  #captureToast {
    position: fixed; top: 70px; left: 50%; transform: translateX(-50%);
    z-index: 1060; opacity: 0; transition: opacity 0.3s; pointer-events: none;
  }
  #captureToast.show { opacity: 1; }

  .status-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 5px; background: #dc3545; }
  .status-dot.on { background: #28a745; }

  #shrimpTargetModal, #powerModal, #calibrationModal, #roiModal, #manualFeedModal, #secretFeedModal {
    display: none; position: fixed; inset: 0; z-index: 1080;
    background: rgba(17, 24, 39, 0.6); align-items: center; justify-content: center;
  }
  #shrimpTargetModal.show, #powerModal.show, #calibrationModal.show, #roiModal.show, #manualFeedModal.show, #secretFeedModal.show {
    display: flex !important;
  }
  #shrimpTargetModal .modal-dialog, #powerModal .modal-dialog, #calibrationModal .modal-dialog, #roiModal .modal-dialog, #manualFeedModal .modal-dialog {
    margin: 0; max-width: 440px; width: 94%;
  }

  .roi-preview { position: relative; width: 100%; background: #111; border-radius: 4px; overflow: hidden; margin-bottom: 10px; }
  .roi-preview img { display: block; width: 100%; height: auto; }
  .roi-box { position: absolute; border: 3px solid var(--shrimp-orange); box-shadow: 0 0 0 9999px rgba(0,0,0,0.45); pointer-events: none; }
  .roi-slider-label { display: flex; justify-content: space-between; font-weight: 700; margin-top: 4px; }

  #osk {
    display: none; position: fixed; left: 0; right: 0; bottom: 0; z-index: 2000;
    background: #111827; padding: 10px 12px 14px; box-shadow: 0 -6px 18px rgba(0,0,0,0.35);
  }
  #osk.show { display: block; }
  #osk .osk-keys { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; max-width: 420px; margin: 0 auto; }
  #osk .osk-wide { grid-column: span 2; }
  #osk button {
    min-height: 48px; font-size: 22px; font-weight: 700; border: 0; border-radius: 8px;
    background: #2C3E50; color: #fff;
  }
  #osk button.osk-action { background: #566573; }
  #osk button.osk-ok { background: var(--shrimp-red); }
</style>
"""

NAV_TABS = [
    ("controls", "/controls", "Controls"),
    ("gallery", "/gallery", "Gallery"),
]


def render_nav_links(active):
    dashboard_active = "active font-weight-bold text-dark" if active == "camera" else "text-dark"
    brand_tab = f"""
    <li class="nav-item mr-3">
      <a class="nav-link d-flex align-items-center {dashboard_active}" href="/" id="secretFeedToggle" title="Double click for developer feed">
        <img src="/assets/ShrimpSenseLogo.png" alt="ShrimpSense" onerror="this.src='/assets/images/ShrimpSenseLogo.png'" style="height: 32px; width: auto;" class="mr-2">
        <strong style="font-size:1.15rem;">ShrimpSense Dashboard</strong>
      </a>
    </li>
    """
    
    links = [brand_tab]
    for key, href, label in NAV_TABS:
        cls = "nav-link active font-weight-bold text-dark" if key == active else "nav-link font-weight-bold text-muted"
        links.append(f'<li class="nav-item"><a class="{cls}" href="{href}">{label}</a></li>')
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
}
function closePowerModal(){
  if (!powerModal) return;
  powerModal.classList.remove('show');
}
async function requestPowerAction(url, failLabel){
  closePowerModal();
  try{
    const res = await fetch(url, {method:'POST'});
    const data = await res.json();
    if (!data.ok) alert(failLabel + ': ' + (data.error || 'failed'));
  } catch(e){}
}
if (document.getElementById('powerModalClose')) document.getElementById('powerModalClose').addEventListener('click', closePowerModal);
if (document.getElementById('powerModalCancel')) document.getElementById('powerModalCancel').addEventListener('click', closePowerModal);
if (powerModal) powerModal.addEventListener('click', (e) => { if (e.target === powerModal) closePowerModal(); });

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
}
function closeCalibrationModal(){
  if (!calibrationModal) return;
  calibrationModal.classList.remove('show');
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
if (document.getElementById('calibrationModalClose')) document.getElementById('calibrationModalClose').addEventListener('click', closeCalibrationModal);
if (document.getElementById('calibrationModalCancel')) document.getElementById('calibrationModalCancel').addEventListener('click', closeCalibrationModal);
if (calibrationModal) calibrationModal.addEventListener('click', (e) => { if (e.target === calibrationModal) closeCalibrationModal(); });

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

const DEVICE_LABELS = { relay1:'Pump', relay2:'Feeder', servo1:'Gate 1', servo2:'Gate 2' };
let automationRunning = false;

const shrimpTargetModal = document.getElementById('shrimpTargetModal');
const shrimpTargetInput = document.getElementById('shrimpTargetInput');

function openShrimpTargetModal(){
  if (!shrimpTargetModal) return;
  shrimpTargetInput.value = '';
  shrimpTargetModal.classList.add('show');
  setTimeout(() => shrimpTargetInput.focus(), 50);
}

function closeShrimpTargetModal(){
  if (!shrimpTargetModal) return;
  shrimpTargetModal.classList.remove('show');
}

if (document.getElementById('shrimpModalClose')) document.getElementById('shrimpModalClose').addEventListener('click', closeShrimpTargetModal);
if (document.getElementById('shrimpModalCancel')) document.getElementById('shrimpModalCancel').addEventListener('click', closeShrimpTargetModal);
if (shrimpTargetModal) shrimpTargetModal.addEventListener('click', (e) => { if (e.target === shrimpTargetModal) closeShrimpTargetModal(); });

if (document.getElementById('shrimpModalSubmit')) {
  document.getElementById('shrimpModalSubmit').addEventListener('click', async () => {
    const value = parseInt(shrimpTargetInput.value, 10);
    if (!value || value <= 0){
      alert('Enter a valid total number of shrimp (greater than 0).');
      return;
    }
    closeShrimpTargetModal();
    try{
      await fetch('/api/automation/start', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({target_count: value})
      });
    } catch(e){}
  });
}

if (shrimpTargetInput) {
  shrimpTargetInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') document.getElementById('shrimpModalSubmit').click();
  });
}

// ROI Editor
const roiModal = document.getElementById('roiModal');
const roiSliders = {
  left: document.getElementById('roiLeft'),
  right: document.getElementById('roiRight'),
  top: document.getElementById('roiTop'),
  bottom: document.getElementById('roiBottom'),
};

function roiClamp(changed){
  const L = roiSliders.left, R = roiSliders.right, T = roiSliders.top, B = roiSliders.bottom;
  const maxSum = 95;
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
  if (box){
    box.style.left = l + '%';
    box.style.top = t + '%';
    box.style.width = (100 - l - r) + '%';
    box.style.height = (100 - t - b) + '%';
  }
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
}

function closeRoiModal(){
  if (!roiModal) return;
  roiModal.classList.remove('show');
  if (roiPreviewTimer){ clearInterval(roiPreviewTimer); roiPreviewTimer = null; }
  const preview = document.getElementById('roiPreviewImg');
  if (preview) preview.src = '';
  if (typeof hideOsk === 'function') hideOsk();
}

if (roiModal){
  Object.keys(roiSliders).forEach((side) => {
    if (roiSliders[side]) roiSliders[side].addEventListener('input', () => { roiClamp(side); roiRender(); });
  });
  if (document.getElementById('roiBtn')) document.getElementById('roiBtn').addEventListener('click', openRoiModal);
  if (document.getElementById('roiModalClose')) document.getElementById('roiModalClose').addEventListener('click', closeRoiModal);
  if (document.getElementById('roiModalCancel')) document.getElementById('roiModalCancel').addEventListener('click', closeRoiModal);
  roiModal.addEventListener('click', (e) => { if (e.target === roiModal) closeRoiModal(); });
  if (document.getElementById('roiResetBtn')){
    document.getElementById('roiResetBtn').addEventListener('click', async () => {
      try{ roiApply(await (await fetch('/api/roi/reset', {method:'POST'})).json()); } catch(e){}
    });
  }
  if (document.getElementById('roiSaveBtn')){
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
}

// Touch Numpad
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

if (osk){
  osk.addEventListener('mousedown', (e) => e.preventDefault());
  osk.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-osk]');
    if (!btn) return;
    oskType(btn.getAttribute('data-osk'));
  });
}

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
new MutationObserver(bindOskInputs).observe(document.body, {childList:true, subtree:true});
document.addEventListener('click', (e) => {
  if (!osk || !osk.classList.contains('show')) return;
  if (e.target.closest('#osk')) return;
  if (e.target.closest('input')) return;
  hideOsk();
});

refreshPorts();
refreshStatus();
loadCalibration();
setInterval(() => { refreshPorts(); refreshStatus(); }, 2000);
"""


def render_page(active, body, page_script, extra_body="", full_height=False):
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Cache-Control" content="no-store">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>ShrimpSense</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lato:wght@400;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/admin-lte@3.2.0/dist/css/adminlte.min.css">
{PAGE_STYLE}
</head>
<body class="hold-transition layout-top-nav">
<div class="wrapper">

  <nav class="main-header navbar navbar-expand navbar-white navbar-light border-bottom px-2 shadow-sm">
    <div class="container-fluid">
      <ul class="navbar-nav align-items-center">
        {render_nav_links(active)}
        <li class="nav-item ml-2">
          <button id="calibrationBtn" class="btn btn-outline-secondary btn-sm mr-1 font-weight-bold text-dark">Calibration</button>
          <button id="roiBtn" class="btn btn-outline-secondary btn-sm font-weight-bold text-dark">ROI</button>
        </li>
      </ul>

      <ul class="navbar-nav ml-auto align-items-center flex-nowrap">
        <li class="nav-item px-1">
          <select id="portSelect" class="custom-select custom-select-sm text-dark font-weight-bold" style="width:auto;"></select>
        </li>
        <li class="nav-item px-1">
          <button id="refreshBtn" class="btn btn-sm btn-outline-secondary text-dark font-weight-bold" title="Refresh ports">&#8635;</button>
        </li>
        <li class="nav-item px-1">
          <button id="connectBtn" class="btn btn-sm btn-success font-weight-bold">Connect</button>
        </li>
        <li class="nav-item px-2 d-flex align-items-center">
          <span id="statusDot" class="status-dot"></span>
          <small id="statusText" class="text-dark font-weight-bold d-none d-md-inline">Disconnected</small>
        </li>
        <li class="nav-item px-1">
          <button id="shutdownBtn" class="btn btn-sm btn-outline-danger font-weight-bold" title="Power">&#9211; Power</button>
        </li>
      </ul>
    </div>
  </nav>

  <div class="content-wrapper">
    <div class="content pt-2 pb-3">
      <div class="container-fluid">
{body}
      </div>
    </div>
  </div>

</div>

<!-- Calibration Modal -->
<div class="modal" id="calibrationModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content shadow border-0" style="border-radius:12px;">
      <div class="modal-header border-bottom">
        <h5 class="modal-title font-weight-bold text-dark">System Calibration</h5>
        <button type="button" class="close" id="calibrationModalClose" aria-label="Close"><span>&times;</span></button>
      </div>
      <div class="modal-body">
        <label for="calibConfidence" class="text-dark font-weight-bold">Detection Confidence</label>
        <input id="calibConfidence" type="text" class="form-control mb-2 text-dark font-weight-bold" placeholder="0.437">
        <label for="calibFeederMultiplier" class="text-dark font-weight-bold">Feeder Multiplier</label>
        <input id="calibFeederMultiplier" type="text" class="form-control mb-2 text-dark font-weight-bold" placeholder="0.15">
        <label for="calibShrimpWeight" class="text-dark font-weight-bold">Single Shrimp Weight (g)</label>
        <input id="calibShrimpWeight" type="text" class="form-control mb-2 text-dark font-weight-bold" placeholder="0.00333">
        <label for="calibFeederPulse" class="text-dark font-weight-bold">Feeder Pulse Duration (s)</label>
        <input id="calibFeederPulse" type="text" class="form-control mb-2 text-dark font-weight-bold" placeholder="5">
        <label for="calibFlushPump" class="text-dark font-weight-bold">Flush Duration (s)</label>
        <input id="calibFlushPump" type="text" class="form-control mb-2 text-dark font-weight-bold" placeholder="10">
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary font-weight-bold" id="calibrationModalCancel">Cancel</button>
        <button type="button" class="btn btn-shrimp-primary font-weight-bold px-3" id="calibrationModalSave">Save</button>
      </div>
    </div>
  </div>
</div>

<!-- ROI Modal -->
<div class="modal" id="roiModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content shadow border-0" style="border-radius:12px;">
      <div class="modal-header border-bottom">
        <h5 class="modal-title font-weight-bold text-dark">Region of Interest (ROI)</h5>
        <button type="button" class="close" id="roiModalClose" aria-label="Close"><span>&times;</span></button>
      </div>
      <div class="modal-body">
        <div class="roi-preview">
          <img id="roiPreviewImg" alt="Camera preview">
          <div class="roi-box" id="roiBox"></div>
        </div>
        <div class="roi-slider-label text-dark font-weight-bold"><span>Left</span><span id="roiLeftVal">0%</span></div>
        <input type="range" id="roiLeft" min="0" max="95" step="1" value="0" class="custom-range">
        <div class="roi-slider-label text-dark font-weight-bold"><span>Right</span><span id="roiRightVal">0%</span></div>
        <input type="range" id="roiRight" min="0" max="95" step="1" value="0" class="custom-range">
        <div class="roi-slider-label text-dark font-weight-bold"><span>Top</span><span id="roiTopVal">0%</span></div>
        <input type="range" id="roiTop" min="0" max="95" step="1" value="0" class="custom-range">
        <div class="roi-slider-label text-dark font-weight-bold"><span>Bottom</span><span id="roiBottomVal">0%</span></div>
        <input type="range" id="roiBottom" min="0" max="95" step="1" value="0" class="custom-range">
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline-secondary mr-auto font-weight-bold text-dark" id="roiResetBtn">Reset</button>
        <button type="button" class="btn btn-secondary font-weight-bold" id="roiModalCancel">Cancel</button>
        <button type="button" class="btn btn-shrimp-primary font-weight-bold px-3" id="roiSaveBtn">Save</button>
      </div>
    </div>
  </div>
</div>

<!-- Power Modal -->
<div class="modal" id="powerModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content shadow border-0" style="border-radius:12px;">
      <div class="modal-header border-bottom">
        <h5 class="modal-title font-weight-bold text-dark">System Power</h5>
        <button type="button" class="close" id="powerModalClose" aria-label="Close"><span>&times;</span></button>
      </div>
      <div class="modal-body">
        <p class="text-dark font-weight-bold mb-3">Choose system action:</p>
        <button type="button" id="powerExitAppBtn" class="btn btn-secondary btn-block font-weight-bold py-2 mb-2">Exit Desktop App</button>
        <button type="button" id="powerShutdownPiBtn" class="btn btn-danger btn-block font-weight-bold py-2 mb-2">Shutdown Raspberry Pi</button>
        <button type="button" id="powerModalCancel" class="btn btn-outline-secondary btn-block font-weight-bold">Cancel</button>
      </div>
    </div>
  </div>
</div>

<!-- Target PL Count Modal -->
<div class="modal" id="shrimpTargetModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content shadow border-0" style="border-radius:12px;">
      <div class="modal-header border-bottom">
        <h5 class="modal-title font-weight-bold text-dark">Target PL Shrimp Count</h5>
        <button type="button" class="close" id="shrimpModalClose" aria-label="Close"><span>&times;</span></button>
      </div>
      <div class="modal-body">
        <label for="shrimpTargetInput" class="font-weight-bold text-dark">Set Target Count</label>
        <input type="number" min="1" step="1" class="form-control form-control-lg text-center font-weight-bold text-dark" id="shrimpTargetInput" placeholder="e.g. 500">
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary font-weight-bold" id="shrimpModalCancel">Cancel</button>
        <button type="button" class="btn btn-shrimp-primary font-weight-bold px-4" id="shrimpModalSubmit">Confirm &amp; Start</button>
      </div>
    </div>
  </div>
</div>

{extra_body}

<!-- Touch Numpad -->
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
# Serial Manager
# ---------------------------------------------------------------------------
class SerialManager:
    def __init__(self):
        self.ser = None
        self.port_name = None
        self.read_thread = None
        self.write_thread = None
        self.stop_flag = threading.Event()
        self.log = []
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
            time.sleep(2)
            self.stop_flag.clear()
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
                    self.disconnect()
                return

            if self.ser is not None or self.port_name is not None:
                self.disconnect()

            for port in self._candidate_ports(ports):
                if port in self._skip_ports:
                    continue
                try:
                    self.connect(port)
                    return
                except Exception as exc:
                    self._add_log("sys", f"Auto-connect to {port} failed: {exc}")

    def is_connected(self):
        return self.ser is not None and self.ser.is_open

    def send(self, command):
        if not self.is_connected():
            raise RuntimeError("Not connected to serial port.")
        self.write_queue.put(command.strip())

    def _write_loop(self):
        while not self.stop_flag.is_set():
            try:
                command = self.write_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if command is None:
                continue
            line = command + "\n"
            try:
                if self.ser is not None:
                    self.ser.write(line.encode("utf-8"))
                    self._add_log("out", command)
            except serial.SerialTimeoutException:
                self._add_log("sys", f"Write timed out: {command}")
            except (OSError, serial.SerialException) as exc:
                self._add_log("sys", f"Write failed: {exc}")

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

DEVICE_LABELS = {
    "relay1": "Pump",
    "relay2": "Feeder",
    "servo1": "Gate 1",
    "servo2": "Gate 2",
}


def _device_command(device, action):
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


PRESET_AUTOMATION_STEPS = [
    {"device": "servo1", "action": "open",  "duration": 0},
    {"device": "relay1", "action": "on",    "duration": 7},
    {"device": "relay1", "action": "off",   "duration": 0},
    {"device": "servo1", "action": "close", "duration": 0, "capture": True},
    {"device": "servo2", "action": "open",  "duration": 3},
    {"device": "servo2", "action": "close", "duration": 0},
]

DEFAULT_FEEDER_SECONDS = 5.0
AUTOMATION_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "automation_defaults.json"
)

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
            return False, "Invalid payload"
        try:
            confidence = float(data.get("confidence", self.get_confidence()))
            multiplier = float(data.get("feeder_multiplier", self.get_feeder_multiplier()))
            shrimp_weight = float(data.get("shrimp_weight_g", self.get_shrimp_weight_g()))
            pulse = float(data.get("feeder_pulse_seconds", self.get_feeder_pulse_seconds()))
            flush_pump = float(data.get("flush_pump_seconds", self.get_flush_pump_seconds()))
        except (TypeError, ValueError):
            return False, "All values must be numbers"
        if not 0.01 <= confidence <= 0.99:
            return False, "Confidence must be 0.01 - 0.99"
        if multiplier <= 0 or shrimp_weight <= 0:
            return False, "Weights/multipliers must be > 0"
        if pulse < 0 or flush_pump < 0:
            return False, "Durations must be >= 0"
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
        except OSError:
            pass


calibration_mgr = CalibrationSettings()


class AutomationManager:
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
                for step, duration in zip(self._steps, cleaned):
                    step["duration"] = duration
            except (TypeError, ValueError):
                pass
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
        except OSError:
            pass

    def get_target_count(self):
        with self._lock:
            return self._target_count if self._running else None

    def _set_default_state(self):
        for item in AUTOMATION_DEFAULT_STATE:
            self._send(item["device"], item["action"])
        time.sleep(0.5)

    def get_steps(self):
        return [dict(s) for s in self._steps]

    def set_durations(self, durations, feeder_seconds=None):
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
        with self._lock:
            completed_count = self._last_completed_count
            completed_feed_grams = (
                round(
                    completed_count
                    * calibration_mgr.get_shrimp_weight_g()
                    * calibration_mgr.get_feeder_multiplier(),
                    5,
                )
                if completed_count is not None else None
            )
            return {
                "running": self._running,
                "steps": [dict(s) for s in self._steps],
                "current_index": self._current_index,
                "seconds_left": self._seconds_left,
                "target_count": self._target_count,
                "just_completed": self._just_completed,
                "completed_count": completed_count,
                "completed_target": self._last_target_count,
                "completed_feed_grams": completed_feed_grams,
                "feeder_seconds": self._feeder_seconds,
            }

    def get_last_completed_count(self):
        with self._lock:
            return self._last_completed_count

    def start(self, target_count=None):
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._target_count = target_count
            self._just_completed = False
            self._stop_event.clear()

        camera_mgr.reset_shrimp_count()
        self._set_default_state()

        with self._lock:
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
            self._target_count = None

        self._set_default_state()
        return not already_idle

    def _send(self, device, action):
        command = _device_command(device, action)
        if command is None:
            return
        try:
            serial_mgr.send(command)
        except Exception:
            pass

    def _target_reached(self):
        with self._lock:
            target = self._target_count
        return target is not None and camera_mgr.get_shrimp_count() >= target

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
                self._target_count = None


automation_mgr = AutomationManager()

HX_WEIGHT_PATTERN = re.compile(r"HX:STREAM:WEIGHT:?\s*([-+]?[0-9]*\.?[0-9]+)", re.IGNORECASE)
WEIGHT_LINE_PATTERN = re.compile(r"^\s*([-+]?\d+\.\d+)\s*$")


def parse_serial_weight(text):
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
        5,
    )


class FeedDispenseManager:
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
            self._tare_offset = 0.0
            self._message = "Zeroing scale..."
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
            self._target_grams = None
        return not already_idle

    def _set_state(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key if key.startswith("_") else f"_{key}", value)

    def _send(self, command):
        try:
            serial_mgr.send(command)
            return True
        except Exception:
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
        return round(float(raw) - self._tare_offset, 5)

    def _establish_tare(self):
        self._set_state(_phase="waiting_zero", _message="Stabilizing tare...")
        samples = []
        started = time.time()
        since_id = serial_mgr.get_latest_log_id()
        deadline = started + FEED_ZERO_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self._stop_event.is_set():
                return False
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
                self._set_state(_current_weight=weight)

            now = time.time()
            elapsed = now - started
            if elapsed >= FEED_TARE_SECONDS and len(samples) >= FEED_TARE_MIN_SAMPLES:
                window = samples[-20:] if len(samples) > 20 else samples
                offset = sum(window) / len(window)
                if abs(offset) <= FEED_ZERO_TOLERANCE:
                    offset = 0.0
                self._tare_offset = offset
                self._set_state(_tare_offset=offset, _current_weight=0.0, _message="Scale zeroed")
                return True

            if self._stop_event.wait(0.1):
                return False
        self._set_state(_phase="error", _message="Tare timeout")
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
                self._set_state(_phase="error", _message="Scale detection failed")
                return

            if not self._establish_tare():
                return

            while not self._stop_event.is_set():
                with self._lock:
                    self._cycle += 1
                    self._phase = "dispensing"
                    self._message = f"Dispense pulse {self._cycle}"

                if not self._dispense(calibration_mgr.get_feeder_pulse_seconds()):
                    return

                with self._lock:
                    self._phase = "weighing"
                    self._message = "Weighing"

                if not self._watch_weight(FEED_WEIGH_SECONDS):
                    return

                if self._weight_reached():
                    with self._lock:
                        self._phase = "done"
                        self._message = f"Complete: {self._current_weight:.3f} g"
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
# Flush Manager
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
        except Exception:
            pass

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
# Camera Manager
# ---------------------------------------------------------------------------
class CameraManager:
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
        if not CV2_AVAILABLE or not PICAMERA2_AVAILABLE:
            return False
        try:
            self._setup_camera()
            self._setup_yolo()
            self.available = True
            return True
        except Exception:
            self.available = False
            return False

    def _setup_camera(self):
        self.camera_cap = PiCamCapture(size=CAMERA_RESOLUTION, buffer_count=CAMERA_BUFFER_COUNT)
        if not self.camera_cap.isOpened():
            raise RuntimeError("Picamera2 capture error")

    def _setup_yolo(self):
        if os.path.isfile(YOLO_LABELS_PATH):
            with open(YOLO_LABELS_PATH, "r", encoding="utf-8") as fh:
                self.labels = [line.strip() for line in fh if line.strip()] or ["shrimp"]
        if not YOLO_AVAILABLE or not os.path.isfile(YOLO_WEIGHTS_PATH):
            return
        self.yolo_model = YOLO(YOLO_WEIGHTS_PATH)

    def is_bursting(self):
        with self._burst_lock:
            return self._burst_running

    def live_feed_enabled(self):
        with self._live_lock:
            return self._live_feed_enabled

    def set_live_feed(self, enabled):
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
        if not self.available or self.is_bursting():
            return False
        frame = self._grab_bgr()
        if frame is None:
            return False
        self._draw_roi_only(frame)
        latest_frame.set(self._to_pil(frame))
        return True

    def begin_detection_cycle(self):
        with self._cycle_lock:
            self.peak_detection_count = 0
            self.live_detection_count = 0
        self._fallback_id = 10000
        if self.yolo_model is not None:
            self.yolo_model.predictor = None

    def capture_count_burst(self, stop_event=None):
        with self._burst_lock:
            self._burst_running = True
        try:
            if self.yolo_model is None:
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
            return True
        except Exception:
            return True
        finally:
            with self._burst_lock:
                self._burst_running = False

    def _track_frame(self, frame_bgr):
        tracker = YOLO_TRACKER_PATH if os.path.isfile(YOLO_TRACKER_PATH) else "bytetrack.yaml"
        model_input = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB) if MODEL_EXPECTS_SWAPPED_RB else frame_bgr
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
        if not results or results[0].boxes is None:
            return dets
        boxes = results[0].boxes
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
        ix1, iy1 = max(ax, bx), max(ay, by)
        ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
        inter = iw * ih
        union = aw * ah + bw * bh - inter
        return 0.0 if union <= 0 else inter / union

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
        for i in sorted(indices)[:BURST_GALLERY_COUNT]:
            count, arr = frames_meta[i]
            try:
                save_snapshot(self._to_pil(arr))
            except Exception:
                pass

    def _draw_roi_only(self, arr):
        height, width = arr.shape[:2]
        rx1, ry1, rx2, ry2 = self._roi_pixels(width, height)
        if (rx1, ry1, rx2, ry2) != (0, 0, width - 1, height - 1):
            cv2.rectangle(arr, (rx1, ry1), (rx2, ry2), self._c(ROI_COLOR), 2)

    def _draw_annotations(self, arr, detections, unique_count):
        self._draw_roi_only(arr)
        for det in detections:
            x, y, w, h = det["box"]
            cx, cy = int(x + w / 2), int(y + h / 2)
            cv2.rectangle(arr, (int(x), int(y)), (int(x + w), int(y + h)), self._c(DETECTION_BOX_COLOR), 2)
            cv2.circle(arr, (cx, cy), 3, self._c(DETECTION_CENTROID_COLOR), -1)
        cv2.putText(arr, f"Detected: {unique_count}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, self._c(DETECTED_COUNT_TEXT_COLOR), 2)

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
        if isinstance(data, dict):
            roi = data.get("roi")
            if isinstance(roi, dict):
                cleaned, _ = self._validate_roi(roi)
                if cleaned is not None:
                    self._roi = cleaned

    def _save_camera_settings(self):
        with self._roi_lock:
            payload = {"roi": dict(self._roi)}
        try:
            with open(CAMERA_SETTINGS_PATH, "w") as f:
                json.dump(payload, f, indent=2)
        except OSError:
            pass

    @staticmethod
    def _validate_roi(data):
        try:
            left = float(data.get("left", 0.0))
            top = float(data.get("top", 0.0))
            right = float(data.get("right", 1.0))
            bottom = float(data.get("bottom", 1.0))
        except (TypeError, ValueError, AttributeError):
            return None, "ROI numbers must be 0 to 1"
        left, top = min(1.0, max(0.0, left)), min(1.0, max(0.0, top))
        right, bottom = min(1.0, max(0.0, right)), min(1.0, max(0.0, bottom))
        if right - left < ROI_MIN_SIZE or bottom - top < ROI_MIN_SIZE:
            return None, "ROI is too small"
        return {"left": round(left, 4), "top": round(top, 4), "right": round(right, 4), "bottom": round(bottom, 4)}, None

    def get_roi_settings(self):
        with self._roi_lock:
            return {"roi": dict(self._roi)}

    def set_roi_settings(self, data):
        if not isinstance(data, dict):
            return False, "Invalid ROI payload"
        with self._roi_lock:
            merged = dict(self._roi)
            merged.update({k: data[k] for k in ("left", "top", "right", "bottom") if k in data})
            roi, err = self._validate_roi(merged)
            if roi is None:
                return False, err
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
        return int(round(roi["left"] * (width - 1))), int(round(roi["top"] * (height - 1))), int(round(roi["right"] * (width - 1))), int(round(roi["bottom"] * (height - 1)))

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
    def __init__(self):
        self._lock = threading.Lock()
        self._image = None
        self._jpeg = None
        self._version = 0

    def set(self, img):
        with self._lock:
            self._image = img
            self._jpeg = None
            self._version += 1

    def get(self):
        with self._lock:
            return self._image

    def get_jpeg(self, quality=STREAM_JPEG_QUALITY):
        with self._lock:
            if self._jpeg is None and self._image is not None:
                self._jpeg = encode_jpeg(self._image, quality=quality)
            return self._jpeg, self._version


latest_frame = LatestFrame()
CAMERA_CAPTURE_FPS = 15


def camera_capture_loop():
    interval = 1.0 / CAMERA_CAPTURE_FPS
    while True:
        if not camera_mgr.available:
            time.sleep(0.5)
            continue
        try:
            if camera_mgr.live_feed_enabled() and not automation_mgr.is_running():
                if not camera_mgr.pump_preview():
                    time.sleep(0.2)
                    continue
        except Exception:
            time.sleep(0.5)
            continue
        time.sleep(interval)


def encode_jpeg(img, quality=85):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def save_snapshot(img):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    base = time.strftime('%Y%m%d_%H%M%S')
    filename = f"snapshot_{base}.jpg"
    suffix = 1
    while os.path.exists(os.path.join(SNAPSHOT_DIR, filename)):
        filename = f"snapshot_{base}_{suffix}.jpg"
        suffix += 1
    img.save(os.path.join(SNAPSHOT_DIR, filename), quality=92)
    return filename


flask_app = Flask(
    __name__,
    static_folder="assets",
    static_url_path="/assets",
)


def _generate_mjpeg():
    interval = 1.0 / 12
    last_version = -1
    while True:
        frame_bytes, version = latest_frame.get_jpeg()
        if frame_bytes is None or version == last_version:
            time.sleep(0.05)
            continue
        last_version = version
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        time.sleep(interval)


@flask_app.route("/video_feed")
def video_feed():
    return Response(_generate_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@flask_app.route("/api/live_feed", methods=["GET"])
def api_live_feed_get():
    return jsonify(camera_mgr.live_feed_status())


@flask_app.route("/api/live_feed", methods=["POST"])
def api_live_feed_set():
    data = request.get_json(silent=True) or {}
    wanted = bool(data.get("enabled")) if "enabled" in data else not camera_mgr.live_feed_enabled()
    enabled = camera_mgr.set_live_feed(wanted)
    return jsonify({"ok": True, "enabled": enabled, **camera_mgr.live_feed_status()})


@flask_app.route("/api/ports", methods=["GET"])
def api_ports():
    return jsonify({"ports": serial_mgr.list_ports()})


@flask_app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({"connected": serial_mgr.is_connected(), "port": serial_mgr.port_name})


@flask_app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    _stop_app_services()
    try:
        subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


@flask_app.route("/api/exit-app", methods=["POST"])
def api_exit_app():
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


@flask_app.route("/api/snapshot", methods=["GET"])
def api_snapshot():
    if not automation_mgr.is_running():
        try:
            camera_mgr.pump_preview()
        except Exception:
            pass
    img = latest_frame.get()
    if img is None:
        return Response(status=503)
    return Response(encode_jpeg(img, quality=85), mimetype="image/jpeg")


@flask_app.route("/api/roi", methods=["GET"])
def api_roi_get():
    return jsonify(camera_mgr.get_roi_settings())


@flask_app.route("/api/roi", methods=["POST"])
def api_roi_set():
    data = request.get_json(silent=True) or {}
    ok, err = camera_mgr.set_roi_settings(data)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, **camera_mgr.get_roi_settings()})


@flask_app.route("/api/roi/reset", methods=["POST"])
def api_roi_reset():
    camera_mgr.reset_roi()
    return jsonify({"ok": True, **camera_mgr.get_roi_settings()})


@flask_app.route("/api/automation", methods=["GET"])
def api_automation_get():
    return jsonify(automation_mgr.get_status())


@flask_app.route("/api/automation/durations", methods=["POST"])
def api_automation_set_durations():
    data = request.get_json(force=True)
    durations = data.get("durations") if isinstance(data, dict) else None
    if not automation_mgr.set_durations(durations):
        return jsonify({"ok": False, "error": "Invalid durations"}), 400
    return jsonify({"ok": True, "steps": automation_mgr.get_steps()})


@flask_app.route("/api/automation/start", methods=["POST"])
def api_automation_start():
    if flush_mgr.is_running():
        return jsonify({"ok": False, "error": "Flush is running"}), 400

    data = request.get_json(silent=True) or {}
    raw_target = data.get("target_count")
    target_count = None
    if raw_target is not None and str(raw_target).strip() != "":
        try:
            target_count = int(raw_target)
            if target_count <= 0:
                return jsonify({"ok": False, "error": "Target count must be greater than 0"}), 400
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Target count must be a number"}), 400

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
    if flush_mgr.is_running():
        return jsonify({"ok": False, "error": "Flush is running"}), 400
    if automation_mgr.is_running():
        return jsonify({"ok": False, "error": "Automation is running"}), 400
    if feed_mgr.is_running():
        return jsonify({"ok": False, "error": "Feeder already running"}), 400

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
        return jsonify({"ok": False, "error": "Enter a shrimp count first"}), 400

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
        return jsonify({"ok": False, "error": "Automation is running"}), 400
    if feed_mgr.is_running():
        return jsonify({"ok": False, "error": "Feed dispensing is running"}), 400

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
    flask_app.run(host="0.0.0.0", port=WEB_PORT, debug=False, threaded=True, use_reloader=False)


def launch_kiosk_browser(url):
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
        print(f"[Kiosk] Launch failed: {exc}")
        shutil.rmtree(profile_dir, ignore_errors=True)
        return None

    process._kiosk_profile_dir = profile_dir
    return process


if __name__ == "__main__":
    camera_mgr.start()
    serial_mgr.start_watcher()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    camera_thread = threading.Thread(target=camera_capture_loop, daemon=True)
    camera_thread.start()

    time.sleep(1.5)

    kiosk_url = f"http://127.0.0.1:{WEB_PORT}/splash"
    _kiosk_process = launch_kiosk_browser(kiosk_url)

    if _kiosk_process is not None:
        try:
            _kiosk_process.wait()
        except KeyboardInterrupt:
            pass
        finally:
            profile_dir = getattr(_kiosk_process, "_kiosk_profile_dir", None)
            if profile_dir:
                shutil.rmtree(profile_dir, ignore_errors=True)
    else:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    _stop_app_services()