// ============================================================
// UNIFIED STATE - single declaration
// ============================================================
const state = {
    // App state
    serverUrl: 'http://localhost:8766',
    shinobiUrl: 'http://localhost:8080',
    cameras: [],
    recordings: [],
    events: [],
    currentCamera: null,
    currentDate: new Date(),
    currentRecordingIndex: -1,
    activeEventIndex: -1,
    isPlaying: false,
    autoPlay: true,
    pendingSeekTime: null,

    // PTZ state
    ptzSpeed: 4,
    dayZoomIndex: 0,       // 0-5 → [1x,5x,15x,30x,60x,68x]
    digitalZoomIndex: 0,   // 0-3 → [1x,2x,4x,8x]
    brightness: 50,
    contrast: 50,
    thermalMode: 'blackhot',
    azimuth: 0,
    elevation: 0,
    jetsonOnline: false
};

const DAY_ZOOM_VALUES     = [1, 5, 15, 30, 60, 68];
const DIGITAL_ZOOM_VALUES = [1, 2, 4, 8];
const JETSON_PROXY        = 'http://localhost:8766/api/jetson';

// ============================================================
// UTILITIES
// ============================================================
const $ = id => document.getElementById(id);

const formatTime = date => {
    if (!date) return '--:--:--';
    return new Date(date).toLocaleTimeString('en-US', { hour12: false });
};

const formatDate = date => {
    return new Date(date).toLocaleDateString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric', year: 'numeric'
    });
};

const timeToPercent = (time, date) => {
    const d = new Date(time);
    const dayStart = new Date(date);
    dayStart.setHours(0, 0, 0, 0);
    return ((d - dayStart) / (24 * 60 * 60 * 1000)) * 100;
};

const percentToTime = (percent, date) => {
    const dayStart = new Date(date);
    dayStart.setHours(0, 0, 0, 0);
    return new Date(dayStart.getTime() + (percent / 100) * 24 * 60 * 60 * 1000);
};

// ============================================================
// NOTIFICATIONS
// ============================================================
function showNotification(message, type = 'info') {
    const notif = document.createElement('div');
    notif.className = `notification notification-${type}`;
    notif.textContent = message;
    document.body.appendChild(notif);
    setTimeout(() => notif.classList.add('show'), 10);
    setTimeout(() => {
        notif.classList.remove('show');
        setTimeout(() => notif.remove(), 300);
    }, 3000);
}

// ============================================================
// SURVEILLANCE API
// ============================================================
const api = {
    async health() {
        try {
            const r = await fetch(`${state.serverUrl}/health`);
            return r.ok;
        } catch { return false; }
    },
    async cameras() {
        try {
            const r = await fetch(`${state.serverUrl}/api/cameras`);
            const data = await r.json();
            return data.cameras || [];
        } catch (e) { console.error('Failed to load cameras:', e); return []; }
    },
    async recordings(cameraId) {
        try {
            const r = await fetch(`${state.serverUrl}/api/recordings/${cameraId}?source=shinobi`);
            const data = await r.json();
            return data.recordings || [];
        } catch (e) { console.error('Failed to load recordings:', e); return []; }
    },
    async events(cameraId) {
        try {
            const r = await fetch(`${state.serverUrl}/api/shinobi-events/${cameraId}?limit=500`);
            const data = await r.json();
            return data.events || [];
        } catch (e) { console.error('Failed to load events:', e); return []; }
    }
};

