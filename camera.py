"""
Camera page (/) - ShrimpSense Industrial Touchscreen HMI
- Shared 42px baseline band: Manual Mode button height & styling locked to Left Telemetry footer
- Matching 1px solid #cbd5e1 border and 6px border-radius across bottom row
- 10px tight grouping between Dispense Feed (50px) and Manual Mode (42px)
- Strict 22px bottom padding alignment across both primary panels
"""

from flask import Blueprint, Response

CAMERA_BODY = """
<div class="hmi-dashboard">
  <!-- Left Side: Vision/Process Stage, 4 Action Buttons, Telemetry Bar -->
  <section class="hmi-panel hmi-panel-left">
    
    <!-- Process Stage Area (60% Vertical Workspace) -->
    <div class="hmi-card hmi-stage-card" id="processDisplayArea">
      <div class="stage-centerpiece">
        <div id="processStatusMain" class="stage-headline">System Ready</div>
        <div id="processStatusSub" class="stage-subhead">Waiting for cycle</div>
      </div>
    </div>

    <!-- 4 High-Target Industrial Machine Buttons -->
    <div class="hmi-action-row">
      <button id="cameraStartContinuousBtn" class="hmi-touch-btn hmi-btn-primary">
        Start
      </button>
      <button id="cameraSetTargetBtn" class="hmi-touch-btn hmi-btn-accent">
        Set Target
      </button>
      <button id="cameraCancelLoopBtn" class="hmi-touch-btn hmi-btn-danger">
        Cancel
      </button>
      <button id="cameraFlushBtn" class="hmi-touch-btn hmi-btn-neutral">
        Flush
      </button>
    </div>

    <!-- Machine Telemetry Footer (Baseline Anchor: 42px Height) -->
    <footer class="hmi-telemetry-bar">
      <div id="cameraAutomationStatus" class="telemetry-status">
        <span class="telemetry-tag">STATUS:</span> <span class="telemetry-val">Idle</span>
      </div>
      <div id="dashboardFooterClock" class="telemetry-clock">
        -- --, ----, --:--:-- --
      </div>
    </footer>

  </section>

  <!-- Right Side: Two Sections Only (Information Section + Bottom-Anchored Action Section) -->
  <section class="hmi-panel hmi-panel-right">
    
    <!-- Section 1: Information Section (Absorbs available space) -->
    <div class="hmi-info-section">
      <!-- Card 1: Target Shrimp Count -->
      <div class="hmi-card hmi-metric-card">
        <div class="hmi-metric-label">TARGET SHRIMP COUNT</div>
        <div class="hmi-metric-value" id="displayTargetCount">None</div>
      </div>

      <!-- Card 2: Counted Shrimp -->
      <div class="hmi-card hmi-metric-card">
        <div class="hmi-metric-label">COUNTED SHRIMP</div>
        <div class="hmi-metric-value" id="displayCountedShrimp">0</div>
      </div>

      <!-- Card 3: Total Biomass & Recommended Feed (Equal Height & Width) -->
      <div class="hmi-metric-grid">
        <div class="hmi-card hmi-metric-card-split">
          <div class="hmi-metric-label">TOTAL BIOMASS</div>
          <div class="hmi-metric-value-sm" id="displayBiomass">0.00 g</div>
        </div>
        <div class="hmi-card hmi-metric-card-split">
          <div class="hmi-metric-label">RECOMMENDED FEED</div>
          <div class="hmi-metric-value-sm" id="displayRecommendedFeed">0.00 g</div>
        </div>
      </div>

      <!-- Live Dispense Status Text (Kept inside info flow, never between buttons) -->
      <div id="dispenseStatusText" class="hmi-dispense-feedback"></div>
    </div>

    <!-- Section 2: Action Section (Anchored to the absolute bottom of right panel) -->
    <div class="hmi-action-section">
      <button type="button" id="btnDispenseAuto" class="hmi-touch-btn hmi-btn-primary hmi-btn-dispense">
        Dispense Feed
      </button>
      <!-- Manual Mode matches height (42px), radius (6px), and border with Left Telemetry Footer -->
      <button type="button" id="btnOpenManualModal" class="hmi-touch-btn hmi-btn-secondary hmi-btn-manual">
        Manual Mode
      </button>
    </div>

  </section>
</div>

<!-- ========================================== -->
<!-- Target PL Shrimp Count Modal with Keypad   -->
<!-- ========================================== -->
<div class="modal" id="shrimpTargetModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered" style="max-width: 440px; width: 95%;">
    <div class="modal-content hmi-modal-box">
      <!-- Title -->
      <div class="hmi-modal-titlebar">
        <h5 class="hmi-dialog-title">Target Shrimp Count</h5>
        <button type="button" class="close" id="shrimpModalClose" aria-label="Close"><span>&times;</span></button>
      </div>

      <div class="hmi-modal-body">
        <!-- Input Field -->
        <div>
          <label for="shrimpTargetInput" class="hmi-metric-label mb-1">Set Desired Count</label>
          <input type="text" inputmode="none" autocomplete="off" class="form-control hmi-dialog-input" id="shrimpTargetInput" placeholder="0" readonly>
        </div>

        <!-- Inline Keypad (Elevated closer to active input) -->
        <div class="hmi-dialog-keypad">
          <button type="button" class="hmi-key-btn" data-val="1">1</button>
          <button type="button" class="hmi-key-btn" data-val="2">2</button>
          <button type="button" class="hmi-key-btn" data-val="3">3</button>
          <button type="button" class="hmi-key-btn" data-val="4">4</button>
          <button type="button" class="hmi-key-btn" data-val="5">5</button>
          <button type="button" class="hmi-key-btn" data-val="6">6</button>
          <button type="button" class="hmi-key-btn" data-val="7">7</button>
          <button type="button" class="hmi-key-btn" data-val="8">8</button>
          <button type="button" class="hmi-key-btn" data-val="9">9</button>
          <button type="button" class="hmi-key-btn hmi-key-fn" id="targetKeyClear">CLR</button>
          <button type="button" class="hmi-key-btn" data-val="0">0</button>
          <button type="button" class="hmi-key-btn hmi-key-fn" id="targetKeyBack">&#9003;</button>
        </div>

        <!-- Action Buttons -->
        <div class="hmi-modal-actions">
          <button type="button" class="hmi-touch-btn hmi-btn-neutral flex-fill" id="shrimpModalCancel" style="height:48px;">Cancel</button>
          <button type="button" class="hmi-touch-btn hmi-btn-primary flex-fill" id="shrimpModalSubmit" style="height:48px;">Confirm &amp; Start</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ========================================== -->
<!-- Manual Mode Modal (Feed Simulator)        -->
<!-- ========================================== -->
<div class="modal" id="manualFeedModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered" style="max-width: 480px; width: 95%;">
    <div class="modal-content hmi-modal-box">
      <div class="hmi-modal-titlebar">
        <h5 class="hmi-dialog-title">Manual Feed Simulation</h5>
        <button type="button" class="close" id="manualFeedModalClose" aria-label="Close"><span>&times;</span></button>
      </div>

      <div class="hmi-modal-body">
        <div>
          <label for="manualShrimpInput" class="hmi-metric-label mb-1">Enter Shrimp Count</label>
          <div class="input-group">
            <input id="manualShrimpInput" type="text" inputmode="none" autocomplete="off" class="form-control hmi-dialog-input" placeholder="0">
            <div class="input-group-append">
              <button class="btn btn-outline-secondary font-weight-bold px-3" type="button" id="btnManualClear">Clear</button>
            </div>
          </div>
        </div>

        <!-- Perfectly Aligned Dual Split Cards -->
        <div class="hmi-metric-grid">
          <div class="hmi-card hmi-metric-card-split bg-light">
            <div class="hmi-metric-label">Total Biomass</div>
            <div id="manualBiomassVal" class="hmi-metric-value-sm">0.00 g</div>
          </div>
          <div class="hmi-card hmi-metric-card-split bg-light">
            <div class="hmi-metric-label">Recommended Feed</div>
            <div id="manualFeedVal" class="hmi-metric-value-sm">0.00 g</div>
          </div>
        </div>

        <!-- Cohesive Action Group (Identical 50px Height) -->
        <div class="hmi-modal-actions mt-1">
          <button type="button" id="btnManualDispense" class="hmi-touch-btn hmi-btn-primary flex-fill" style="height: 50px;">
            Dispense Feed
          </button>
          <button type="button" id="btnManualStop" class="hmi-touch-btn hmi-btn-danger flex-fill" style="height: 50px;">
            Stop
          </button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ============================================================== -->
<!-- Hidden Developer Mode Modal (Industrial Diagnostic Layout)     -->
<!-- ============================================================== -->
<div class="modal" id="developerModeModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered" style="max-width: 1240px; width: 98%; height: 95%;">
    <div class="modal-content hmi-modal-box d-flex flex-column h-100 p-0 overflow-hidden bg-dark text-white border-secondary">
      
      <!-- Top Diagnostic Header -->
      <div class="d-flex justify-content-between align-items-center px-3 py-2 bg-black border-bottom border-secondary" style="height: 42px;">
        <div class="d-flex align-items-center">
          <span class="status-dot" id="devRecDot" style="background:#64748b;"></span>
          <span class="small font-weight-bold ml-2 text-light" style="letter-spacing: 0.5px;">DIAGNOSTIC &bull; SHRIMP CV DATASET STUDIO</span>
        </div>
        <span class="small font-weight-bold text-muted">Raspberry Pi Hardware Camera Inspector</span>
      </div>

      <!-- Large Live Camera Viewport (80-85% Height) -->
      <div class="dev-stream-viewport">
        <img id="devVideoFeed" src="" alt="Developer Feed" class="dev-stream-img">
        <div id="devFeedFallback" class="text-muted text-center" style="display:none;">
          <h5>Camera Feed Inactive</h5>
          <small>Check hardware connection</small>
        </div>
      </div>

      <!-- Uniform Grid-Aligned Diagnostic Footer Panel -->
      <div class="dev-footer-panel">
        
        <!-- Left Group: 4 Symmetrical Telemetry Diagnostic Cards -->
        <div class="dev-telemetry-grid">
          
          <div class="dev-stat-card">
            <span class="dev-stat-label">RECORDING STATUS</span>
            <div class="dev-stat-value" id="devRecordingStatusText">● Idle</div>
          </div>

          <div class="dev-stat-card">
            <span class="dev-stat-label">ELAPSED TIME</span>
            <div class="dev-stat-value font-monospace" id="devRecordTimer">00:00</div>
          </div>

          <div class="dev-stat-card">
            <span class="dev-stat-label">STORAGE REMAINING</span>
            <div class="dev-stat-value" id="devStorageRemaining">14.8 GB</div>
          </div>

          <div class="dev-stat-card">
            <span class="dev-stat-label">VIDEOS RECORDED</span>
            <div class="dev-stat-value" id="devVideosRecorded">0</div>
          </div>

        </div>

        <!-- Right Group: Diagnostic Action Buttons -->
        <div class="dev-actions-cluster">
          <button type="button" id="btnDevStartRecord" class="hmi-touch-btn hmi-btn-primary dev-action-btn">
            Start Recording
          </button>
          <button type="button" id="btnDevStopRecord" class="hmi-touch-btn hmi-btn-neutral dev-action-btn" disabled>
            Stop Recording
          </button>
          <button type="button" id="btnExitDevMode" class="hmi-touch-btn hmi-btn-secondary dev-action-btn">
            Exit
          </button>
        </div>

      </div>

    </div>
  </div>
</div>
"""

