"""
Camera page (/) - ShrimpSense Aquaculture Dashboard
- Zero-scroll industrial dashboard
- 4 primary action buttons on the left
- Status on bottom-left, Full Timestamp on bottom-right (Month Day, Year, HH:MM:SS AM/PM)
- Right side: Compact cards, Dispense Feed, and secondary "Manual Mode" button
- Secret Developer Live Feed (Double-click ShrimpSense logo/title in navbar)
"""

from flask import Blueprint, Response

CAMERA_BODY = """
<div class="dashboard-grid-container">
  <!-- Left Side: Status Display, 4 Machine Buttons, Footer Info -->
  <div class="col-panel left-panel">
    <div class="card h-100 shadow-sm border-0 d-flex flex-column justify-content-between p-2" style="border-radius: 8px;">
      
      <!-- Compact White Process Area -->
      <div class="process-stage-container d-flex flex-column align-items-center justify-content-center border" id="processDisplayArea">
        <div id="processStatusMain" class="process-text-headline text-center font-weight-bold">
          System Ready
        </div>
        <div id="processStatusSub" class="process-text-sub text-center mt-1">
          Waiting for cycle
        </div>
      </div>

      <!-- Exactly 4 Inline Buttons -->
      <div class="d-flex justify-content-between mt-2 button-row" style="gap:6px;">
        <button id="cameraStartContinuousBtn" class="btn btn-shrimp-primary font-weight-bold flex-fill">
          Start
        </button>
        <button id="cameraSetTargetBtn" class="btn btn-shrimp-accent font-weight-bold flex-fill">
          Set Target
        </button>
        <button id="cameraCancelLoopBtn" class="btn btn-outline-danger font-weight-bold flex-fill">
          Cancel
        </button>
        <button id="cameraFlushBtn" class="btn btn-outline-marine font-weight-bold flex-fill">
          Flush
        </button>
      </div>

      <!-- Footer Bar: Status on Left, Full Timestamp on Right -->
      <div class="d-flex justify-content-between align-items-center mt-2 px-1 border-top pt-1 text-dark" style="font-size: 11px;">
        <div id="cameraAutomationStatus" class="font-weight-bold text-truncate mr-2">
          Status: Idle
        </div>
        <div id="dashboardFooterClock" class="font-weight-bold text-muted text-nowrap">
          -- --, ----, --:--:-- --
        </div>
      </div>

    </div>
  </div>

  <!-- Right Side: Metrics, Dispense Feed, and Manual Mode -->
  <div class="col-panel right-panel">
    <div class="card h-100 shadow-sm border-0 d-flex flex-column justify-content-between p-2" style="border-radius: 8px;">
      
      <div class="metrics-wrap">
        <!-- Metric 1: Target PL Shrimp Count -->
        <div class="metric-card mb-1 p-1 rounded border">
          <div class="metric-label text-dark font-weight-bold">TARGET PL SHRIMP COUNT</div>
          <div class="metric-val text-dark font-weight-bold" id="displayTargetCount">None</div>
        </div>

        <!-- Metric 2: Counted Shrimp -->
        <div class="metric-card mb-1 p-1 rounded border">
          <div class="metric-label text-dark font-weight-bold">COUNTED SHRIMP</div>
          <div class="metric-val text-dark font-weight-bold" id="displayCountedShrimp">0</div>
        </div>

        <!-- Metric 3 & 4: Total Biomass & Recommended Feed -->
        <div class="row mb-1" style="margin: 0 -2px;">
          <div class="col-6 px-1">
            <div class="metric-card p-1 rounded border text-center h-100">
              <div class="metric-label text-dark font-weight-bold">TOTAL BIOMASS</div>
              <div class="metric-val-sm font-weight-bold text-dark" id="displayBiomass">0.00 g</div>
            </div>
          </div>
          <div class="col-6 px-1">
            <div class="metric-card p-1 rounded border text-center h-100">
              <div class="metric-label text-dark font-weight-bold">RECOMMENDED FEED</div>
              <div class="metric-val-sm font-weight-bold text-dark" id="displayRecommendedFeed">0.00 g</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Action Section: Dispense Button & Cohesive Manual Mode Action -->
      <div class="mt-1 d-flex flex-column">
        <button type="button" id="btnDispenseAuto" class="btn btn-shrimp-primary btn-block font-weight-bold py-2 shadow-sm" style="font-size: 1.1rem;">
          Dispense Feed
        </button>
        <div id="dispenseStatusText" class="text-center font-weight-bold text-dark mt-1" style="min-height: 16px; font-size: 11px;"></div>
        
        <!-- Secondary Button for Manual Mode directly below -->
        <button type="button" id="btnOpenManualModal" class="btn btn-outline-secondary btn-block btn-sm font-weight-bold mt-1 py-1">
          Manual Mode
        </button>
      </div>

    </div>
  </div>
</div>

<!-- Manual Mode Modal -->
<div class="modal" id="manualFeedModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content shadow-lg border-0" style="border-radius:10px;">
      <div class="modal-header border-bottom py-2">
        <h5 class="modal-title font-weight-bold text-dark">Manual Mode</h5>
        <button type="button" class="close" id="manualFeedModalClose" aria-label="Close"><span>&times;</span></button>
      </div>
      <div class="modal-body p-3">
        <label for="manualShrimpInput" class="text-dark font-weight-bold small text-uppercase mb-1">Enter Shrimp Count</label>
        <div class="input-group mb-2">
          <input id="manualShrimpInput" type="text" inputmode="none" autocomplete="off" class="form-control text-center font-weight-bold text-dark" style="font-size:1.4rem; height:44px;" placeholder="0">
          <div class="input-group-append">
            <button class="btn btn-outline-secondary font-weight-bold text-dark" type="button" id="btnManualClear">Clear</button>
          </div>
        </div>

        <div class="row mb-3" style="margin:0 -4px;">
          <div class="col-6 px-1">
            <div class="p-2 border rounded bg-light text-center">
              <small class="text-dark d-block font-weight-bold">Biomass</small>
              <strong id="manualBiomassVal" class="text-dark" style="font-size:1.1rem;">0.00 g</strong>
            </div>
          </div>
          <div class="col-6 px-1">
            <div class="p-2 border rounded bg-light text-center">
              <small class="text-dark d-block font-weight-bold">Recommended Feed</small>
              <strong id="manualFeedVal" class="text-dark" style="font-size:1.1rem;">0.00 g</strong>
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

<!-- Secret Developer Live Feed Modal -->
<div class="modal" id="secretFeedModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered" style="max-width: 640px; width: 95%;">
    <div class="modal-content shadow-lg border-0 bg-dark text-white" style="border-radius:10px; overflow: hidden;">
      <div class="modal-header border-0 py-2 px-3 d-flex justify-content-between align-items-center" style="background:#111827;">
        <div class="d-flex align-items-center">
          <span class="status-dot" style="background:#dc3545; animation: blinker 1s linear infinite;"></span>
          <span class="small font-weight-bold text-white ml-2">DEV STREAM INSPECTOR &bull; REC</span>
        </div>
        <button type="button" class="close text-white" id="secretFeedClose" aria-label="Close" style="opacity: 0.8;"><span>&times;</span></button>
      </div>
      <div class="modal-body p-0 text-center bg-black" style="min-height: 400px; display: flex; align-items: center; justify-content: center;">
        <img id="secretVideoFeed" src="" alt="Developer Feed" style="max-width: 100%; height: auto; display: block; margin: 0 auto;">
      </div>
    </div>
  </div>
</div>
"""

