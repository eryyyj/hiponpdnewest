#!/usr/bin/env python3
"""
Standalone Flask footage playback + detection tool.

Plays the clips recorded by capture.py (captures/videos/) through your .pt
model with the ultralytics package and shows the annotated result in the
browser. It does NOT touch the camera, so it can run while the camera is free
or busy.

    python playback.py --model best.pt

Open http://<pi-ip>:5002   (or http://127.0.0.1:5002 on the Pi itself)

What you see on the video:
    green boxes   = detections at or above your confidence (these are counted)
    yellow boxes  = near misses (confidence between 0.05 and your threshold)
    top-left text = count in the current frame, near misses, frame number

Things to try if nothing is detected:
    1. Lower the confidence. Yellow boxes appearing means the model sees
       something but is below your threshold.
    2. Tick "Swap red/blue channels". picamera2's RGB888 is really BGR in
       memory, so clips/photos made by capture.py can have red and blue
       swapped. If detection works with the swap on (or off) but not the
       other way, your live pipeline must feed the model the same channel
       order the model works with.
    3. Change the image size to the one you trained/tested with in Colab.
"""

import argparse
import os
import threading
import time
import traceback

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request

ROOT = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(ROOT, "captures", "videos")
VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".m4v")
LOW_CONF_FLOOR = 0.05  # boxes below your conf but above this are drawn yellow
DEFAULT_PORT = 5002

COLOR_HIT = (0, 200, 0)       # BGR green
COLOR_NEAR = (0, 200, 255)    # BGR yellow/orange