// ============================================================
// JETSON PTZ API
// ============================================================
async function jetsonAPI(method, endpoint, body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(`${JETSON_PROXY}${endpoint}`, opts);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

// ============================================================
// UI UPDATES
// ============================================================
function updateStatus(connected) {
    const dot  = $('statusDot');
    const text = $('statusText');
    if (dot)  dot.className  = 'status-dot ' + (connected ? 'connected' : 'disconnected');
    if (text) text.textContent = connected ? 'Connected' : 'Disconnected';
}

function updateDisplay(id, value) {
    const el = $(id);
    if (el) el.textContent = value;
}

function renderCameras() {
    const container = $('cameraTabs');
    if (!container) return;
    container.innerHTML = '';
    state.cameras.forEach(cam => {
        const btn = document.createElement('button');
        btn.className = 'camera-tab' + (cam.id === state.currentCamera ? ' active' : '');
        btn.textContent = cam.name;
        btn.onclick = () => selectCamera(cam.id);
        container.appendChild(btn);
    });
}

function renderTimeline() {
    const track           = $('timelineTrack');
    const eventsContainer = $('timelineEvents');
    const dateLabel       = $('timelineDate');
    const statsLabel      = $('timelineStats');
    if (!track || !eventsContainer) return;

    if (dateLabel) dateLabel.textContent = formatDate(state.currentDate);
    track.innerHTML = '';
    eventsContainer.innerHTML = '';

    let totalDuration = 0;
    state.recordings.forEach((rec, idx) => {
        if (!rec.start_time) return;
        const start = new Date(rec.start_time);
        const end   = rec.end_time ? new Date(rec.end_time) : new Date(start.getTime() + 15 * 60 * 1000);
        const startPercent = timeToPercent(start, state.currentDate);
        const endPercent   = timeToPercent(end, state.currentDate);
        const width = Math.max(0.1, endPercent - startPercent);
        totalDuration += (end - start);

        const segment = document.createElement('div');
        segment.className = 'timeline-segment' + (idx === state.currentRecordingIndex ? ' active' : '');
        segment.style.left  = `${Math.max(0, startPercent)}%`;
        segment.style.width = `${Math.min(width, 100 - startPercent)}%`;
        segment.title  = `${formatTime(start)} - ${formatTime(end)}\nClick to play`;
        segment.onclick = (e) => { e.stopPropagation(); playRecording(idx); };
        track.appendChild(segment);
    });

    state.events.forEach((evt, idx) => {
        if (!evt.timestamp) return;
        const percent = timeToPercent(evt.timestamp, state.currentDate);
        if (percent < 0 || percent > 100) return;
        const marker = document.createElement('div');
        const type = (evt.type || 'motion').toLowerCase();
        marker.className = `timeline-event-marker ${type}`;
        marker.style.left = `${percent}%`;
        marker.title = `${evt.type} at ${formatTime(evt.timestamp)}`;
        marker.onclick = (e) => { e.stopPropagation(); seekToEvent(idx); };
        eventsContainer.appendChild(marker);
    });

    if (statsLabel) {
        const hours = Math.floor(totalDuration / 3600000);
        const mins  = Math.floor((totalDuration % 3600000) / 60000);
        statsLabel.textContent = `${state.recordings.length} recordings (${hours}h ${mins}m) • ${state.events.length} events`;
    }
}

function renderEvents() {
    const container = $('eventsList');
    const countEl   = $('eventCount');
    if (!container) return;

    const filter   = $('eventFilter')?.value || 'all';
    let filtered   = state.events;
    if (filter !== 'all') filtered = state.events.filter(e => (e.type || '').toLowerCase() === filter);
    if (countEl) countEl.textContent = filtered.length;

    if (!filtered.length) {
        container.innerHTML = '<div class="empty-state">No events for this day</div>';
        return;
    }

    const icons = { person:'👤', car:'🚗', vehicle:'🚗', truck:'🚛', bus:'🚌', motion:'🔵', face:'😀' };
    container.innerHTML = '';
    filtered.forEach((evt) => {
        const realIdx = state.events.indexOf(evt);
        const type    = (evt.type || 'motion').toLowerCase();
        const icon    = icons[type] || '⚪';
        const active  = realIdx === state.activeEventIndex;
        const div     = document.createElement('div');
        div.className = 'event-item' + (active ? ' active' : '');
        div.innerHTML = `
            <div class="event-icon ${type}">${icon}</div>
            <div class="event-info">
                <div class="event-type">${evt.type || 'Motion'}</div>
                <div class="event-time">${formatTime(evt.timestamp)}</div>
            </div>
            <div class="event-confidence">${evt.confidence || 100}%</div>`;
        div.onclick = () => seekToEvent(realIdx);
        container.appendChild(div);
    });
}

function renderRecordings() {
    const container = $('recordingsList');
    if (!container) return;
    if (!state.recordings.length) {
        container.innerHTML = '<div class="empty-state">No recordings for this day</div>';
        return;
    }
    container.innerHTML = '';
    state.recordings.forEach((rec, idx) => {
        const active     = idx === state.currentRecordingIndex;
        const startTime  = rec.start_time ? formatTime(rec.start_time) : 'Unknown';
        const endTime    = rec.end_time   ? formatTime(rec.end_time)   : '';
        const size       = rec.size ? (rec.size / 1024 / 1024).toFixed(1) + ' MB' : '';
        const hasEvts    = hasEventsInRecording(rec);
        const div        = document.createElement('div');
        div.className    = 'recording-item' + (active ? ' active' : '');
        div.innerHTML = `
            <span class="recording-icon">🎬</span>
            <div class="recording-info">
                <div class="recording-time">${startTime}${endTime ? ' - ' + endTime : ''}</div>
                <div class="recording-meta"><span>${size}</span><span>${rec.source || 'shinobi'}</span></div>
            </div>
            ${hasEvts ? '<div class="recording-events-dot" title="Contains events"></div>' : ''}`;
        div.onclick = () => playRecording(idx);
        container.appendChild(div);
    });
}

function hasEventsInRecording(rec) {
    if (!rec.start_time || !rec.end_time) return false;
    const start = new Date(rec.start_time);
    const end   = new Date(rec.end_time);
    return state.events.some(evt => {
        const t = new Date(evt.timestamp);
        return t >= start && t <= end;
    });
}

// ============================================================
// SURVEILLANCE ACTIONS
// ============================================================
async function selectCamera(id) {
    state.currentCamera = id;
    state.currentRecordingIndex = -1;
    state.activeEventIndex = -1;
    renderCameras();
    showLoading();
    const [recordings, events] = await Promise.all([api.recordings(id), api.events(id)]);
    state.recordings = recordings.sort((a, b) => new Date(a.start_time || 0) - new Date(b.start_time || 0));
    state.events     = events.sort((a, b) => new Date(a.timestamp || 0) - new Date(b.timestamp || 0));
    renderTimeline();
    renderEvents();
    renderRecordings();
}

async function changeDate(date) {
    state.currentDate = new Date(date);
    $('datePicker').value = state.currentDate.toISOString().split('T')[0];
    if (state.currentCamera) await selectCamera(state.currentCamera);
}

function playRecording(idx) {
    const rec = state.recordings[idx];
    if (!rec) return;
    state.currentRecordingIndex = idx;
    const video       = $('videoPlayer');
    const placeholder = $('placeholder');
    if (placeholder) placeholder.classList.add('hidden');
    if (video) {
        video.classList.add('active');
        video.src = state.serverUrl + rec.url;
        video.onloadedmetadata = () => {
            if (state.pendingSeekTime != null) {
                video.currentTime = Math.min(state.pendingSeekTime, video.duration - 1);
                state.pendingSeekTime = null;
            }
            if (state.autoPlay) video.play().catch(() => {});
        };
        video.onerror = () => showNotification('Failed to load video', 'error');
    }
    renderTimeline();
    renderRecordings();
    updateTimeDisplay();
}

function seekToEvent(idx) {
    const evt = state.events[idx];
    if (!evt || !evt.timestamp) return;
    state.activeEventIndex = idx;
    renderEvents();
    const evtTime   = new Date(evt.timestamp);
    const tolerance = 5 * 60 * 1000;
    let closestRec  = null;
    let closestDist = Infinity;

    for (let i = 0; i < state.recordings.length; i++) {
        const rec = state.recordings[i];
        if (!rec.start_time) continue;
        const start = new Date(rec.start_time);
        const end   = rec.end_time ? new Date(rec.end_time) : new Date(start.getTime() + 15 * 60 * 1000);
        if (evtTime >= start && evtTime <= end) {
            state.pendingSeekTime = (evtTime - start) / 1000;
            playRecording(i);
            return;
        }
        const dist = Math.min(Math.abs(evtTime - start), Math.abs(evtTime - end));
        if (dist < closestDist && dist < tolerance) { closestDist = dist; closestRec = i; }
    }

    if (closestRec !== null) {
        const rec   = state.recordings[closestRec];
        const start = new Date(rec.start_time);
        state.pendingSeekTime = Math.max(0, (evtTime - start) / 1000);
        showNotification(`Playing closest recording (${Math.round(closestDist / 1000)}s offset)`, 'info');
        playRecording(closestRec);
        return;
    }
    showNotification('No recording found for this event', 'error');
}

function showLoading() {
    const events     = $('eventsList');
    const recordings = $('recordingsList');
    if (events)     events.innerHTML     = '<div class="loading"><div class="loading-spinner"></div><div class="loading-text">Loading events...</div></div>';
    if (recordings) recordings.innerHTML = '<div class="loading"><div class="loading-spinner"></div><div class="loading-text">Loading recordings...</div></div>';
}

function updateTimeDisplay() {
    const video   = $('videoPlayer');
    const display = $('currentTimeDisplay');
    const overlay = $('overlayTime');
    const cursor  = $('timelineCursor');
    if (!video || !display) return;
    const rec = state.recordings[state.currentRecordingIndex];
    if (!rec || !rec.start_time) { display.textContent = '--:--:--'; return; }
    const startTime   = new Date(rec.start_time);
    const currentTime = new Date(startTime.getTime() + video.currentTime * 1000);
    display.textContent = formatTime(currentTime);
    if (overlay) overlay.textContent = formatTime(currentTime);
    if (cursor) {
        cursor.style.left = `${timeToPercent(currentTime, state.currentDate)}%`;
        cursor.classList.add('active');
    }
}

// ============================================================
// TIMELINE INTERACTION
// ============================================================
function setupTimelineInteraction() {
    const container = document.querySelector('.timeline-container');
    const hoverEl   = $('timelineHover');
    const hoverTime = $('hoverTime');
    if (!container) return;
    container.addEventListener('mousemove', (e) => {
        const rect    = container.getBoundingClientRect();
        const percent = ((e.clientX - rect.left) / rect.width) * 100;
        const time    = percentToTime(percent, state.currentDate);
        if (hoverEl)   hoverEl.style.left  = `${percent}%`;
        if (hoverTime) hoverTime.textContent = formatTime(time);
    });
    container.addEventListener('click', (e) => {
        if (e.target.classList.contains('timeline-segment') ||
            e.target.classList.contains('timeline-event-marker')) return;
        const rect      = container.getBoundingClientRect();
        const percent   = ((e.clientX - rect.left) / rect.width) * 100;
        const clickTime = percentToTime(percent, state.currentDate);
        for (let i = 0; i < state.recordings.length; i++) {
            const rec = state.recordings[i];
            if (!rec.start_time) continue;
            const start = new Date(rec.start_time);
            const end   = rec.end_time ? new Date(rec.end_time) : new Date(start.getTime() + 15 * 60 * 1000);
            if (clickTime >= start && clickTime <= end) {
                state.pendingSeekTime = (clickTime - start) / 1000;
                playRecording(i);
                return;
            }
        }
        showNotification('No recording at this time', 'warning');
    });
}

// ============================================================
// SETTINGS
// ============================================================
function openSettings() {
    $('serverUrlInput').value  = state.serverUrl;
    $('shinobiUrlInput').value = state.shinobiUrl;
    $('autoPlayCheck').checked = state.autoPlay;
    $('settingsModal').classList.add('open');
}

function closeSettings() {
    $('settingsModal').classList.remove('open');
}

async function saveSettings() {
    state.serverUrl = $('serverUrlInput')?.value || 'http://localhost:8766';
    state.shinobiUrl = $('shinobiUrlInput')?.value || 'http://localhost:8080';
    state.autoPlay   = $('autoPlayCheck')?.checked ?? true;
    if (window.electronAPI) {
        await window.electronAPI.setSettings({
            serverUrl:   state.serverUrl,
            shinobiUrl:  state.shinobiUrl,
            alwaysOnTop: $('alwaysOnTopCheck')?.checked ?? false,
            autoPlay:    state.autoPlay
        });
    }
    closeSettings();
    showNotification('Settings saved', 'success');
    init();
}

// ============================================================
// JETSON PTZ CONTROLS
// ============================================================
async function setPTZDirection(direction, start) {
    try {
        await jetsonAPI('POST', '/ptz/direction', { direction, start });
    } catch { /* Jetson offline, silent fail */ }
}

function setPTZStatus(text) {
    updateDisplay('ptzStatusText', text);
}

function bindPTZButtons() {
    const ptzMap = {
        '[data-ptz="up"]':         'ptz_up',
        '[data-ptz="down"]':       'ptz_down',
        '[data-ptz="left"]':       'ptz_left',
        '[data-ptz="right"]':      'ptz_right',
        '[data-ptz="middle"]':     'ptz_middle',
        '[data-ptz="focus-near"]': 'near_focus',
        '[data-ptz="focus-far"]':  'far_focus',
    };
    Object.entries(ptzMap).forEach(([selector, direction]) => {
        const btn = document.querySelector(selector);
        if (!btn) return;
        btn.addEventListener('mousedown', () => {
            setPTZDirection(direction, true);
            setPTZStatus(`Moving ${direction.replace('ptz_', '')}...`);
            btn.classList.add('pressed');
        });
        btn.addEventListener('mouseup', () => {
            setPTZDirection(direction, false);
            setPTZStatus('Ready');
            btn.classList.remove('pressed');
        });
        btn.addEventListener('mouseleave', () => {
            setPTZDirection(direction, false);
            btn.classList.remove('pressed');
        });
    });
}

async function stepDayZoom(direction) {
    if (direction === 'up') state.dayZoomIndex = Math.min(DAY_ZOOM_VALUES.length - 1, state.dayZoomIndex + 1);
    else                    state.dayZoomIndex = Math.max(0, state.dayZoomIndex - 1);
    const value = DAY_ZOOM_VALUES[state.dayZoomIndex];
    updateDisplay('dayZoomValue', `${value}x`);
    try { await jetsonAPI('POST', '/zoom/day', { direction }); }
    catch { showNotification('Zoom failed', 'error'); }
}

async function stepDigitalZoom(direction) {
    if (direction === 'up') state.digitalZoomIndex = Math.min(DIGITAL_ZOOM_VALUES.length - 1, state.digitalZoomIndex + 1);
    else                    state.digitalZoomIndex = Math.max(0, state.digitalZoomIndex - 1);
    const value = DIGITAL_ZOOM_VALUES[state.digitalZoomIndex];
    updateDisplay('digitalZoomValue', `${value}x`);
    try { await jetsonAPI('POST', '/zoom/digital', { direction }); }
    catch { showNotification('Zoom failed', 'error'); }
}

async function setPTZSpeed(speed) {
    state.ptzSpeed = speed;
    document.querySelectorAll('[data-ptz-speed]').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.ptzSpeed) === speed);
    });
    try { await jetsonAPI('POST', '/speed', { speed }); }
    catch { /* silent */ }
}