CAMERA_EXTRA_BODY = """
<div id="captureToast" class="alert alert-success shadow"></div>
<style>
/* Root HMI Dashboard: 18px top margin, 22px bottom buffer across both panels */
.hmi-dashboard {
  display: flex;
  flex-direction: row;
  height: calc(100vh - 74px);
  max-height: calc(100vh - 74px);
  gap: 14px;
  padding: 18px 10px 22px 10px;
  overflow: hidden;
  box-sizing: border-box;
}

.hmi-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.hmi-panel-left {
  flex: 5.8;
  gap: 12px;
}

/* Right Panel: Clean two-section column */
.hmi-panel-right {
  flex: 4.2;
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* Section 1: Info section holding all metrics */
.hmi-info-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

/* Section 2: Action group anchored to the absolute bottom */
.hmi-action-section {
  margin-top: auto; /* Pushes button pair flush to the bottom */
  display: flex;
  flex-direction: column;
  gap: 10px; /* Exact 10px spacing between Dispense Feed and Manual Mode */
  width: 100%;
}

/* Base Industrial Card */
.hmi-card {
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

/* 60% Left Panel Video/Stage Container */
.hmi-stage-card {
  flex: 6 1 0;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  border: 2px solid #cbd5e1;
  position: relative;
}
.stage-centerpiece {
  text-align: center;
  padding: 16px;
}
.stage-headline {
  font-size: 2.2rem;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.5px;
  line-height: 1.15;
}
.stage-subhead {
  font-size: 1.25rem;
  font-weight: 600;
  color: #475569;
  margin-top: 6px;
}

/* Machine Controls Row */
.hmi-action-row {
  display: flex;
  flex-direction: row;
  gap: 10px;
  height: 52px;
  flex-shrink: 0;
}
.hmi-touch-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1rem;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  user-select: none;
  touch-action: manipulation;
  transition: filter 0.15s ease, transform 0.05s ease;
}
.hmi-touch-btn:active {
  transform: scale(0.98);
}
.hmi-action-row .hmi-touch-btn {
  flex: 1;
  height: 100%;
}

/* Industrial Action Button Styling */
.hmi-btn-primary {
  background: var(--shrimp-red);
  color: #ffffff;
  border-color: #b91c1c;
}
.hmi-btn-primary:active { background: #991b1b; }
.hmi-btn-accent {
  background: var(--shrimp-orange);
  color: #ffffff;
  border-color: #ea580c;
}
.hmi-btn-accent:active { background: #c2410c; }
.hmi-btn-danger {
  background: #ffffff;
  color: #dc2626;
  border: 2px solid #ef4444;
}
.hmi-btn-danger:active { background: #fee2e2; }
.hmi-btn-neutral {
  background: #ffffff;
  color: #0f172a;
  border: 2px solid #475569;
}
.hmi-btn-neutral:active { background: #e2e8f0; }

/* Status & Timestamp Bar (Baseline Anchor: 42px Height) */
.hmi-telemetry-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 14px;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  height: 42px;
  flex-shrink: 0;
  font-size: 0.88rem;
  box-sizing: border-box;
}
.telemetry-status {
  font-weight: 700;
  color: #0f172a;
}
.telemetry-tag {
  color: #64748b;
  margin-right: 4px;
}
.telemetry-clock {
  font-family: monospace, sans-serif;
  font-weight: 700;
  color: #334155;
}

/* Metric Display Cards (Equal 88px Height & Consistent Padding) */
.hmi-metric-card {
  height: 88px;
  padding: 10px 16px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  flex-shrink: 0;
  width: 100%;
}
.hmi-metric-grid {
  display: flex;
  gap: 12px;
  height: 88px;
  flex-shrink: 0;
  width: 100%;
}
.hmi-metric-card-split {
  flex: 1;
  padding: 10px 16px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  text-align: center;
}
.hmi-metric-label {
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.8px;
  color: #64748b;
  text-transform: uppercase;
  margin-bottom: 2px;
}
.hmi-metric-value {
  font-size: 2.15rem;
  font-weight: 800;
  line-height: 1.1;
  color: #0f172a;
}
.hmi-metric-value-sm {
  font-size: 1.5rem;
  font-weight: 800;
  line-height: 1.1;
  color: #0f172a;
}

/* Dispense Feed (Primary Action) */
.hmi-btn-dispense {
  width: 100%;
  height: 52px;
  font-size: 1.15rem;
}

/* Manual Mode (Symmetric Horizontal Footer Partner: Exactly 42px Height) */
.hmi-btn-manual {
  width: 100%;
  height: 42px;
  font-size: 0.95rem;
  background: #f8fafc;
  color: #1e293b;
  border: 1px solid #cbd5e1; /* Identical border thickness and color as Telemetry Footer */
  border-radius: 6px;        /* Identical corner radius as Telemetry Footer */
  box-sizing: border-box;
}
.hmi-btn-manual:active {
  background: #e2e8f0;
}

.hmi-dispense-feedback {
  min-height: 16px;
  font-size: 0.85rem;
  font-weight: 700;
  text-align: center;
  color: #1e293b;
  margin-top: -4px;
}

/* Modal Box Standards */
.hmi-modal-box {
  padding: 24px;
  border-radius: 12px;
  border: 1px solid #94a3b8;
  box-shadow: 0 10px 25px rgba(0,0,0,0.25);
  background: #ffffff;
}
.hmi-modal-titlebar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.hmi-dialog-title {
  font-size: 1.25rem;
  font-weight: 800;
  color: #0f172a;
  margin: 0;
}
.hmi-modal-body {
  display: flex;
  flex-direction: column;
  gap: 12px; /* Tight 12px gap to lift keypad higher */
  padding: 0;
}
.hmi-dialog-input {
  font-size: 1.6rem;
  font-weight: 800;
  height: 48px;
  text-align: center;
  color: #0f172a;
  border: 2px solid #cbd5e1;
  border-radius: 6px;
}

/* Keypad Layout */
.hmi-dialog-keypad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.hmi-key-btn {
  height: 48px;
  font-size: 1.4rem;
  font-weight: 800;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #f8fafc;
  color: #0f172a;
  touch-action: manipulation;
}
.hmi-key-btn:active { background: #e2e8f0; }
.hmi-key-fn { background: #e2e8f0; font-size: 1.1rem; color: #475569; }

.hmi-modal-actions {
  display: flex;
  gap: 12px;
}

/* ========================================================= */
/* Developer Dataset Collector Diagnostic Styling            */
/* ========================================================= */
.dev-stream-viewport {
  flex: 1 1 82%;
  min-height: 0;
  background: #000000;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}
.dev-stream-img {
  max-height: 100%;
  max-width: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
}

.dev-footer-panel {
  flex: 0 0 94px;
  background: #111827;
  border-top: 2px solid #374151;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  gap: 16px;
}

/* 4-Column Equal Telemetry Diagnostic Grid */
.dev-telemetry-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  flex: 1;
}
.dev-stat-card {
  height: 72px;
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 8px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.dev-stat-label {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.7px;
  color: #9ca3af;
  text-transform: uppercase;
}
.dev-stat-value {
  font-size: 1.35rem;
  font-weight: 800;
  color: #f3f4f6;
  line-height: 1.2;
  margin-top: 2px;
}

/* Right Group: Diagnostic Action Buttons */
.dev-actions-cluster {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dev-action-btn {
  height: 64px;
  min-width: 130px;
  font-size: 0.95rem;
  padding: 0 16px;
  white-space: nowrap;
}

@keyframes blinker { 50% { opacity: 0; } }
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

const shrimpTargetModal = document.getElementById('shrimpTargetModal');
const shrimpModalClose = document.getElementById('shrimpModalClose');
const shrimpModalCancel = document.getElementById('shrimpModalCancel');
const shrimpModalSubmit = document.getElementById('shrimpModalSubmit');
const shrimpTargetInput = document.getElementById('shrimpTargetInput');
const targetKeyClear = document.getElementById('targetKeyClear');
const targetKeyBack = document.getElementById('targetKeyBack');

let flushRunning = false;
let currentCounted = 0;

// Footer Clock Implementation (Month Day, Year, HH:MM:SS AM/PM)
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
  hours = hours ? hours : 12;
  const strHours = String(hours).padStart(2, '0');

  el.textContent = `${month} ${day}, ${year}, ${strHours}:${minutes}:${seconds} ${ampm}`;
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

// Target Modal Logic with Keypad Integration
function openTargetModal() {
  if (!shrimpTargetModal) return;
  shrimpTargetInput.value = '';
  shrimpTargetModal.classList.add('show');
}
function closeTargetModal() {
  if (!shrimpTargetModal) return;
  shrimpTargetModal.classList.remove('show');
}
if (cameraSetTargetBtn) cameraSetTargetBtn.addEventListener('click', openTargetModal);
if (shrimpModalClose) shrimpModalClose.addEventListener('click', closeTargetModal);
if (shrimpModalCancel) shrimpModalCancel.addEventListener('click', closeTargetModal);

document.querySelectorAll('.hmi-key-btn[data-val]').forEach(btn => {
  btn.addEventListener('click', () => {
    shrimpTargetInput.value = (shrimpTargetInput.value || '') + btn.getAttribute('data-val');
  });
});
if (targetKeyClear) {
  targetKeyClear.addEventListener('click', () => { shrimpTargetInput.value = ''; });
}
if (targetKeyBack) {
  targetKeyBack.addEventListener('click', () => {
    shrimpTargetInput.value = shrimpTargetInput.value.slice(0, -1);
  });
}
if (shrimpModalSubmit) {
  shrimpModalSubmit.addEventListener('click', async () => {
    const value = parseInt(shrimpTargetInput.value, 10);
    if (!value || value <= 0) {
      alert('Enter a valid target count greater than 0.');
      return;
    }
    closeTargetModal();
    try {
      await fetch('/api/automation/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_count: value })
      });
    } catch(e){}
    await pollCameraAutomationStatus();
  });
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

// Hidden Developer Dataset Studio Logic
const devModeModal = document.getElementById('developerModeModal');
const devVideoFeed = document.getElementById('devVideoFeed');
const btnExitDevMode = document.getElementById('btnExitDevMode');
const btnDevStartRecord = document.getElementById('btnDevStartRecord');
const btnDevStopRecord = document.getElementById('btnDevStopRecord');
const devRecDot = document.getElementById('devRecDot');
const devRecordingStatusText = document.getElementById('devRecordingStatusText');
const devRecordTimer = document.getElementById('devRecordTimer');
const devStorageRemaining = document.getElementById('devStorageRemaining');
const devVideosRecorded = document.getElementById('devVideosRecorded');

let devRecordInterval = null;
let devSecondsElapsed = 0;
let devIsRecording = false;

function openDeveloperMode() {
  if (!devModeModal) return;
  fetch('/api/live_feed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: true })
  }).catch(() => {});
  
  devVideoFeed.src = '/video_feed';
  devModeModal.classList.add('show');
  refreshDevTelemetry();
}

function closeDeveloperMode() {
  if (!devModeModal) return;
  if (devIsRecording) stopDevRecording();
  devVideoFeed.src = '';
  devModeModal.classList.remove('show');
  
  fetch('/api/live_feed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: false })
  }).catch(() => {});
}

async function refreshDevTelemetry() {
  try {
    const res = await fetch('/api/developer/stats');
    if (res.ok) {
      const data = await res.json();
      if (devStorageRemaining) devStorageRemaining.textContent = (data.storage_gb || '14.8') + ' GB';
      if (devVideosRecorded) devVideosRecorded.textContent = (data.video_count || '0');
    }
  } catch(e) {}
}

const secretBrandToggle = document.getElementById('secretFeedToggle');
if (secretBrandToggle) {
  secretBrandToggle.addEventListener('dblclick', (e) => {
    e.preventDefault();
    openDeveloperMode();
  });
}
if (btnExitDevMode) btnExitDevMode.addEventListener('click', closeDeveloperMode);

function startDevRecording() {
  devIsRecording = true;
  devSecondsElapsed = 0;
  btnDevStartRecord.disabled = true;
  btnDevStopRecord.disabled = false;
  devRecDot.style.background = '#dc2626';
  devRecDot.style.animation = 'blinker 1s linear infinite';
  devRecordingStatusText.textContent = '● Recording';
  devRecordingStatusText.style.color = '#ef4444';

  fetch('/api/developer/record/start', { method: 'POST' }).catch(() => {});

  devRecordInterval = setInterval(() => {
    devSecondsElapsed++;
    const m = String(Math.floor(devSecondsElapsed / 60)).padStart(2, '0');
    const s = String(devSecondsElapsed % 60).padStart(2, '0');
    devRecordTimer.textContent = `${m}:${s}`;
  }, 1000);
}

function stopDevRecording() {
  devIsRecording = false;
  clearInterval(devRecordInterval);
  btnDevStartRecord.disabled = false;
  btnDevStopRecord.disabled = true;
  devRecDot.style.background = '#64748b';
  devRecDot.style.animation = 'none';
  devRecordingStatusText.textContent = '● Idle';
  devRecordingStatusText.style.color = '#f3f4f6';

  fetch('/api/developer/record/stop', { method: 'POST' }).catch(() => {});
  refreshDevTelemetry();
}

if (btnDevStartRecord) btnDevStartRecord.addEventListener('click', startDevRecording);
if (btnDevStopRecord) btnDevStopRecord.addEventListener('click', stopDevRecording);

// Machine Loop Actions
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

if (cameraCancelLoopBtn) {
  cameraCancelLoopBtn.addEventListener('click', async () => {
    cameraCancelLoopBtn.disabled = true;
    try {
      await fetch('/api/automation/stop', { method: 'POST' });
    } catch (e) {}
    await pollCameraAutomationStatus();
  });
}

// Dispense Actions
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

    processStatusMain.textContent = 'Running: ' + deviceLabel;
    processStatusSub.textContent = action + tail + progress;
    cameraAutomationStatusEl.innerHTML = '<span class="telemetry-tag">RUNNING:</span> <span class="telemetry-val text-primary">' + deviceLabel + ' &rarr; ' + action + tail + '</span>';
  } else {
    processStatusMain.textContent = 'System Ready';
    processStatusSub.textContent = 'Waiting for cycle';
    cameraAutomationStatusEl.innerHTML = '<span class="telemetry-tag">STATUS:</span> <span class="telemetry-val">Idle</span>';
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
      dispenseStatusText.innerHTML = '<span class="font-weight-bold text-primary">Dispensing... ' + weight + ' / ' + target + '</span>';
      btnDispenseAuto.disabled = true;
      btnManualDispense.disabled = true;
    } else if (status.phase === 'done') {
      dispenseStatusText.innerHTML = '<span class="font-weight-bold text-success">Dispense Complete (' + formatSmartGrams(status.current_weight || 0) + ')</span>';
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
    cameraAutomationStatusEl.innerHTML = '<span class="telemetry-tag">FLUSHING:</span> <span class="telemetry-val text-info">' + deviceLabel + ' &rarr; ' + action + tail + '</span>';
    processStatusMain.textContent = 'Flushing System';
    processStatusSub.textContent = deviceLabel + ' ' + action + tail;
  } else if (!automationRunning) {
    cameraAutomationStatusEl.innerHTML = '<span class="telemetry-tag">STATUS:</span> <span class="telemetry-val">Idle</span>';
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
            full_height=True
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