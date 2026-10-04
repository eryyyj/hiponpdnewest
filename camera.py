"""
Camera page (/) - optional YOLO-free live feed plus shrimp automation.

The page contains:
    - Live Feed toggle (off by default; forced off during a count cycle)
    - LIVE indicator (only while the feed is on)
    - Start Loop button
    - Cancel Loop button
    - Flush button
    - Automation status below the buttons
    - Flush status below the automation status

Counting does NOT use the live stream. After the pump stops and gate 1
closes, the backend runs a short ByteTrack burst on stills and adds the
peak unique-ID count for that set.

The automation backend is shared with main.py. This page does NOT create
another automation manager. It only communicates with the existing API
endpoints:

    /api/automation
    /api/automation/start
    /api/automation/stop
    /api/shrimp_count
    /api/live_feed        (GET current state, POST to toggle)

Flush uses:

    /api/flush/start
    /api/flush/status

The shared render_page() function is passed into this blueprint from main.py
to avoid a circular import.
"""

from flask import Blueprint, Response


# ============================================================================
# CAMERA PAGE HTML
# ============================================================================

CAMERA_BODY = """
        <div class="card">
          <div class="card-body camera-split">

            <div class="camera-split-left">
              <div class="camera-frame" id="cameraFrame">
                <div class="camera-stage" id="cameraStage">
                  <img
                    id="videoFeed"
                    alt="Live camera feed"
                  >
                  <div class="feed-off" id="feedOffPlaceholder">
                    Live feed off &mdash; press <strong>Live Feed</strong> to check camera position.
                    The feed turns off automatically while a count cycle runs.
                  </div>
                </div>
                <div class="live-badge" id="liveBadge" style="display:none;">
                  <span class="live-dot"></span>
                  LIVE
                </div>
              </div>

              <div class="d-flex justify-content-center flex-wrap mt-1 camera-split-actions" style="gap:6px;">
                <button id="cameraLiveFeedBtn" class="btn btn-primary feeder-action-btn">&#128247; Live Feed</button>
                <button id="cameraStartLoopBtn" class="btn btn-success feeder-action-btn">&#9654; Start Loop</button>
                <button id="cameraCancelLoopBtn" class="btn btn-danger feeder-action-btn">&#10005; Cancel</button>
                <button id="cameraFlushBtn" class="btn btn-info feeder-action-btn">Flush</button>
              </div>
              <div id="cameraAutomationStatus" class="text-center mt-1 mb-0" style="min-height:18px; font-size:12px;">
                <span class="text-muted">Automation: Idle</span>
              </div>
              <p id="cameraFlushStatus" class="text-center text-muted mt-0 mb-0" style="font-size:12px;">&nbsp;</p>
            </div>

            <div class="camera-split-right" id="feedDetailsPanel">
              <div class="feed-side-title">Feed</div>
              <label for="feederCountInput" class="feed-side-label" id="feederCountLabel">To Count</label>
              <input id="feederCountInput" type="text" inputmode="none" autocomplete="off" class="form-control" placeholder="0">
              <p class="feeder-stat" id="feederTargetCountWrap" style="display:none;">Target Count<br><strong id="feederTargetCountValue">0</strong></p>
              <p class="feeder-stat">Total Biomass<br><strong id="feederBiomassValue">0.00 g</strong></p>
              <p class="feeder-stat">Feed to dispense<br><strong id="feederDispenseValue">0.00 g</strong></p>
              <p class="feeder-stat">Total current weight<br><strong id="feederCurrentWeightValue">0.00 g</strong></p>
              <button type="button" id="feederStartBtn" class="btn btn-warning btn-block feeder-action-btn">Start</button>
              <button type="button" id="feederStopBtn" class="btn btn-outline-danger btn-block feeder-action-btn mb-2">Stop</button>
              <button type="button" id="feederManualBtn" class="btn btn-secondary btn-block feeder-action-btn">Manual Feeder</button>
              <p id="feederLiveStatus" class="text-muted mt-2 mb-0" style="font-size:16px; min-height:20px;"></p>
            </div>

          </div>
        </div>
"""


