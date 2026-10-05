"""
Camera page (/) - ShrimpSense Aquaculture Dashboard
- Plain white process status display
- Clean all-black metrics: Target PL Shrimp Count, Counted Shrimp, Total Biomass, Recommended Feed
- Dual Run Controls: "Start" (continuous) and "Set Target" (panel target mode)
- "Feed Simulator" modal
- Hidden Developer Live Feed Modal (Double-click ShrimpSense Dashboard brand title in navbar to activate)
"""

from flask import Blueprint, Response

CAMERA_BODY = """
<div class="row" style="margin: 0 -6px;">
  <!-- Left Side: Clean White Status Display & Loop Controls -->
  <div class="col-lg-6 col-md-12 px-1 mb-2">
    <div class="card h-100 shadow-sm border-0" style="border-radius: 12px;">
      <div class="card-body p-3 d-flex flex-column justify-content-between">
        
        <!-- Plain White Process Area -->
        <div class="process-stage-container d-flex flex-column align-items-center justify-content-center border" id="processDisplayArea">
          <div id="processStatusMain" class="process-text-headline text-center font-weight-bold">
            System Ready
          </div>
          <div id="processStatusSub" class="process-text-sub text-center mt-1">
            Waiting for cycle
          </div>
        </div>

        <!-- Automation & Machine Actions -->
        <div class="d-flex justify-content-center flex-wrap mt-3" style="gap:8px;">
          <button id="cameraStartContinuousBtn" class="btn btn-shrimp-primary btn-lg font-weight-bold px-4">
            Start
          </button>
          <button id="cameraSetTargetBtn" class="btn btn-shrimp-accent btn-lg font-weight-bold px-3">
            Set Target
          </button>
          <button id="cameraCancelLoopBtn" class="btn btn-outline-danger btn-lg font-weight-bold px-3">
            Cancel
          </button>
          <button id="cameraFlushBtn" class="btn btn-outline-marine btn-lg font-weight-bold px-3">
            Flush
          </button>
          <button id="btnOpenManualModal" class="btn btn-outline-secondary btn-lg font-weight-bold px-3">
            Feed Simulator
          </button>
        </div>

        <div id="cameraAutomationStatus" class="text-center mt-2" style="min-height:20px; font-size:13px;">
          <span class="text-dark font-weight-bold">Status: Idle</span>
        </div>
        <p id="cameraFlushStatus" class="text-center text-dark mb-0" style="font-size:12px; min-height:16px;">&nbsp;</p>
      </div>
    </div>
  </div>

  <!-- Right Side: Essential Shrimp & Feed Metrics -->
  <div class="col-lg-6 col-md-12 px-1 mb-2">
    <div class="card h-100 shadow-sm border-0" style="border-radius: 12px;">
      <div class="card-body p-3 d-flex flex-column justify-content-between">
        
        <!-- Metric 1: Target PL Shrimp Count -->
        <div class="metric-card mb-2 p-2 rounded border">
          <div class="metric-label text-dark font-weight-bold">TARGET PL SHRIMP COUNT</div>
          <div class="metric-val text-dark font-weight-bold" id="displayTargetCount">None</div>
        </div>

        <!-- Metric 2: Counted Shrimp -->
        <div class="metric-card mb-2 p-2 rounded border">
          <div class="metric-label text-dark font-weight-bold">COUNTED SHRIMP</div>
          <div class="metric-val text-dark font-weight-bold" id="displayCountedShrimp">0</div>
        </div>

        <!-- Metric 3 & 4: Total Biomass & Recommended Feed -->
        <div class="row mb-2" style="margin: 0 -4px;">
          <div class="col-6 px-1">
            <div class="metric-card p-2 rounded border text-center h-100">
              <div class="metric-label text-dark font-weight-bold">TOTAL BIOMASS</div>
              <div class="metric-val-sm font-weight-bold text-dark" id="displayBiomass">0.00 g</div>
            </div>
          </div>
          <div class="col-6 px-1">
            <div class="metric-card p-2 rounded border text-center h-100">
              <div class="metric-label text-dark font-weight-bold">RECOMMENDED FEED</div>
              <div class="metric-val-sm font-weight-bold text-dark" id="displayRecommendedFeed">0.00 g</div>
            </div>
          </div>
        </div>

        <!-- Primary Dispense Button -->
        <div class="mt-2">
          <button type="button" id="btnDispenseAuto" class="btn btn-shrimp-primary btn-block btn-lg font-weight-bold py-3 shadow-sm">
            Dispense Feed
          </button>
          <div id="dispenseStatusText" class="text-center font-weight-bold text-dark mt-2" style="min-height:22px; font-size:14px;"></div>
        </div>

      </div>
    </div>
  </div>
</div>

<!-- Feed Simulator Modal -->
<div class="modal" id="manualFeedModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content shadow-lg border-0" style="border-radius:12px;">
      <div class="modal-header border-bottom">
        <h5 class="modal-title font-weight-bold text-dark">Feed Simulator</h5>
        <button type="button" class="close" id="manualFeedModalClose" aria-label="Close"><span>&times;</span></button>
      </div>
      <div class="modal-body p-3">
        <label for="manualShrimpInput" class="text-dark font-weight-bold small text-uppercase mb-1">Enter Shrimp Count</label>
        <div class="input-group mb-3">
          <input id="manualShrimpInput" type="text" inputmode="none" autocomplete="off" class="form-control text-center font-weight-bold text-dark" style="font-size:1.6rem; height:50px;" placeholder="0">
          <div class="input-group-append">
            <button class="btn btn-outline-secondary font-weight-bold text-dark" type="button" id="btnManualClear">Clear</button>
          </div>
        </div>

        <div class="row mb-3" style="margin:0 -4px;">
          <div class="col-6 px-1">
            <div class="p-2 border rounded bg-light text-center">
              <small class="text-dark d-block font-weight-bold">Biomass</small>
              <strong id="manualBiomassVal" class="text-dark" style="font-size:1.2rem;">0.00 g</strong>
            </div>
          </div>
          <div class="col-6 px-1">
            <div class="p-2 border rounded bg-light text-center">
              <small class="text-dark d-block font-weight-bold">Recommended Feed</small>
              <strong id="manualFeedVal" class="text-dark" style="font-size:1.2rem;">0.00 g</strong>
            </div>
          </div>
        </div>

        <div class="d-flex" style="gap:8px;">
          <button type="button" id="btnManualDispense" class="btn btn-shrimp-primary flex-grow-1 font-weight-bold py-2">
            Dispense Feed
          </button>
          <button type="button" id="btnManualStop" class="btn btn-outline-danger font-weight-bold px-3">
            Stop
          </button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Secret Developer Live Feed Modal with Recording Indicator -->
<div class="modal" id="secretFeedModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered" style="max-width: 680px; width: 95%;">
    <div class="modal-content shadow-lg border-0 bg-dark text-white" style="border-radius:12px; overflow: hidden;">
      <div class="modal-header border-0 py-2 px-3 d-flex justify-content-between align-items-center" style="background:#111827;">
        <div class="d-flex align-items-center">
          <span class="status-dot" style="background:#dc3545; animation: blinker 1s linear infinite;"></span>
          <span class="small font-weight-bold text-white ml-2">DEV STREAM INSPECTOR &bull; REC</span>
        </div>
        <button type="button" class="close text-white" id="secretFeedClose" aria-label="Close" style="opacity: 0.8;"><span>&times;</span></button>
      </div>
      <div class="modal-body p-0 text-center bg-black" style="min-height: 480px; display: flex; align-items: center; justify-content: center;">
        <img id="secretVideoFeed" src="" alt="Developer Feed" style="max-width: 100%; height: auto; display: block; margin: 0 auto;">
      </div>
    </div>
  </div>
</div>
"""

