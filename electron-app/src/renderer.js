// State
const state = {
    serverUrl: 'http://localhost:8766',
    cameras: [],
    recordings: [],
    events: [],
    currentCamera: null,
    currentRecordingIndex: -1,
    activeEventIndex: -1,
    pendingSeekTime: null
};

// Helper
function $(id) {
    const el = document.getElementById(id);
    if (!el) console.error('Element not found:', id);
    return el;
}

// API
const api = {
    async health() {
        try {
            console.log('Checking health at:', state.serverUrl);
            const r = await fetch(`${state.serverUrl}/health`);
            console.log('Health response:', r.ok);
            return r.ok;
        } catch (e) {
            console.error('Health check failed:', e);
            return false;
        }
    },
    async cameras() {
        try {
            console.log('Fetching cameras...');
            const r = await fetch(`${state.serverUrl}/api/cameras`);
            const data = await r.json();
            console.log('Cameras:', data);
            return data.cameras || [];
        } catch (e) {
            console.error('Cameras fetch failed:', e);
            return [];
        }
    },
    async recordings(cam) {
        try {
            console.log('Fetching recordings for:', cam);
            const r = await fetch(`${state.serverUrl}/api/recordings/${cam}?source=shinobi`);
            const data = await r.json();
            console.log('Recordings:', data);
            return data.recordings || [];
        } catch (e) {
            console.error('Recordings fetch failed:', e);
            return [];
        }
    },
    async events(cam) {
        try {
            console.log('Fetching events for:', cam);
            const r = await fetch(`${state.serverUrl}/api/shinobi-events/${cam}?limit=50`);
            const data = await r.json();
            console.log('Events:', data);
            return data.events || [];
        } catch (e) {
            console.error('Events fetch failed:', e);
            return [];
        }
    }
};

// Render functions
function renderCameras() {
    console.log('Rendering cameras:', state.cameras);
    const container = $('cameraTabs');
    if (!container) return;
    
    container.innerHTML = '';
    state.cameras.forEach(c => {
        const btn = document.createElement('button');
        btn.className = 'camera-tab' + (c.id === state.currentCamera ? ' active' : '');
        btn.textContent = c.name;
        btn.addEventListener('click', () => {
            console.log('Camera clicked:', c.id);
            selectCamera(c.id);
        });
        container.appendChild(btn);
    });
}

function renderTimeline() {
    const container = $('timeline');
    if (!container) return;
    
    const recs = state.recordings.slice(0, 50);
    if (!recs.length) {
        container.innerHTML = '<div style="color:#8b949e;padding:8px;text-align:center">No recordings</div>';
        return;
    }
    
    container.innerHTML = '';
    recs.forEach((r, i) => {
        const div = document.createElement('div');
        div.className = 'timeline-segment';
        if (hasEventsIn(r)) div.classList.add('has-events');
        if (i === state.currentRecordingIndex) div.classList.add('active');
        div.addEventListener('click', () => {
            console.log('Timeline segment clicked:', i);
            playRecording(i);
        });
        container.appendChild(div);
    });
}

function renderRecordings() {
    const container = $('recordingsList');
    if (!container) return;
    
    const recs = state.recordings;
    if (!recs.length) {
        container.innerHTML = '<div class="empty-state">No recordings</div>';
        return;
    }
    
    container.innerHTML = '';
    recs.slice(0, 50).forEach((r, i) => {
        const time = r.start_time ? new Date(r.start_time).toLocaleString() : r.filename;
        const size = r.size ? (r.size / 1024 / 1024).toFixed(1) + ' MB' : '';
        const active = i === state.currentRecordingIndex;
        const hasEvents = hasEventsIn(r);
        
        const div = document.createElement('div');
        div.className = 'recording-item' + (active ? ' active' : '');
        div.innerHTML = `
            <span>🎞️</span>
            <div class="recording-info">
                <div class="recording-name">${time}</div>
                <div class="recording-meta"><span>${size}</span><span>${r.source || 'shinobi'}</span></div>
            </div>
            ${hasEvents ? '<div class="event-dot"></div>' : ''}
        `;
        div.addEventListener('click', () => {
            console.log('Recording clicked:', i, r.filename);
            playRecording(i);
        });
        container.appendChild(div);
    });
}