async function adjustBrightness(direction) {
    state.brightness = direction === 'up' ? Math.min(100, state.brightness + 10) : Math.max(0, state.brightness - 10);
    updateDisplay('brightnessValue', state.brightness);
    try { await jetsonAPI('POST', '/image/brightness', { direction }); }
    catch { /* silent */ }
}

async function adjustContrast(direction) {
    state.contrast = direction === 'up' ? Math.min(100, state.contrast + 10) : Math.max(0, state.contrast - 10);
    updateDisplay('contrastValue', state.contrast);
    try { await jetsonAPI('POST', '/image/contrast', { direction }); }
    catch { /* silent */ }
}

async function setThermalMode(mode) {
    state.thermalMode = mode;
    document.querySelectorAll('[data-thermal]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.thermal === mode);
    });
    try { await jetsonAPI('POST', '/image/thermal-mode', { mode }); }
    catch { /* silent */ }
}

async function measureRange() {
    const btn     = $('measureRangeBtn');
    const display = $('distanceDisplay');
    if (btn) btn.disabled = true;
    if (display) display.textContent = '...';
    setPTZStatus('Measuring...');
    try {
        const result   = await jetsonAPI('POST', '/rangefinder/measure');
        const distance = result.distance;
        if (display) display.textContent = distance != null ? `${parseFloat(distance).toFixed(1)} m` : '-- m';
        if (distance != null) showNotification(`Distance: ${parseFloat(distance).toFixed(1)}m`, 'success');
    } catch {
        if (display) display.textContent = 'Error';
        showNotification('Range finder failed', 'error');
    } finally {
        if (btn) btn.disabled = false;
        setPTZStatus('Ready');
    }
}