# Toast container retained for compatibility with the shared page.
CAMERA_EXTRA_BODY = """
<div
  id="captureToast"
  class="alert alert-success shadow"
></div>
<div id="feederModal">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Manual Feeder</h5>
        <button type="button" class="close" id="feederModalClose" aria-label="Close"><span aria-hidden="true">&times;</span></button>
      </div>
      <div class="modal-body">
        <div class="d-flex justify-content-center flex-wrap" style="gap:10px;">
          <button type="button" id="feederManualOnBtn" class="btn btn-success feeder-action-btn">ON</button>
          <button type="button" id="feederManualOffBtn" class="btn btn-outline-secondary feeder-action-btn">OFF</button>
          <button type="button" id="feederResetBtn" class="btn btn-outline-danger feeder-action-btn">Reset</button>
        </div>
      </div>
    </div>
  </div>
</div>
"""


# ============================================================================
# CAMERA PAGE JAVASCRIPT
# ============================================================================

CAMERA_SCRIPT = r"""
// ============================================================================
// CAMERA PAGE AUTOMATION
// ============================================================================
//
// This page uses the SAME backend automation manager as main.py.
//
// It does not create another automation manager.
//
// Shared functions supplied by main.py include:
//
//     openShrimpTargetModal()
//     openFeedReadyModal()
//     DEVICE_LABELS
//
// The camera page itself owns:
//
//     Start Loop button
//     Cancel Loop button
//     Flush button
//     Automation status display
//     Flush status display
//
// ============================================================================


// ============================================================================
// ELEMENTS
// ============================================================================

const cameraStartLoopBtn =
  document.getElementById('cameraStartLoopBtn');

const cameraCancelLoopBtn =
  document.getElementById('cameraCancelLoopBtn');

const cameraFlushBtn =
  document.getElementById('cameraFlushBtn');

const cameraAutomationStatusEl =
  document.getElementById('cameraAutomationStatus');

const cameraFlushStatusEl =
  document.getElementById('cameraFlushStatus');

const cameraLiveFeedBtn =
  document.getElementById('cameraLiveFeedBtn');

const videoFeedEl =
  document.getElementById('videoFeed');

const cameraFrameEl =
  document.getElementById('cameraFrame');

const liveBadgeEl =
  document.getElementById('liveBadge');

let liveFeedOn = false;


// ============================================================================
// LOCAL STATE
// ============================================================================

let flushRunning = false;


// ============================================================================
// AUTOMATION STATUS
// ============================================================================

function renderCameraAutomationStatus(data, currentCount, detectedPeak) {

  // Keep the shared automation state synchronized.
  automationRunning = !!data.running;

  const steps = data.steps || [];

  const step =
    steps[data.current_index];

  // ------------------------------------------------------------
  // RUNNING
  // ------------------------------------------------------------

  if (automationRunning && step) {

    const deviceLabel =
      (typeof DEVICE_LABELS !== 'undefined' &&
      DEVICE_LABELS[step.device])
        ? DEVICE_LABELS[step.device]
        : step.device;

    const action =
      step.action
        ? step.action.toUpperCase()
        : '';

    const label =
      deviceLabel +
      ' \u2192 ' +
      action;

    const tail =
      data.seconds_left
        ? ' \u2014 ' + data.seconds_left + 's'
        : '';

    let progress = '';

    if (
      data.target_count != null &&
      currentCount != null
    ) {

      progress =
        ' (' +
        currentCount +
        '/' +
        data.target_count +
        ' shrimp';

      // Running peak for the set in progress (max unique IDs in one frame).
      if (detectedPeak != null) {

        progress +=
          ' - Detected ' +
          detectedPeak;

      }

      progress += ')';

    }

    cameraAutomationStatusEl.innerHTML =
      '<strong>Automation:</strong> ' +
      label +
      tail +
      progress;

  }

  // ------------------------------------------------------------
  // IDLE
  // ------------------------------------------------------------

  else {

    cameraAutomationStatusEl.innerHTML =
      '<span class="text-muted">' +
      'Automation: Idle' +
      '</span>';

  }


  updateCameraButtonStates();
}


// ============================================================================
// POLL AUTOMATION STATUS
// ============================================================================

async function pollCameraAutomationStatus() {

  try {

    const results =
      await Promise.all([
        fetch('/api/automation'),
        fetch('/api/shrimp_count')
      ]);

    const autoRes =
      results[0];

    const countRes =
      results[1];


    if (!autoRes.ok) {
      throw new Error(
        'Automation API returned HTTP ' +
        autoRes.status
      );
    }


    if (!countRes.ok) {
      throw new Error(
        'Shrimp count API returned HTTP ' +
        countRes.status
      );
    }


    const autoData =
      await autoRes.json();

    const countData =
      await countRes.json();


    renderCameraAutomationStatus(
      autoData,
      countData.count,
      countData.detected
    );

    if (typeof syncFeederAutoTarget === 'function') {
      syncFeederAutoTarget(autoData);
    }


    // ----------------------------------------------------------
    // Automation completed
    // ----------------------------------------------------------

    if (
      typeof maybeOpenFeedReadyModal === 'function'
    ) {
      maybeOpenFeedReadyModal(autoData);
    } else if (
      typeof openFeedReadyModal === 'function' &&
      (autoData.just_completed || autoData.feed_popup_pending) &&
      autoData.completed_count != null
    ) {
      openFeedReadyModal(
        autoData.completed_count,
        autoData.completed_feed_grams,
        autoData.completed_target
      );
    }

  }

  catch (error) {

    // Do not spam the screen with temporary network errors.
    // The next polling cycle will automatically retry.
    console.warn(
      '[Camera] Automation status:',
      error
    );

  }

}


// ============================================================================
// START LOOP
// ============================================================================

cameraStartLoopBtn.addEventListener(
  'click',
  () => {

    if (
      automationRunning ||
      flushRunning
    ) {
      return;
    }


    if (
      typeof openShrimpTargetModal === 'function'
    ) {

      openShrimpTargetModal();

    }

  }
);


// ============================================================================
// CANCEL LOOP
// ============================================================================

cameraCancelLoopBtn.addEventListener(
  'click',
  async () => {

    cameraCancelLoopBtn.disabled = true;

    try {

      const res =
        await fetch(
          '/api/automation/stop',
          {
            method: 'POST'
          }
        );


      const data =
        await res.json();


      if (!data.ok) {

        console.warn(
          '[Camera] Could not stop automation:',
          data.error
        );

      }

    }

    catch (error) {

      console.warn(
        '[Camera] Stop request failed:',
        error
      );

    }


    // Immediately refresh the displayed state.
    await pollCameraAutomationStatus();

  }
);


// ============================================================================
// FLUSH START
// ============================================================================

cameraFlushBtn.addEventListener(
  'click',
  async () => {

    if (
      automationRunning ||
      flushRunning
    ) {
      return;
    }


    cameraFlushBtn.disabled = true;


    try {

      const res =
        await fetch(
          '/api/flush/start',
          {
            method: 'POST'
          }
        );


      const data =
        await res.json();


      if (!data.ok) {

        cameraFlushStatusEl.textContent =
          data.error ||
          'Could not start flush';

        updateCameraButtonStates();

        return;
      }


      cameraFlushStatusEl.innerHTML =
        '<strong>Flushing...</strong>';

    }

    catch (error) {

      console.warn(
        '[Camera] Flush request failed:',
        error
      );

      cameraFlushStatusEl.textContent =
        'Could not start flush';

    }


    await pollFlushStatus();

  }
);


// ============================================================================
// RENDER FLUSH STATUS
// ============================================================================

function renderFlushStatus(status) {

  flushRunning =
    !!status.running;


  const steps =
    status.steps || [];


  const step =
    steps[status.current_index];


  // ------------------------------------------------------------
  // FLUSH RUNNING
  // ------------------------------------------------------------

  if (
    flushRunning &&
    step
  ) {

    const deviceLabel =
      (typeof DEVICE_LABELS !== 'undefined' &&
      DEVICE_LABELS[step.device])
        ? DEVICE_LABELS[step.device]
        : step.device;


    const action =
      step.action
        ? step.action.toUpperCase()
        : '';


    const label =
      deviceLabel +
      ' \u2192 ' +
      action;


    const tail =
      status.seconds_left
        ? ' \u2014 ' +
          status.seconds_left +
          's'
        : '';


    cameraFlushStatusEl.innerHTML =
      '<strong>Flushing:</strong> ' +
      label +
      tail;

  }


  // ------------------------------------------------------------
  // FLUSH IDLE
  // ------------------------------------------------------------

  else {

    cameraFlushStatusEl.innerHTML =
      '&nbsp;';

  }


  updateCameraButtonStates();

}


// ============================================================================
// POLL FLUSH STATUS
// ============================================================================

async function pollFlushStatus() {

  try {

    const res =
      await fetch(
        '/api/flush/status'
      );


    if (!res.ok) {
      throw new Error(
        'Flush API returned HTTP ' +
        res.status
      );
    }


    const status =
      await res.json();


    renderFlushStatus(status);

  }

  catch (error) {

    console.warn(
      '[Camera] Flush status:',
      error
    );

  }

}


// ============================================================================
// BUTTON STATES
// ============================================================================

function updateCameraButtonStates() {

  // ------------------------------------------------------------
  // START LOOP
  // ------------------------------------------------------------

  cameraStartLoopBtn.disabled =
    automationRunning ||
    flushRunning;


  // ------------------------------------------------------------
  // CANCEL LOOP
  // ------------------------------------------------------------

  cameraCancelLoopBtn.disabled =
    !automationRunning;


  // ------------------------------------------------------------
  // FLUSH
  // ------------------------------------------------------------

  cameraFlushBtn.disabled =
    automationRunning ||
    flushRunning;


  // ------------------------------------------------------------
  // LIVE FEED (forced off while a count cycle runs)
  // ------------------------------------------------------------

  if (cameraLiveFeedBtn) {
    cameraLiveFeedBtn.disabled = automationRunning;
    if (automationRunning && liveFeedOn) {
      applyLiveFeed(false);
    }
  }

}


// ============================================================================
// INITIAL STATE
// ============================================================================

updateCameraButtonStates();


// Get the initial automation state immediately.
pollCameraAutomationStatus();


// Get the initial flush state immediately.
pollFlushStatus();


// Get the initial live feed state immediately.
pollLiveFeedStatus();


// ============================================================================
// CONTINUOUS STATUS POLLING
// ============================================================================

setInterval(
  pollCameraAutomationStatus,
  1000
);


setInterval(
  pollFlushStatus,
  1000
);


setInterval(
  pollLiveFeedStatus,
  1000
);


setInterval(
  updateCameraButtonStates,
  500
);


// ============================================================================
// LIVE FEED TOGGLE
// ============================================================================
//
// Off by default: the <img> has no src, so the browser is not streaming.
// On: point it at /video_feed for a YOLO-free positioning preview.
// While a count cycle (automation) runs the button is disabled and the feed
// is forced off - counting happens on stills, never on the live stream.

function applyLiveFeed(enabled){
  liveFeedOn = !!enabled;
  if (cameraFrameEl){
    cameraFrameEl.classList.toggle('feed-on', liveFeedOn);
  }
  if (liveBadgeEl){
    liveBadgeEl.style.display = liveFeedOn ? 'flex' : 'none';
  }
  if (videoFeedEl){
    videoFeedEl.src = liveFeedOn ? '/video_feed' : '';
  }
  if (cameraLiveFeedBtn){
    cameraLiveFeedBtn.textContent = liveFeedOn ? '\u25A0 Stop Live Feed' : '\uD83D\uDCF7 Live Feed';
  }
}

if (cameraLiveFeedBtn){
  cameraLiveFeedBtn.addEventListener('click', async () => {
    cameraLiveFeedBtn.disabled = true;
    try{
      const res = await fetch('/api/live_feed', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({enabled: !liveFeedOn})
      });
      const data = await res.json();
      applyLiveFeed(!!data.enabled);
      if (!data.enabled && !liveFeedOn){
        cameraFlushStatusEl.textContent = 'Live view is unavailable during a count cycle.';
      }
    } catch(e){
      console.warn('[Camera] Live feed toggle failed:', e);
    }
    updateCameraButtonStates();
  });
}

async function pollLiveFeedStatus(){
  try{
    const res = await fetch('/api/live_feed');
    const data = await res.json();
    applyLiveFeed(!!data.enabled);
  } catch(e){ /* keep current state on transient errors */ }
}

applyLiveFeed(false);
"""


# ============================================================================
# BLUEPRINT FACTORY
# ============================================================================

def create_camera_blueprint(render_page):
    """
    Create the Camera Flask blueprint.

    render_page is supplied by main.py rather than imported directly.
    This keeps camera.py independent from main.py and prevents circular
    imports.
    """

    camera_bp = Blueprint(
        "camera",
        __name__
    )


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