function renderEvents() {
    const container = $('eventsList');
    if (!container) return;
    
    const evts = state.events;
    if (!evts.length) {
        container.innerHTML = '<div class="empty-state">No events</div>';
        return;
    }
    
    const icons = { Motion: '🔵', Person: '🟢', Vehicle: '🟠', Face: '🟣', Intrusion: '🔴' };
    
    container.innerHTML = '';
    evts.forEach((e, i) => {
        const icon = icons[e.type] || '⚪';
        const time = e.timestamp ? new Date(e.timestamp).toLocaleString() : '';
        const active = i === state.activeEventIndex;
        
        const div = document.createElement('div');
        div.className = 'event-item' + (active ? ' active' : '');
        div.innerHTML = `
            <div class="event-icon">${icon}</div>
            <div class="event-info">
                <div class="event-type">${e.type}</div>
                <div class="event-time">${time}</div>
            </div>
            <div class="event-confidence">${e.confidence || 100}%</div>
        `;
        div.addEventListener('click', () => {
            console.log('Event clicked:', i, e.timestamp);
            seekToEvent(e.timestamp, i);
        });
        container.appendChild(div);
    });
}

function hasEventsIn(rec) {
    if (!rec.start_time || !rec.end_time) return false;
    const s = rec.start_time.slice(0, 19);
    const e = rec.end_time.slice(0, 19);
    return state.events.some(ev => {
        const t = (ev.timestamp || '').slice(0, 19);
        return t >= s && t <= e;
    });
}

function updateStatus(connected) {
    const dot = $('statusDot');
    const text = $('statusText');
    if (dot) dot.className = 'status-dot ' + (connected ? 'connected' : 'disconnected');
    if (text) text.textContent = connected ? 'Connected' : 'Disconnected';
}

// Actions
async function selectCamera(id) {
    console.log('Selecting camera:', id);
    state.currentCamera = id;
    state.currentRecordingIndex = -1;
    state.activeEventIndex = -1;
    renderCameras();
    
    const eventsList = $('eventsList');
    const recordingsList = $('recordingsList');
    if (eventsList) eventsList.innerHTML = '<div class="loading">Loading...</div>';
    if (recordingsList) recordingsList.innerHTML = '<div class="loading">Loading...</div>';
    
    try {
        const [recordings, events] = await Promise.all([
            api.recordings(id),
            api.events(id)
        ]);
        
        state.recordings = recordings;
        state.events = events;
        
        const eventCount = $('eventCount');
        const recordingCount = $('recordingCount');
        if (eventCount) eventCount.textContent = state.events.length;
        if (recordingCount) recordingCount.textContent = state.recordings.length;
        
        renderTimeline();
        renderRecordings();
        renderEvents();
    } catch (e) {
        console.error('Error loading camera data:', e);
    }
}

function playRecording(i) {
    console.log('Playing recording:', i);
    const rec = state.recordings[i];
    if (!rec) {
        console.error('Recording not found at index:', i);
        return;
    }
    
    state.currentRecordingIndex = i;
    
    const placeholder = $('placeholder');
    const video = $('videoPlayer');
    
    if (placeholder) placeholder.classList.add('hidden');
    
    const videoUrl = state.serverUrl + rec.url;
    console.log('Video URL:', videoUrl);
    
    if (video) {
        video.src = videoUrl;
        
        const seek = state.pendingSeekTime;
        state.pendingSeekTime = null;
        
        video.onloadedmetadata = () => {
            console.log('Video loaded, duration:', video.duration);
            if (seek != null) {
                console.log('Seeking to:', seek);
                video.currentTime = Math.min(seek, video.duration - 1);
            }
            video.play().catch(e => console.log('Autoplay blocked:', e));
        };
        
        video.onerror = (e) => {
            console.error('Video error:', e, video.error);
        };
    }
    
    const videoInfo = $('videoInfo');
    if (videoInfo) videoInfo.textContent = rec.filename;
    
    renderRecordings();
    renderTimeline();
}