async function checkJetsonStatus() {
    try {
        const result = await jetsonAPI('GET', '/status');
        state.jetsonOnline = result.online;
        const dot  = document.querySelector('#jetsonStatus .status-dot');
        const text = document.querySelector('#jetsonStatus .status-text');
        if (dot)  dot.className   = result.online ? 'status-dot online' : 'status-dot offline';
        if (text) text.textContent = result.online ? 'Online' : 'Offline';
    } catch {
        state.jetsonOnline = false;
        const dot  = document.querySelector('#jetsonStatus .status-dot');
        const text = document.querySelector('#jetsonStatus .status-text');
        if (dot)  dot.className   = 'status-dot offline';
        if (text) text.textContent = 'Offline';
    }
}

let telemetryInterval = null;
function startTelemetryPolling() {
    if (telemetryInterval) clearInterval(telemetryInterval);
    telemetryInterval = setInterval(async () => {
        try {
            const data = await jetsonAPI('GET', '/telemetry');
            updateDisplay('azimuthDisplay',   (data.azimuth_degrees   || 0).toFixed(1) + '°');
            updateDisplay('elevationDisplay', (data.elevation_degrees || 0).toFixed(1) + '°');
            if (data.distance != null) updateDisplay('distanceDisplay', data.distance.toFixed(1) + ' m');
        } catch { /* Jetson offline */ }
    }, 1000);
}

