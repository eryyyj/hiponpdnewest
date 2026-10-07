"""
Camera page (/) - ShrimpSense Industrial Touchscreen HMI
- Preserves two-section right panel layout with bottom-anchored actions
- Developer Mode includes Start/Stop toggle button for Relay 1 (Water Pump)
- Manual Mode Modal with 2 tabs:
    1. "Manual Mode": Kept exactly as originally designed with no changes.
    2. "Refill Mode": Shortened and streamlined to match Tab 1's natural height,
       with clean "Start" and "Stop" buttons.
"""

from flask import Blueprint, Response

CAMERA_BODY = """
<div class="hmi-dashboard">
  <!-- Left Side: Stage, 4 Action Buttons, Status Footer -->
  <section class="hmi-panel hmi-panel-left">
    
    <!-- Process Stage Area -->
    <div class="hmi-card hmi-stage-card" id="processDisplayArea">
      <div class="stage-centerpiece">
        <div id="processStatusMain" class="stage-headline">System Ready</div>
        <div id="processStatusSub" class="stage-subhead">Waiting for cycle</div>
      </div>
    </div>

    <!-- 4 Machine Action Buttons -->
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

    <!-- Left Footer: Status + Clock -->
    <footer class="hmi-telemetry-bar">
      <div id="cameraAutomationStatus" class="telemetry-status">
        <span class="telemetry-tag">STATUS:</span> <span class="telemetry-val">Idle</span>
      </div>
      <div id="dashboardFooterClock" class="telemetry-clock">
        -- --, ----, --:--:-- --
      </div>
    </footer>

  </section>

  <!-- Right Side: Two Sections (Metrics + Bottom-Anchored Actions) -->
  <section class="hmi-panel hmi-panel-right">
    
    <!-- Information Section -->
    <div class="hmi-info-section">
      <div class="hmi-card hmi-metric-card">
        <div class="hmi-metric-label">TARGET SHRIMP COUNT</div>
        <div class="hmi-metric-value" id="displayTargetCount">None</div>
      </div>

      <div class="hmi-card hmi-metric-card">
        <div class="hmi-metric-label">COUNTED SHRIMP</div>
        <div class="hmi-metric-value" id="displayCountedShrimp">0</div>
      </div>

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

      <div id="dispenseStatusText" class="hmi-dispense-feedback"></div>
    </div>

    <!-- Action Section: Anchored to Bottom -->
    <div class="hmi-action-section">
      <button type="button" id="btnDispenseAuto" class="hmi-touch-btn hmi-btn-primary hmi-btn-dispense">
        Dispense Feed
      </button>
      <button type="button" id="btnOpenManualModal" class="hmi-touch-btn hmi-btn-secondary hmi-btn-manual">
        Manual Mode
      </button>
    </div>

  </section>
</div>

<!-- Target PL Shrimp Count Modal -->
<div class="modal" id="shrimpTargetModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered" style="max-width: 440px; width: 95%;">
    <div class="modal-content shadow border-0" style="border-radius:12px; padding:20px;">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h5 class="font-weight-bold text-dark m-0">Target Shrimp Count</h5>
        <button type="button" class="close" id="shrimpModalClose" aria-label="Close"><span>&times;</span></button>
      </div>

      <div>
        <label for="shrimpTargetInput" class="hmi-metric-label mb-1">Set Desired Count</label>
        <input type="text" inputmode="none" autocomplete="off" class="form-control text-center font-weight-bold text-dark mb-2" style="font-size:1.6rem; height:48px;" id="shrimpTargetInput" placeholder="0" readonly>

        <div class="hmi-dialog-keypad mb-3">
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
          <button type="button" class="hmi-key-btn" data-val="back">&#9003;</button>
        </div>

        <div class="d-flex" style="gap:10px;">
          <button type="button" class="btn btn-secondary font-weight-bold flex-fill py-2" id="shrimpModalCancel">Cancel</button>
          <button type="button" class="btn btn-danger font-weight-bold flex-fill py-2" id="shrimpModalSubmit">Confirm &amp; Start</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Manual Mode Modal (Tab 1 Original + Tab 2 Shortened Refill) -->
<div class="modal" id="manualFeedModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered" style="max-width: 480px; width: 95%;">
    <div class="modal-content shadow-lg border-0" style="border-radius:12px;">
      <div class="modal-header border-bottom py-2">
        <ul class="nav nav-pills card-header-pills m-0" id="manualModalTabs">
          <li class="nav-item">
            <a class="nav-link active font-weight-bold py-1 px-3" id="tabManualLink" href="javascript:void(0);">Manual Mode</a>
          </li>
          <li class="nav-item">
            <a class="nav-link font-weight-bold py-1 px-3 text-secondary" id="tabRefillLink" href="javascript:void(0);">Refill Mode</a>
          </li>
        </ul>
        <button type="button" class="close ml-auto" id="manualFeedModalClose" aria-label="Close"><span>&times;</span></button>
      </div>

      <!-- Tab 1: EXACT ORIGINAL TAB 1 (Untouched) -->
      <div class="modal-body p-3" id="tabManualContent">
        <label for="manualShrimpInput" class="text-dark font-weight-bold small text-uppercase mb-1">Enter Shrimp Count</label>
        <div class="input-group mb-2">
          <input id="manualShrimpInput" type="text" inputmode="none" autocomplete="off" class="form-control text-center font-weight-bold text-dark" style="font-size:1.5rem; height:46px;" placeholder="0">
          <div class="input-group-append">
            <button class="btn btn-outline-secondary font-weight-bold text-dark" type="button" id="btnManualClear">Clear</button>
          </div>
        </div>

        <div class="row mb-3" style="margin:0 -4px;">
          <div class="col-6 px-1">
            <div class="p-2 border rounded bg-light text-center h-100">
              <small class="text-dark d-block font-weight-bold">Biomass</small>
              <strong id="manualBiomassVal" class="text-dark" style="font-size:1.15rem;">0.00 g</strong>
            </div>
          </div>
          <div class="col-6 px-1">
            <div class="p-2 border rounded bg-light text-center h-100">
              <small class="text-dark d-block font-weight-bold">Recommended Feed</small>
              <strong id="manualFeedVal" class="text-dark" style="font-size:1.15rem;">0.00 g</strong>
            </div>
          </div>
        </div>

        <div class="d-flex" style="gap:8px;">
          <button type="button" id="btnManualDispense" class="btn btn-danger flex-grow-1 font-weight-bold py-2">
            Dispense Feed
          </button>
          <button type="button" id="btnManualStop" class="btn btn-outline-danger font-weight-bold px-4">
            Stop
          </button>
        </div>
      </div>

      <!-- Tab 2: Refill Mode (Shortened & Proportioned to match Tab 1) -->
      <div class="modal-body p-3" id="tabRefillContent" style="display:none;">
        <label class="text-dark font-weight-bold small text-uppercase mb-1">Feeder Refill Control</label>
        
        <div class="border rounded bg-light text-center mb-3 d-flex flex-column justify-content-center" style="height: 104px;">
          <small class="text-dark d-block font-weight-bold mb-1">STATUS</small>
          <div>
            <span id="refillWheelStatusPill" class="badge badge-secondary px-3 py-1 font-weight-bold" style="font-size:1.05rem;">STOPPED</span>
          </div>
        </div>

        <div class="d-flex" style="gap:8px;">
          <button type="button" id="btnRefillStartWheel" class="btn btn-success flex-grow-1 font-weight-bold py-2">
            Start
          </button>
          <button type="button" id="btnRefillStopWheel" class="btn btn-danger flex-grow-1 font-weight-bold py-2" disabled>
            Stop
          </button>
        </div>
      </div>

    </div>
  </div>
</div>

<!-- Developer Dataset Collector / CV Inspector Modal -->
<div class="modal" id="developerModeModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered" style="max-width: 1200px; width: 96%; height: 92%;">
    <div class="modal-content d-flex flex-column h-100 p-0 overflow-hidden dev-modal-window">
      
      <!-- Modal Top Bar -->
      <div class="dev-header-bar">
        <div class="d-flex align-items-center">
          <span class="status-dot" id="devRecDot"></span>
          <span class="dev-header-title ml-2">DATASET RECORDER &bull; CV INSPECTOR</span>
        </div>
        <div class="dev-header-badge">Live Hardware Controls</div>
      </div>

      <!-- Live Stream Viewport -->
      <div class="dev-stream-viewport">
        <img id="devVideoFeed" src="" alt="Developer Feed" class="dev-stream-img">
        <div id="devFeedFallback" class="text-muted text-center" style="display:none;">
          <h6 class="font-weight-bold">Camera Feed Inactive</h6>
          <small>Check camera hardware connection</small>
        </div>
      </div>

      <!-- Aesthetic Telemetry & Controls Panel -->
      <div class="dev-footer-panel">
        
        <!-- 4 Grid Telemetry Cards -->
        <div class="dev-telemetry-grid">
          <div class="dev-stat-card">
            <span class="dev-stat-label">RECORD STATUS</span>
            <div class="dev-stat-value" id="devRecordingStatusText">
              <span class="dev-pill dev-pill-idle">IDLE</span>
            </div>
          </div>
          <div class="dev-stat-card">
            <span class="dev-stat-label">RECORD DURATION</span>
            <div class="dev-stat-value font-mono" id="devRecordTimer">00:00</div>
          </div>
          <div class="dev-stat-card">
            <span class="dev-stat-label">WATER PUMP</span>
            <div class="dev-stat-value" id="devPumpStatusText">
              <span class="dev-pill dev-pill-off" id="devPumpPill">STOPPED</span>
            </div>
          </div>
          <div class="dev-stat-card">
            <span class="dev-stat-label">DISK FREE / VIDEOS</span>
            <div class="dev-stat-value font-mono-sm">
              <span id="devStorageRemaining">14.8 GB</span> <span class="text-muted mx-1">|</span> <span id="devVideosRecorded" class="text-info">0</span>
            </div>
          </div>
        </div>

        <!-- Action Control Buttons -->
        <div class="dev-actions-cluster">
          <button type="button" id="btnDevTogglePump" class="btn btn-outline-info font-weight-bold dev-action-btn">
            &#9654; Start Pump
          </button>
          
          <button type="button" id="btnDevStartRecord" class="btn btn-danger font-weight-bold dev-action-btn">
            Record Video
          </button>
          <button type="button" id="btnDevStopRecord" class="btn btn-secondary font-weight-bold dev-action-btn" disabled>
            Stop Record
          </button>
          <button type="button" id="btnExitDevMode" class="btn btn-outline-secondary font-weight-bold dev-action-btn dev-btn-exit">
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
.hmi-dashboard {
  display: flex;
  flex-direction: row;
  height: calc(100vh - 74px);
  max-height: calc(100vh - 74px);
  gap: 14px;
  padding: 16px 10px 22px 10px;
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
.hmi-panel-right {
  flex: 4.2;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.hmi-info-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.hmi-action-section {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.hmi-card {
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

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
.hmi-touch-btn:active { transform: scale(0.98); }
.hmi-action-row .hmi-touch-btn { flex: 1; height: 100%; }

.hmi-btn-primary { background: #D82B27; color: #ffffff; border-color: #b91c1c; }
.hmi-btn-primary:active { background: #991b1b; }
.hmi-btn-accent { background: #F1691F; color: #ffffff; border-color: #ea580c; }
.hmi-btn-accent:active { background: #c2410c; }
.hmi-btn-danger { background: #ffffff; color: #dc2626; border: 2px solid #ef4444; }
.hmi-btn-danger:active { background: #fee2e2; }
.hmi-btn-neutral { background: #ffffff; color: #0f172a; border: 2px solid #475569; }
.hmi-btn-neutral:active { background: #e2e8f0; }

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
.telemetry-status { font-weight: 700; color: #0f172a; }
.telemetry-tag { color: #64748b; margin-right: 4px; }
.telemetry-clock { font-family: monospace, sans-serif; font-weight: 700; color: #334155; }

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

.hmi-btn-dispense {
  width: 100%;
  height: 52px;
  font-size: 1.15rem;
}

.hmi-btn-manual {
  width: 100%;
  height: 42px;
  font-size: 0.95rem;
  background: #f8fafc;
  color: #1e293b;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  box-sizing: border-box;
}
.hmi-btn-manual:active { background: #e2e8f0; }

.hmi-dispense-feedback {
  min-height: 16px;
  font-size: 0.85rem;
  font-weight: 700;
  text-align: center;
  color: #1e293b;
  margin-top: -4px;
}

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

/* Developer Modal Styles */
.dev-modal-window {
  background: #090e17;
  border: 1px solid #1e293b;
  border-radius: 12px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
}

.dev-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px;
  height: 42px;
  background: #040711;
  border-bottom: 1px solid #1e293b;
}
.dev-header-title {
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.8px;
  color: #f1f5f9;
}
.dev-header-badge {
  font-size: 0.72rem;
  font-weight: 700;
  color: #64748b;
  background: #0f172a;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid #1e293b;
}

.dev-stream-viewport {
  flex: 1 1 auto;
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
  flex-shrink: 0;
  background: #090e17;
  border-top: 1px solid #1e293b;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  gap: 12px;
}

.dev-telemetry-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  flex: 1;
}

.dev-stat-card {
  height: 56px;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.dev-stat-label {
  font-size: 0.64rem;
  font-weight: 800;
  letter-spacing: 0.6px;
  color: #64748b;
  text-transform: uppercase;
  margin-bottom: 2px;
}
.dev-stat-value {
  font-size: 1.05rem;
  font-weight: 700;
  color: #f8fafc;
  line-height: 1.1;
  display: flex;
  align-items: center;
}
.font-mono {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.5px;
}
.font-mono-sm {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.92rem;
}

.dev-pill {
  font-size: 0.72rem;
  font-weight: 800;
  padding: 2px 7px;
  border-radius: 4px;
  letter-spacing: 0.5px;
}
.dev-pill-idle { background: #1e293b; color: #94a3b8; }
.dev-pill-rec { background: #7f1d1d; color: #fecaca; }
.dev-pill-off { background: #1e293b; color: #94a3b8; }
.dev-pill-on { background: #064e3b; color: #6ee7b7; border: 1px solid #059669; }

.dev-actions-cluster {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dev-action-btn {
  height: 56px;
  min-width: 110px;
  font-size: 0.88rem;
  border-radius: 6px;
  padding: 0 14px;
  white-space: nowrap;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}
.dev-btn-exit {
  color: #94a3b8;
  border-color: #334155;
  background: transparent;
}
.dev-btn-exit:hover {
  background: #1e293b;
  color: #ffffff;
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

// Refill Tab Controls
const tabManualLink = document.getElementById('tabManualLink');
const tabRefillLink = document.getElementById('tabRefillLink');
const tabManualContent = document.getElementById('tabManualContent');
const tabRefillContent = document.getElementById('tabRefillContent');
const btnRefillStartWheel = document.getElementById('btnRefillStartWheel');
const btnRefillStopWheel = document.getElementById('btnRefillStopWheel');
const refillWheelStatusPill = document.getElementById('refillWheelStatusPill');

const shrimpTargetModal = document.getElementById('shrimpTargetModal');
const shrimpModalClose = document.getElementById('shrimpModalClose');
const shrimpModalCancel = document.getElementById('shrimpModalCancel');
const shrimpModalSubmit = document.getElementById('shrimpModalSubmit');
const shrimpTargetInput = document.getElementById('shrimpTargetInput');
const targetKeyClear = document.getElementById('targetKeyClear');

let flushRunning = false;
let currentCounted = 0;
let refillWheelRunning = false;

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
  if (Math.abs(n) < 1.0) return n.toFixed(5) + ' g';
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
    const val = btn.getAttribute('data-val');
    if (val === 'back') {
      shrimpTargetInput.value = String(shrimpTargetInput.value || '').slice(0, -1);
    } else {
      shrimpTargetInput.value = (shrimpTargetInput.value || '') + val;
    }
  });
});
if (targetKeyClear) {
  targetKeyClear.addEventListener('click', () => { shrimpTargetInput.value = ''; });
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

function updateManualCalculator() {
  const count = parseInt(manualShrimpInput.value, 10) || 0;
  manualBiomassVal.textContent = formatSmartGrams(calcRawBiomass(count));
  manualFeedVal.textContent = formatSmartGrams(calcRawFeed(count));
}

function switchManualModalTab(activeTab) {
  if (activeTab === 'manual') {
    tabManualLink.classList.add('active');
    tabManualLink.classList.remove('text-secondary');
    tabRefillLink.classList.remove('active');
    tabRefillLink.classList.add('text-secondary');
    tabManualContent.style.display = 'block';
    tabRefillContent.style.display = 'none';
  } else {
    tabRefillLink.classList.add('active');
    tabRefillLink.classList.remove('text-secondary');
    tabManualLink.classList.remove('active');
    tabManualLink.classList.add('text-secondary');
    tabManualContent.style.display = 'none';
    tabRefillContent.style.display = 'block';
    if (typeof hideOsk === 'function') hideOsk();
  }
}

if (tabManualLink) tabManualLink.addEventListener('click', () => switchManualModalTab('manual'));
if (tabRefillLink) tabRefillLink.addEventListener('click', () => switchManualModalTab('refill'));

if (btnOpenManualModal) {
  btnOpenManualModal.addEventListener('click', () => {
    switchManualModalTab('manual');
    manualFeedModal.classList.add('show');
    updateManualCalculator();
    setTimeout(() => manualShrimpInput.focus(), 50);
  });
}

function setRefillWheelUi(running) {
  refillWheelRunning = running;
  if (!refillWheelStatusPill) return;
  if (running) {
    refillWheelStatusPill.className = 'badge badge-success px-3 py-1 font-weight-bold';
    refillWheelStatusPill.textContent = 'RUNNING';
    if (btnRefillStartWheel) btnRefillStartWheel.disabled = true;
    if (btnRefillStopWheel) btnRefillStopWheel.disabled = false;
  } else {
    refillWheelStatusPill.className = 'badge badge-secondary px-3 py-1 font-weight-bold';
    refillWheelStatusPill.textContent = 'STOPPED';
    if (btnRefillStartWheel) btnRefillStartWheel.disabled = false;
    if (btnRefillStopWheel) btnRefillStopWheel.disabled = true;
  }
}

async function requestWheelAction(action) {
  const isStart = action === 'on';
  const cmd = isStart ? 'R2ON' : 'R2OFF';
  try {
    const res = await fetch('/api/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd })
    });
    const data = await res.json();
    if (data.ok) {
      setRefillWheelUi(isStart);
    } else {
      alert('Feeder command failed: ' + (data.error || 'error'));
    }
  } catch(e) {
    alert('Failed to send feeder command');
  }
}

if (btnRefillStartWheel) btnRefillStartWheel.addEventListener('click', () => requestWheelAction('on'));
if (btnRefillStopWheel) btnRefillStopWheel.addEventListener('click', () => requestWheelAction('off'));

function closeManualModal() {
  if (refillWheelRunning) {
    requestWheelAction('off');
  }
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

/* Developer Mode Controller */
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

const btnDevTogglePump = document.getElementById('btnDevTogglePump');
const devPumpPill = document.getElementById('devPumpPill');

let devRecordInterval = null;
let devSecondsElapsed = 0;
let devIsRecording = false;
let devPumpRunning = false;

function setPumpUiState(running) {
  devPumpRunning = running;
  if (!btnDevTogglePump) return;

  if (running) {
    btnDevTogglePump.className = 'btn btn-danger font-weight-bold dev-action-btn';
    btnDevTogglePump.innerHTML = '&#9632; Stop Pump';
    if (devPumpPill) {
      devPumpPill.className = 'dev-pill dev-pill-on';
      devPumpPill.textContent = 'RUNNING';
    }
  } else {
    btnDevTogglePump.className = 'btn btn-outline-info font-weight-bold dev-action-btn';
    btnDevTogglePump.innerHTML = '&#9654; Start Pump';
    if (devPumpPill) {
      devPumpPill.className = 'dev-pill dev-pill-off';
      devPumpPill.textContent = 'STOPPED';
    }
  }
}

async function requestPumpAction(action) {
  btnDevTogglePump.disabled = true;
  try {
    const res = await fetch('/api/developer/pump', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action })
    });
    const data = await res.json();
    if (data.ok) {
      setPumpUiState(action === 'on');
    }
  } catch(e) {
    console.error('[Dev Pump] Failed to communicate:', e);
  } finally {
    btnDevTogglePump.disabled = false;
  }
}

if (btnDevTogglePump) {
  btnDevTogglePump.addEventListener('click', () => {
    requestPumpAction(devPumpRunning ? 'off' : 'on');
  });
}

function openDeveloperMode() {
  if (!devModeModal) return;
  fetch('/api/live_feed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: true })
  }).catch(() => {});
  
  if (devVideoFeed) devVideoFeed.src = '/video_feed';
  devModeModal.classList.add('show');
  devModeModal.style.display = 'flex';
  setPumpUiState(false);
  refreshDevTelemetry();
}

function closeDeveloperMode() {
  if (!devModeModal) return;
  
  if (devIsRecording) stopDevRecording();
  if (devPumpRunning) requestPumpAction('off');
  
  if (devVideoFeed) devVideoFeed.src = '';
  devModeModal.classList.remove('show');
  devModeModal.style.display = 'none';
  
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

let brandClickTimer = null;
document.addEventListener('click', (e) => {
  const toggle = e.target.closest('#secretFeedToggle');
  if (!toggle) return;

  if (window.location.pathname === '/' || window.location.pathname === '') {
    e.preventDefault();
    if (!brandClickTimer) {
      brandClickTimer = setTimeout(() => {
        brandClickTimer = null;
      }, 350);
    } else {
      clearTimeout(brandClickTimer);
      brandClickTimer = null;
      openDeveloperMode();
    }
  }
});

if (btnExitDevMode) btnExitDevMode.addEventListener('click', closeDeveloperMode);

function startDevRecording() {
  devIsRecording = true;
  devSecondsElapsed = 0;
  btnDevStartRecord.disabled = true;
  btnDevStopRecord.disabled = false;
  devRecDot.style.background = '#dc2626';
  devRecDot.style.animation = 'blinker 1s linear infinite';
  
  devRecordingStatusText.innerHTML = '<span class="dev-pill dev-pill-rec">RECORDING</span>';

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

  devRecordingStatusText.innerHTML = '<span class="dev-pill dev-pill-idle">IDLE</span>';

  fetch('/api/developer/record/stop', { method: 'POST' }).catch(() => {});
  refreshDevTelemetry();
}

if (btnDevStartRecord) btnDevStartRecord.addEventListener('click', startDevRecording);
if (btnDevStopRecord) btnDevStopRecord.addEventListener('click', stopDevRecording);

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