def placeholder(text, size=(640, 480)):
    img = np.full((size[1], size[0], 3), 30, dtype=np.uint8)
    cv2.putText(img, text, (20, size[1] // 2), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (220, 220, 220), 2, cv2.LINE_AA)
    return encode_jpeg(img)


def encode_jpeg(img, quality=80):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""


class Player:
    def __init__(self, model, video_dir):
        self.model = model
        self.video_dir = video_dir
        self.lock = threading.Lock()
        self.thread = None
        self.stop_event = threading.Event()
        self.jpeg = placeholder("Select a clip and press Play")
        self.version = 0
        self.stats = self._blank_stats()

    @staticmethod
    def _blank_stats():
        return {
            "running": False, "clip": "", "message": "Idle",
            "frame": 0, "total_frames": 0,
            "count_now": 0, "below_now": 0, "peak": 0,
            "total_dets": 0, "frames_done": 0, "frames_with_det": 0,
            "max_conf": 0.0, "ms": 0.0, "fps": 0.0, "loops": 0,
        }

    def snapshot(self):
        with self.lock:
            s = dict(self.stats)
        s["avg_per_frame"] = round(s["total_dets"] / s["frames_done"], 2) if s["frames_done"] else 0.0
        return s

    def _set(self, **kw):
        with self.lock:
            self.stats.update(kw)

    def start(self, clip, conf, imgsz, swap_rb, loop, stride):
        path = os.path.join(self.video_dir, os.path.basename(clip or ""))
        if not clip or not os.path.isfile(path):
            return "Clip not found"
        self.stop()
        self.stop_event.clear()
        with self.lock:
            self.stats = self._blank_stats()
            self.stats["clip"] = os.path.basename(path)
            self.stats["message"] = "Starting..."
        self.thread = threading.Thread(
            target=self._run, args=(path, conf, imgsz, swap_rb, loop, stride), daemon=True
        )
        self.thread.start()
        return None

    def stop(self):
        self.stop_event.set()
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=10)
        self.thread = None
        self._set(running=False)

    def _publish(self, img):
        self.jpeg = encode_jpeg(img)
        self.version += 1

    def _annotate(self, frame, res, conf, idx, total):
        out = frame.copy()
        n_hit = n_near = 0
        best = 0.0
        names = getattr(res, "names", {}) or {}
        if res.boxes is not None and len(res.boxes):
            xyxy = res.boxes.xyxy.cpu().numpy()
            confs = res.boxes.conf.cpu().numpy()
            clss = res.boxes.cls.cpu().numpy().astype(int)
            for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clss):
                p1, p2 = (int(x1), int(y1)), (int(x2), int(y2))
                if c >= conf:
                    n_hit += 1
                    best = max(best, float(c))
                    cv2.rectangle(out, p1, p2, COLOR_HIT, 2)
                    label = f"{names.get(int(k), int(k))} {c:.2f}"
                    cv2.putText(out, label, (p1[0], max(12, p1[1] - 4)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_HIT, 1, cv2.LINE_AA)
                else:
                    n_near += 1
                    cv2.rectangle(out, p1, p2, COLOR_NEAR, 1)
        text = f"count: {n_hit}   near-miss: {n_near}   frame {idx}/{total if total > 0 else '?'}"
        cv2.rectangle(out, (0, 0), (out.shape[1], 24), (0, 0, 0), -1)
        cv2.putText(out, text, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (255, 255, 255), 1, cv2.LINE_AA)
        return out, n_hit, n_near, best

    def _run(self, path, conf, imgsz, swap_rb, loop, stride):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            self._set(running=False, message="Could not open clip (codec problem?)")
            return
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._set(running=True, total_frames=total, message="Playing")
        floor = min(conf, LOW_CONF_FLOOR)
        ema_ms = None
        idx = 0
        read_this_pass = 0
        try:
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    if loop and read_this_pass > 0:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        read_this_pass = 0
                        with self.lock:
                            self.stats["loops"] += 1
                        continue
                    break
                read_this_pass += 1
                idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                for _ in range(max(0, stride - 1)):
                    cap.grab()

                if swap_rb:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                t0 = time.time()
                res = self.model.predict(frame, conf=floor, imgsz=imgsz, verbose=False)[0]
                ms = (time.time() - t0) * 1000.0
                ema_ms = ms if ema_ms is None else 0.9 * ema_ms + 0.1 * ms

                out, n_hit, n_near, best = self._annotate(frame, res, conf, idx, total)
                self._publish(out)

                with self.lock:
                    s = self.stats
                    s["frame"] = idx
                    s["count_now"] = n_hit
                    s["below_now"] = n_near
                    s["peak"] = max(s["peak"], n_hit)
                    s["total_dets"] += n_hit
                    s["frames_done"] += 1
                    if n_hit:
                        s["frames_with_det"] += 1
                    s["max_conf"] = max(s["max_conf"], best)
                    s["ms"] = round(ema_ms, 1)
                    s["fps"] = round(1000.0 / ema_ms, 1) if ema_ms else 0.0
        except Exception as exc:
            traceback.print_exc()
            self._set(message=f"Error: {exc}")
        finally:
            cap.release()
            with self.lock:
                self.stats["running"] = False
                if self.stats["message"] == "Playing":
                    self.stats["message"] = "Stopped" if self.stop_event.is_set() else "Finished"


app = Flask(__name__)
player = None  # created in main()
DEFAULTS = {"conf": 0.25, "imgsz": 640}

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Footage playback</title>
<style>
  body { font-family: Lato, Arial, sans-serif; margin: 0; background: #f4f6f9; color: #222; }
  .wrap { max-width: 820px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 1.4rem; margin: 0 0 12px; }
  .feed { background: #000; border-radius: 8px; overflow: hidden; text-align: center; }
  .feed img { width: 100%; max-width: 640px; height: auto; display: block; margin: 0 auto; }
  .panel { background: #fff; border: 1px solid #dee2e6; border-radius: 8px; padding: 14px; margin-top: 12px; }
  label { font-weight: 700; display: block; margin-bottom: 4px; }
  select, input[type=number] { height: 40px; font-size: 1.05rem; padding: 4px 8px; }
  select { width: 100%; max-width: 420px; }
  input[type=number] { width: 110px; }
  button { min-height: 44px; font-size: 1.05rem; font-weight: 700; border: 0; border-radius: 6px; padding: 8px 16px; cursor: pointer; }
  .btn-play { background: #28a745; color: #fff; }
  .btn-stop { background: #dc3545; color: #fff; }
  .btn-alt { background: #e9ecef; color: #222; }
  .row { display: flex; flex-wrap: wrap; gap: 14px; align-items: flex-end; margin-top: 12px; }
  .check { display: flex; align-items: center; gap: 8px; font-weight: 400; margin: 0; }
  .hint { color: #666; font-size: 0.85rem; margin: 2px 0 0 26px; }
  .msg { min-height: 22px; margin-top: 8px; color: #b02a37; }
  .stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 8px; margin-top: 12px; }
  .stat { background: #f4f6f9; border-radius: 6px; padding: 8px 10px; }
  .stat .k { font-size: 0.8rem; color: #666; }
  .stat .v { font-size: 1.15rem; font-weight: 700; }
  .legend { font-size: 0.9rem; color: #555; margin-top: 10px; }
  .dot { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Footage playback &amp; detection</h1>
  <div class="feed"><img id="live" src="/video_feed" alt="Annotated footage"></div>
  <div class="panel">
    <label for="clip">Recorded clip</label>
    <div class="row" style="margin-top:0">
      <select id="clip"></select>
      <button class="btn-alt" id="reloadBtn" type="button">Reload list</button>
    </div>

    <div class="row">
      <div><label for="conf">Confidence</label>
        <input id="conf" type="number" min="0.01" max="1" step="0.05" value="__CONF__"></div>
      <div><label for="imgsz">Image size</label>
        <input id="imgsz" type="number" min="64" max="1920" step="32" value="__IMGSZ__"></div>
      <div><label for="stride">Every Nth frame</label>
        <input id="stride" type="number" min="1" max="30" step="1" value="1"></div>
    </div>

    <div class="row" style="flex-direction:column; align-items:flex-start; gap:6px">
      <label class="check"><input type="checkbox" id="swap"> Swap red/blue channels before the model</label>
      <div class="hint">picamera2 "RGB888" is BGR in memory, so clips from capture.py may have red/blue swapped. Try both.</div>
      <label class="check"><input type="checkbox" id="loop" checked> Loop the clip</label>
    </div>

    <div class="row">
      <button class="btn-play" id="playBtn" type="button">Play</button>
      <button class="btn-stop" id="stopBtn" type="button">Stop</button>
    </div>
    <p class="msg" id="msg"></p>

    <div class="legend">
      <span class="dot" style="background:#00c800"></span>counted (&ge; confidence)
      &nbsp;&nbsp;<span class="dot" style="background:#ffc800"></span>near miss (0.05 to confidence)
    </div>
    <div class="stats" id="stats"></div>
  </div>
</div>
<script>
const $ = id => document.getElementById(id);

async function loadClips(){
  try{
    const data = await (await fetch('/api/clips')).json();
    const sel = $('clip'); const prev = sel.value;
    sel.innerHTML = '';
    (data.clips || []).forEach(n => { const o = document.createElement('option'); o.value = n; o.textContent = n; sel.appendChild(o); });
    if (!sel.options.length){ const o = document.createElement('option'); o.value = ''; o.textContent = '(no clips found)'; sel.appendChild(o); }
    if (prev) sel.value = prev;
  } catch(e){ $('msg').textContent = 'Could not load clip list'; }
}

$('reloadBtn').addEventListener('click', loadClips);

$('playBtn').addEventListener('click', async () => {
  $('msg').textContent = '';
  const body = {
    clip: $('clip').value,
    conf: parseFloat($('conf').value) || 0.25,
    imgsz: parseInt($('imgsz').value, 10) || 640,
    stride: parseInt($('stride').value, 10) || 1,
    swap_rb: $('swap').checked,
    loop: $('loop').checked
  };
  try{
    const data = await (await fetch('/api/play', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)})).json();
    if (!data.ok) $('msg').textContent = data.error || 'Failed';
  } catch(e){ $('msg').textContent = 'Could not start playback'; }
});

$('stopBtn').addEventListener('click', async () => { await fetch('/api/stop', {method:'POST'}); });

function render(s){
  const items = [
    ['State', s.message + (s.running ? '' : '')],
    ['Frame', s.frame + ' / ' + (s.total_frames > 0 ? s.total_frames : '?')],
    ['Shrimp in this frame', s.count_now],
    ['Near misses (this frame)', s.below_now],
    ['Peak in one frame', s.peak],
    ['Frames with detections', s.frames_with_det + ' / ' + s.frames_done],
    ['Average per frame', s.avg_per_frame],
    ['Best confidence seen', s.max_conf ? s.max_conf.toFixed(2) : '-'],
    ['Inference', s.ms ? (s.ms + ' ms  (~' + s.fps + ' FPS)') : '-'],
    ['Loops completed', s.loops]
  ];
  const box = $('stats'); box.innerHTML = '';
  items.forEach(([k, v]) => {
    const d = document.createElement('div'); d.className = 'stat';
    const a = document.createElement('div'); a.className = 'k'; a.textContent = k;
    const b = document.createElement('div'); b.className = 'v'; b.textContent = v;
    d.appendChild(a); d.appendChild(b); box.appendChild(d);
  });
}

async function poll(){
  try{ render(await (await fetch('/api/status')).json()); } catch(e){}
}
loadClips(); poll(); setInterval(poll, 500);
</script>
</body>
</html>
"""


def list_clips(folder):
    if not os.path.isdir(folder):
        return []
    names = [
        n for n in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, n))
        and not n.startswith(".") and n.lower().endswith(VIDEO_EXTS)
    ]
    names.sort(reverse=True)
    return names


@app.route("/")
def index():
    return (PAGE.replace("__CONF__", str(DEFAULTS["conf"]))
                .replace("__IMGSZ__", str(DEFAULTS["imgsz"])))


@app.route("/video_feed")
def video_feed():
    def generate():
        last = -1
        while True:
            if player.version != last:
                last = player.version
                jpeg = player.jpeg
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.03)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/clips")
def api_clips():
    return jsonify({"clips": list_clips(player.video_dir)})


@app.route("/api/play", methods=["POST"])
def api_play():
    data = request.get_json(silent=True) or {}
    try:
        conf = min(1.0, max(0.001, float(data.get("conf", DEFAULTS["conf"]))))
        imgsz = min(1920, max(64, int(data.get("imgsz", DEFAULTS["imgsz"]))))
        stride = min(30, max(1, int(data.get("stride", 1))))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid settings"}), 400
    err = player.start(
        data.get("clip", ""), conf, imgsz,
        bool(data.get("swap_rb", False)), bool(data.get("loop", True)), stride,
    )
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    player.stop()
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    return jsonify(player.snapshot())


def main():
    global player
    ap = argparse.ArgumentParser(description="Play recorded footage through a YOLO .pt model")
    ap.add_argument("--model", default=os.environ.get("SHRIMP_MODEL", "best.pt"), help="path to your .pt model")
    ap.add_argument("--videos", default=VIDEO_DIR, help="folder with recorded clips")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--conf", type=float, default=0.25, help="default confidence threshold")
    ap.add_argument("--imgsz", type=int, default=640, help="default inference image size")
    args = ap.parse_args()

    if not os.path.isfile(args.model):
        raise SystemExit(f"[Playback] Model file not found: {args.model}")

    from ultralytics import YOLO
    import ultralytics
    print(f"[Playback] ultralytics {ultralytics.__version__}")
    model = YOLO(args.model)
    print(f"[Playback] Model: {args.model}")
    print(f"[Playback] Classes: {model.names}")

    DEFAULTS["conf"] = args.conf
    DEFAULTS["imgsz"] = args.imgsz
    os.makedirs(args.videos, exist_ok=True)
    player = Player(model, args.videos)

    print(f"[Playback] Clips  -> {args.videos} ({len(list_clips(args.videos))} found)")
    print(f"[Playback] Open http://127.0.0.1:{args.port}")
    try:
        app.run(host="0.0.0.0", port=args.port, debug=False, threaded=True, use_reloader=False)
    finally:
        if player is not None:
            player.stop()


if __name__ == "__main__":
    main()