function bindPTZPanel() {
    // D-pad
    bindPTZButtons();

    // PTZ Speed (uses data-ptz-speed to avoid conflict with video playback speed)
    document.querySelectorAll('[data-ptz-speed]').forEach(btn => {
        btn.addEventListener('click', () => setPTZSpeed(parseInt(btn.dataset.ptzSpeed)));
    });

    // Zoom
    document.querySelector('[data-day-zoom="up"]')?.addEventListener('click',     () => stepDayZoom('up'));
    document.querySelector('[data-day-zoom="down"]')?.addEventListener('click',   () => stepDayZoom('down'));
    document.querySelector('[data-digital-zoom="up"]')?.addEventListener('click', () => stepDigitalZoom('up'));
    document.querySelector('[data-digital-zoom="down"]')?.addEventListener('click',() => stepDigitalZoom('down'));

    // Image
    document.querySelector('[data-brightness="up"]')?.addEventListener('click',   () => adjustBrightness('up'));
    document.querySelector('[data-brightness="down"]')?.addEventListener('click', () => adjustBrightness('down'));
    document.querySelector('[data-contrast="up"]')?.addEventListener('click',     () => adjustContrast('up'));
    document.querySelector('[data-contrast="down"]')?.addEventListener('click',   () => adjustContrast('down'));

    // Thermal
    document.querySelectorAll('[data-thermal]').forEach(btn => {
        btn.addEventListener('click', () => setThermalMode(btn.dataset.thermal));
    });

    // Range finder
    $('measureRangeBtn')?.addEventListener('click', measureRange);

    // Collapse toggle
    $('ptzCollapseBtn')?.addEventListener('click', () => {
        const body   = $('ptzPanelBody');
        const btn    = $('ptzCollapseBtn');
        const hidden = body.classList.toggle('hidden');
        btn.textContent = hidden ? '▶' : '▼';
    });
}

function bindKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'SELECT') return;
        switch (e.key) {
            case 'ArrowUp':    e.preventDefault(); setPTZDirection('ptz_up', true);    setPTZStatus('Moving up...');    break;
            case 'ArrowDown':  e.preventDefault(); setPTZDirection('ptz_down', true);  setPTZStatus('Moving down...');  break;
            case 'ArrowLeft':  e.preventDefault(); setPTZDirection('ptz_left', true);  setPTZStatus('Moving left...');  break;
            case 'ArrowRight': e.preventDefault(); setPTZDirection('ptz_right', true); setPTZStatus('Moving right...'); break;
            case 'PageUp':     e.preventDefault(); stepDayZoom('up');   break;
            case 'PageDown':   e.preventDefault(); stepDayZoom('down'); break;
        }
    });
    document.addEventListener('keyup', (e) => {
        const dirs = { ArrowUp:'ptz_up', ArrowDown:'ptz_down', ArrowLeft:'ptz_left', ArrowRight:'ptz_right' };
        if (dirs[e.key]) { setPTZDirection(dirs[e.key], false); setPTZStatus('Ready'); }
    });
}

// ============================================================
// INIT
// ============================================================
async function init() {
    console.log('Initializing Surveillance Viewer...');
    if (window.electronAPI) {
        try {
            const settings   = await window.electronAPI.getSettings();
            state.serverUrl  = settings.serverUrl  || state.serverUrl;
            state.shinobiUrl = settings.shinobiUrl || state.shinobiUrl;
            state.autoPlay   = settings.autoPlay   ?? true;
        } catch (e) { console.log('Could not load settings:', e); }
    }

    state.currentDate    = new Date();
    $('datePicker').value = state.currentDate.toISOString().split('T')[0];

    const ok = await api.health();
    updateStatus(ok);
    if (!ok) {
        $('eventsList').innerHTML     = '<div class="error-state">⚠️ Server offline<br><small>Start webhook_receiver.py on port 8766</small></div>';
        $('recordingsList').innerHTML = '<div class="error-state">Server offline</div>';
        showNotification('Server offline - check webhook_receiver.py', 'error');
        return;
    }

    state.cameras = await api.cameras();
    renderCameras();
    if (state.cameras.length > 0) {
        await selectCamera(state.cameras[0].id);
        showNotification(`Loaded ${state.cameras.length} camera(s)`, 'success');
    } else {
        showNotification('No cameras configured', 'warning');
    }
}