CAMERA_EXTRA_BODY = """
<div id="captureToast" class="alert alert-success shadow"></div>
<style>
@keyframes blinker {
  50% { opacity: 0; }
}
</style>
"""

CAMERA_SCRIPT = r"""
const cameraStartContinuousBtn = document.getElementById('cameraStartContinuousBtn');
const cameraSetTargetBtn = document.getElementById('cameraSetTargetBtn');
const cameraCancelLoopBtn = document.getElementById('cameraCancelLoopBtn');
const cameraFlushBtn = document.getElementById('cameraFlushBtn');
const cameraAutomationStatusEl = document.getElementById('cameraAutomationStatus');
const cameraFlushStatusEl = document.getElementById('cameraFlushStatus');

const processStatusMain = document.getElementById('processStatusMain');
const processStatusSub = document.getElementById('processStatusSub');

const displayTargetCount = document.getElementById('displayTargetCount');
const displayCountedShrimp = document.getElementById('displayCountedShrimp');
const displayBiomass = document.getElementById('displayBiomass');
const displayRecommendedFeed = document.getElementById('displayRecommendedFeed');

const btnDispenseAuto = document.getElementById('btnDispenseAuto');
const dispenseStatusText = document.getElementById('dispenseStatusText');

const btnOpenManualModal = document.getElementById('btnOpenManualModal');
const manualFeedModal = document.getElementById('manualFeedModal');
const manualFeedModalClose = document.getElementById('manualFeedModalClose');
const manualShrimpInput = document.getElementById('manualShrimpInput');
const btnManualClear = document.getElementById('btnManualClear');
const manualBiomassVal = document.getElementById('manualBiomassVal');
const manualFeedVal = document.getElementById('manualFeedVal');
const btnManualDispense = document.getElementById('btnManualDispense');
const btnManualStop = document.getElementById('btnManualStop');

const secretFeedModal = document.getElementById('secretFeedModal');
const secretFeedClose = document.getElementById('secretFeedClose');
const secretVideoFeed = document.getElementById('secretVideoFeed');

let flushRunning = false;
let currentCounted = 0;

function formatSmartGrams(val) {
  const n = Number(val);
  if (!Number.isFinite(n) || n === 0) return '0.00 g';
  if (Math.abs(n) < 1.0) {
    return n.toFixed(5) + ' g';
  }
  return n.toFixed(2) + ' g';
}

function calcRawBiomass(count) {
  const w = (typeof calibShrimpWeight !== 'undefined') ? calibShrimpWeight : 0.00333;
  return count * w;
}

function calcRawFeed(count) {
  const w = (typeof calibShrimpWeight !== 'undefined') ? calibShrimpWeight : 0.00333;
  const m = (typeof calibFeederMultiplier !== 'undefined') ? calibFeederMultiplier : 0.15;
  return count * w * m;
}

function updateMainMetrics(counted) {
  currentCounted = counted || 0;
  displayCountedShrimp.textContent = currentCounted;
  displayBiomass.textContent = formatSmartGrams(calcRawBiomass(currentCounted));
  displayRecommendedFeed.textContent = formatSmartGrams(calcRawFeed(currentCounted));
}

function updateManualCalculator() {
  const count = parseInt(manualShrimpInput.value, 10) || 0;
  manualBiomassVal.textContent = formatSmartGrams(calcRawBiomass(count));
  manualFeedVal.textContent = formatSmartGrams(calcRawFeed(count));
}

if (btnOpenManualModal) {
  btnOpenManualModal.addEventListener('click', () => {
    manualFeedModal.classList.add('show');
    updateManualCalculator();
    setTimeout(() => manualShrimpInput.focus(), 50);
  });
}

function closeManualModal() {
  manualFeedModal.classList.remove('show');
  if (typeof hideOsk === 'function') hideOsk();
}

if (manualFeedModalClose) manualFeedModalClose.addEventListener('click', closeManualModal);
if (manualFeedModal) {
  manualFeedModal.addEventListener('click', (e) => {
    if (e.target === manualFeedModal) closeManualModal();
  });
}

if (manualShrimpInput) manualShrimpInput.addEventListener('input', updateManualCalculator);
if (btnManualClear) {
  btnManualClear.addEventListener('click', () => {
    manualShrimpInput.value = '';
    updateManualCalculator();
  });
}

function openSecretFeed() {
  if (!secretFeedModal) return;
  fetch('/api/live_feed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: true })
  }).catch(() => {});
  secretVideoFeed.src = '/video_feed';
  secretFeedModal.classList.add('show');
}

function closeSecretFeed() {
  if (!secretFeedModal) return;
  secretVideoFeed.src = '';
  secretFeedModal.classList.remove('show');
  fetch('/api/live_feed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: false })
  }).catch(() => {});
}

const brandSecretToggle = document.getElementById('secretFeedToggle');
if (brandSecretToggle) {
  brandSecretToggle.addEventListener('dblclick', (e) => {
    e.preventDefault();
    openSecretFeed();
  });
}

if (secretFeedClose) secretFeedClose.addEventListener('click', closeSecretFeed);
if (secretFeedModal) {
  secretFeedModal.addEventListener('click', (e) => {
    if (e.target === secretFeedModal) closeSecretFeed();
  });
}

if (cameraStartContinuousBtn) {
  cameraStartContinuousBtn.addEventListener('click', async () => {
    if (automationRunning || flushRunning) return;
    cameraStartContinuousBtn.disabled = true;
    try {
      const res = await fetch('/api/automation/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_count: null })
      });
      const data = await res.json();
      if (!data.ok) alert(data.error || 'Could not start counting loop');
    } catch (e) {
      alert('Error starting counting loop');
    }
    await pollCameraAutomationStatus();
  });
}

if (cameraSetTargetBtn) {
  cameraSetTargetBtn.addEventListener('click', () => {
    if (automationRunning || flushRunning) return;
    if (typeof openShrimpTargetModal === 'function') openShrimpTargetModal();
  });
}

if (cameraCancelLoopBtn) {
  cameraCancelLoopBtn.addEventListener('click', async () => {
    cameraCancelLoopBtn.disabled = true;
    try {
      await fetch('/api/automation/stop', { method: 'POST' });
    } catch (e) {}
    await pollCameraAutomationStatus();
  });
}

if (btnDispenseAuto) {
  btnDispenseAuto.addEventListener('click', async () => {
    if (currentCounted <= 0) {
      alert('Counted shrimp is currently 0. Please run a loop or use the Feed Simulator.');
      return;
    }
    btnDispenseAuto.disabled = true;
    dispenseStatusText.textContent = 'Dispensing feed for ' + currentCounted + ' shrimp...';
    try {
      const res = await fetch('/api/feed/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shrimp_count: currentCounted })
      });
      const data = await res.json();
      if (!data.ok) {
        dispenseStatusText.textContent = data.error || 'Could not start feeder';
        btnDispenseAuto.disabled = false;
      }
    } catch (e) {
      dispenseStatusText.textContent = 'Feeder communication failed';
      btnDispenseAuto.disabled = false;
    }
  });
}

if (btnManualDispense) {
  btnManualDispense.addEventListener('click', async () => {
    const count = parseInt(manualShrimpInput.value, 10);
    if (!count || count <= 0) {
      alert('Enter a valid count greater than 0.');
      return;
    }
    btnManualDispense.disabled = true;
    dispenseStatusText.textContent = 'Dispensing feed for ' + count + ' shrimp...';
    try {
      const res = await fetch('/api/feed/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shrimp_count: count })
      });
      const data = await res.json();
      if (!data.ok) {
        dispenseStatusText.textContent = data.error || 'Feeder start failed';
        btnManualDispense.disabled = false;
      } else {
        closeManualModal();
      }
    } catch (e) {
      dispenseStatusText.textContent = 'Feeder communication error';
      btnManualDispense.disabled = false;
    }
  });
}

if (btnManualStop) {
  btnManualStop.addEventListener('click', async () => {
    try {
      await fetch('/api/feed/stop', { method: 'POST' });
      dispenseStatusText.textContent = '';
    } catch(e) {}
    btnDispenseAuto.disabled = false;
    btnManualDispense.disabled = false;
  });
}

function renderCameraAutomationStatus(data, currentCount) {
  automationRunning = !!data.running;
  
  if (data.target_count != null && data.target_count > 0) {
    displayTargetCount.textContent = data.target_count;
  } else {
    displayTargetCount.textContent = 'None';
  }

  updateMainMetrics(currentCount);

  const steps = data.steps || [];
  const step = steps[data.current_index];

  if (automationRunning && step) {
    const deviceLabel = (typeof DEVICE_LABELS !== 'undefined' && DEVICE_LABELS[step.device])
      ? DEVICE_LABELS[step.device]
      : step.device;
    const action = step.action ? step.action.toUpperCase() : '';
    const tail = data.seconds_left ? ' — ' + data.seconds_left + 's' : '';
    
    let progress = '';
    if (data.target_count != null && currentCount != null) {
      progress = ' (' + currentCount + '/' + data.target_count + ' PL)';
    } else if (currentCount != null) {
      progress = ' (' + currentCount + ' PL)';
    }

    processStatusMain.textContent = 'Processing: ' + deviceLabel;
    processStatusSub.textContent = action + tail + progress;
    cameraAutomationStatusEl.innerHTML = '<strong>Running:</strong> ' + deviceLabel + ' &rarr; ' + action + tail;
  } else {
    processStatusMain.textContent = 'System Ready';
    processStatusSub.textContent = 'Waiting for cycle';
    cameraAutomationStatusEl.innerHTML = '<span class="text-dark font-weight-bold">Status: Idle</span>';
  }

  updateCameraButtonStates();
}

async function pollCameraAutomationStatus() {
  try {
    const [autoRes, countRes] = await Promise.all([
      fetch('/api/automation'),
      fetch('/api/shrimp_count')
    ]);

    if (!autoRes.ok || !countRes.ok) return;

    const autoData = await autoRes.json();
    const countData = await countRes.json();

    renderCameraAutomationStatus(autoData, countData.count);

    if (autoData.just_completed && autoData.completed_count != null) {
      dispenseStatusText.textContent = 'Cycle complete (' + autoData.completed_count + ' shrimp). Ready to dispense.';
    }
  } catch (error) {
    console.warn('[Camera] Poll error:', error);
  }
}

async function pollFeederStatus() {
  try {
    const res = await fetch('/api/feed/status');
    const status = await res.json();
    if (status.running) {
      const weight = formatSmartGrams(status.current_weight || 0);
      const target = formatSmartGrams(status.target_grams || 0);
      dispenseStatusText.innerHTML = '<span class="text-dark font-weight-bold">Dispensing... ' + weight + ' / ' + target + '</span>';
      btnDispenseAuto.disabled = true;
      btnManualDispense.disabled = true;
    } else if (status.phase === 'done') {
      dispenseStatusText.innerHTML = '<span class="text-dark font-weight-bold">Feed Dispense Complete! (' + formatSmartGrams(status.current_weight || 0) + ')</span>';
      btnDispenseAuto.disabled = false;
      btnManualDispense.disabled = false;
    }
  } catch(e) {}
}

if (cameraFlushBtn) {
  cameraFlushBtn.addEventListener('click', async () => {
    if (automationRunning || flushRunning) return;
    cameraFlushBtn.disabled = true;
    try {
      const res = await fetch('/api/flush/start', { method: 'POST' });
      const data = await res.json();
      if (!data.ok) {
        cameraFlushStatusEl.textContent = data.error || 'Could not start flush';
        updateCameraButtonStates();
        return;
      }
      cameraFlushStatusEl.innerHTML = '<strong>Flushing system...</strong>';
    } catch (e) {
      cameraFlushStatusEl.textContent = 'Flush request failed';
    }
    await pollFlushStatus();
  });
}

function renderFlushStatus(status) {
  flushRunning = !!status.running;
  const steps = status.steps || [];
  const step = steps[status.current_index];
  if (flushRunning && step) {
    const deviceLabel = (typeof DEVICE_LABELS !== 'undefined' && DEVICE_LABELS[step.device])
      ? DEVICE_LABELS[step.device]
      : step.device;
    const action = step.action ? step.action.toUpperCase() : '';
    const tail = status.seconds_left ? ' — ' + status.seconds_left + 's' : '';
    cameraFlushStatusEl.innerHTML = '<strong>Flushing:</strong> ' + deviceLabel + ' &rarr; ' + action + tail;
    processStatusMain.textContent = 'Flushing System';
    processStatusSub.textContent = deviceLabel + ' ' + action + tail;
  } else {
    cameraFlushStatusEl.innerHTML = '&nbsp;';
  }
  updateCameraButtonStates();
}

async function pollFlushStatus() {
  try {
    const res = await fetch('/api/flush/status');
    if (res.ok) renderFlushStatus(await res.json());
  } catch (e) {}
}

function updateCameraButtonStates() {
  if (cameraStartContinuousBtn) cameraStartContinuousBtn.disabled = automationRunning || flushRunning;
  if (cameraSetTargetBtn) cameraSetTargetBtn.disabled = automationRunning || flushRunning;
  if (cameraCancelLoopBtn) cameraCancelLoopBtn.disabled = !automationRunning;
  if (cameraFlushBtn) cameraFlushBtn.disabled = automationRunning || flushRunning;
}

updateCameraButtonStates();
pollCameraAutomationStatus();
pollFlushStatus();

setInterval(pollCameraAutomationStatus, 1000);
setInterval(pollFlushStatus, 1000);
setInterval(pollFeederStatus, 1000);
"""

def create_camera_blueprint(render_page):
    camera_bp = Blueprint("camera", __name__)

    @camera_bp.route("/")
    def index():
        html = render_page(
            "camera",
            CAMERA_BODY,
            CAMERA_SCRIPT,
            extra_body=CAMERA_EXTRA_BODY,
            full_height=False
        )
        return Response(
            html,
            mimetype="text/html",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )

    return camera_bp