CAMERA_EXTRA_BODY = """
<div id="captureToast" class="alert alert-success shadow"></div>
<style>
/* Full screen fit layout without scrolling */
.dashboard-grid-container {
  display: flex;
  flex-direction: row;
  height: calc(100vh - 54px);
  max-height: calc(100vh - 54px);
  gap: 8px;
  padding: 6px;
  overflow: hidden;
  box-sizing: border-box;
}
.col-panel {
  flex: 1 1 50%;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.process-stage-container {
  background: #ffffff;
  border-radius: 6px;
  flex: 1 1 auto;
  min-height: 120px;
  width: 100%;
  padding: 8px;
}
.process-text-headline {
  font-size: 1.6rem;
  color: #111827;
  letter-spacing: 0.5px;
}
.process-text-sub {
  font-size: 1rem;
  color: #111827;
}
.button-row button {
  padding: 7px 4px;
  font-size: 13px;
  white-space: nowrap;
}
.metric-card {
  background: #ffffff;
}
.metric-label {
  font-size: 9.5px;
  line-height: 1.1;
}
.metric-val {
  font-size: 1.45rem;
  line-height: 1.1;
}
.metric-val-sm {
  font-size: 1.15rem;
  line-height: 1.1;
}
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

// Full Timestamp Formatter: Month Day, Year, HH:MM:SS AM/PM
function updateDashboardClock(){
  const el = document.getElementById('dashboardFooterClock');
  if (!el) return;
  const now = new Date();
  const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const month = months[now.getMonth()];
  const day = now.getDate();
  const year = now.getFullYear();

  let hours = now.getHours();
  const minutes = String(now.getMinutes()).padStart(2, '0');
  const seconds = String(now.getSeconds()).padStart(2, '0');
  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12;
  hours = hours ? String(hours).padStart(2, '0') : '12';

  el.textContent = `${month} ${day}, ${year}, ${hours}:${minutes}:${seconds} ${ampm}`;
}
setInterval(updateDashboardClock, 1000);
updateDashboardClock();

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

// Manual Mode Modal Logic
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

// Developer Inspector Logic
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

// Loop Start & Cancel Actions
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

// Dispensing Handlers
if (btnDispenseAuto) {
  btnDispenseAuto.addEventListener('click', async () => {
    if (currentCounted <= 0) {
      alert('Counted shrimp is currently 0. Please run a loop or use Manual Mode.');
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
        alert(data.error || 'Could not start flush');
        updateCameraButtonStates();
        return;
      }
    } catch (e) {
      alert('Flush request failed');
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
    cameraAutomationStatusEl.innerHTML = '<strong>Flushing:</strong> ' + deviceLabel + ' &rarr; ' + action + tail;
    processStatusMain.textContent = 'Flushing System';
    processStatusSub.textContent = deviceLabel + ' ' + action + tail;
  } else if (!automationRunning) {
    cameraAutomationStatusEl.innerHTML = '<span class="text-dark font-weight-bold">Status: Idle</span>';
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