function seekToEvent(ts, idx) {
    console.log('Seeking to event:', ts, idx);
    if (!ts) return;
    
    state.activeEventIndex = idx;
    renderEvents();
    
    const evtTime = new Date(ts);
    for (let i = 0; i < state.recordings.length; i++) {
        const r = state.recordings[i];
        if (!r.start_time) continue;
        const start = new Date(r.start_time);
        const end = r.end_time ? new Date(r.end_time) : new Date(start.getTime() + 15 * 60000);
        if (evtTime >= start && evtTime <= end) {
            state.pendingSeekTime = (evtTime - start) / 1000;
            console.log('Found recording, seek time:', state.pendingSeekTime);
            playRecording(i);
            return;
        }
    }
    console.log('No recording found for event');
}

// Settings
function openSettings() {
    console.log('Opening settings');
    const modal = $('settingsModal');
    const input = $('serverUrlInput');
    if (input) input.value = state.serverUrl;
    if (modal) modal.classList.add('open');
}

function closeSettings() {
    console.log('Closing settings');
    const modal = $('settingsModal');
    if (modal) modal.classList.remove('open');
}

async function saveSettings() {
    console.log('Saving settings');
    const input = $('serverUrlInput');
    state.serverUrl = (input ? input.value.trim() : '') || 'http://localhost:8766';
    
    if (window.electronAPI) {
        const checkbox = $('alwaysOnTopCheck');
        await window.electronAPI.setSettings({
            serverUrl: state.serverUrl,
            alwaysOnTop: checkbox ? checkbox.checked : false
        });
    }
    
    closeSettings();
    init();
}

// Init
async function init() {
    console.log('=== INITIALIZING ===');
    
    if (window.electronAPI) {
        try {
            state.serverUrl = await window.electronAPI.getServerUrl();
            console.log('Server URL from settings:', state.serverUrl);
        } catch (e) {
            console.log('Could not get server URL from settings:', e);
        }
    }
    
    const ok = await api.health();
    updateStatus(ok);
    
    if (!ok) {
        console.error('Server not available');
        const eventsList = $('eventsList');
        const recordingsList = $('recordingsList');
        if (eventsList) eventsList.innerHTML = '<div class="error-state">Server offline<br><small>Run webhook_receiver.py</small></div>';
        if (recordingsList) recordingsList.innerHTML = '<div class="error-state">Server offline</div>';
        return;
    }
    
    state.cameras = await api.cameras();
    console.log('Loaded cameras:', state.cameras);
    
    renderCameras();
    
    if (state.cameras.length > 0) {
        await selectCamera(state.cameras[0].id);
    }
}

// Setup event listeners when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, setting up event listeners');
    
    const settingsBtn = $('settingsBtn');
    const closeSettingsBtn = $('closeSettings');
    const cancelSettingsBtn = $('cancelSettings');
    const saveSettingsBtn = $('saveSettings');
    const refreshBtn = $('refreshBtn');
    const settingsModal = $('settingsModal');
    
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            console.log('Settings button clicked');
            openSettings();
        });
    }
    
    if (closeSettingsBtn) {
        closeSettingsBtn.addEventListener('click', closeSettings);
    }
    
    if (cancelSettingsBtn) {
        cancelSettingsBtn.addEventListener('click', closeSettings);
    }
    
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', saveSettings);
    }
    
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            console.log('Refresh clicked');
            if (state.currentCamera) selectCamera(state.currentCamera);
        });
    }
    
    if (settingsModal) {
        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) closeSettings();
        });
    }
    
    // Electron IPC
    if (window.electronAPI) {
        window.electronAPI.onOpenSettings(() => openSettings());
        window.electronAPI.onRefreshData(() => state.currentCamera && selectCamera(state.currentCamera));
        window.electronAPI.onSelectCamera(i => state.cameras[i] && selectCamera(state.cameras[i].id));
    }
    
    // Start
    init();
});

// Health check interval
setInterval(async () => {
    const ok = await api.health();
    updateStatus(ok);
}, 30000);