// ============================================================
// EVENT LISTENERS
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    // Settings
    $('settingsBtn')?.addEventListener('click', openSettings);
    $('closeSettings')?.addEventListener('click', closeSettings);
    $('cancelSettings')?.addEventListener('click', closeSettings);
    $('saveSettings')?.addEventListener('click', saveSettings);
    $('settingsModal')?.addEventListener('click', (e) => { if (e.target.id === 'settingsModal') closeSettings(); });

    // Date nav
    $('prevDay')?.addEventListener('click', () => { const d = new Date(state.currentDate); d.setDate(d.getDate() - 1); changeDate(d); });
    $('nextDay')?.addEventListener('click', () => { const d = new Date(state.currentDate); d.setDate(d.getDate() + 1); changeDate(d); });
    $('todayBtn')?.addEventListener('click', () => changeDate(new Date()));
    $('datePicker')?.addEventListener('change', (e) => changeDate(new Date(e.target.value)));

    // Refresh
    $('refreshBtn')?.addEventListener('click', () => { if (state.currentCamera) { selectCamera(state.currentCamera); showNotification('Refreshing...', 'info'); } });

    // Sidebar tabs
    document.querySelectorAll('.sidebar-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const target = tab.dataset.tab;
            $('eventsPanel').classList.toggle('hidden', target !== 'events');
            $('recordingsPanel').classList.toggle('hidden', target !== 'recordings');
            $('ptzPanel').classList.toggle('hidden', target !== 'ptz');
        });
    });

    // Event filter
    $('eventFilter')?.addEventListener('change', renderEvents);

    // Playback controls
    $('skipBackBtn')?.addEventListener('click', () => {
        const v = $('videoPlayer'); if (v) v.currentTime = Math.max(0, v.currentTime - 30);
    });
    $('skipForwardBtn')?.addEventListener('click', () => {
        const v = $('videoPlayer'); if (v) v.currentTime = Math.min(v.duration, v.currentTime + 30);
    });
    $('playPauseBtn')?.addEventListener('click', () => {
        const v = $('videoPlayer');
        if (!v) return;
        if (v.paused) { v.play(); $('playPauseBtn').querySelector('.play-icon')?.classList.add('hidden'); $('playPauseBtn').querySelector('.pause-icon')?.classList.remove('hidden'); }
        else          { v.pause(); $('playPauseBtn').querySelector('.play-icon')?.classList.remove('hidden'); $('playPauseBtn').querySelector('.pause-icon')?.classList.add('hidden'); }
    });
    $('playbackSpeed')?.addEventListener('change', (e) => { const v = $('videoPlayer'); if (v) v.playbackRate = parseFloat(e.target.value); });

    // Video events
    $('videoPlayer')?.addEventListener('timeupdate', updateTimeDisplay);
    $('videoPlayer')?.addEventListener('play',  () => { state.isPlaying = true; });
    $('videoPlayer')?.addEventListener('pause', () => { state.isPlaying = false; });
    $('videoPlayer')?.addEventListener('ended', () => {
        if (state.currentRecordingIndex < state.recordings.length - 1) playRecording(state.currentRecordingIndex + 1);
    });

    // Timeline
    setupTimelineInteraction();

    // Electron IPC
    if (window.electronAPI) {
        window.electronAPI.onOpenSettings?.(() => openSettings());
        window.electronAPI.onRefreshData?.(() => state.currentCamera && selectCamera(state.currentCamera));
        window.electronAPI.onSelectCamera?.(i => state.cameras[i] && selectCamera(state.cameras[i].id));
    }

    // PTZ Panel
    bindPTZPanel();
    bindKeyboardShortcuts();
    checkJetsonStatus();
    setInterval(checkJetsonStatus, 5000);
    startTelemetryPolling();

    // Mark speed 4 as default active
    document.querySelector('[data-ptz-speed="4"]')?.classList.add('active');

    init();
});

// Health check
setInterval(async () => { updateStatus(await api.health()); }, 30000);