/**
 * Camera Viewer Application
 * 
 * Handles:
 * - Camera selection
 * - Recording playback
 * - Event timeline
 * - Video seeking to events
 */

// ==================== State ====================

const state = {
    currentCamera: null,
    cameras: [],
    recordings: [],
    events: [],
    currentRecordingIndex: -1,
    activeEventIndex: -1,
    pendingSeekTime: null,
    isConnected: false
};

// ==================== DOM Elements ====================

const elements = {
    video: document.getElementById('videoPlayer'),
    placeholder: document.getElementById('placeholder'),
    cameraTabs: document.getElementById('cameraTabs'),
    timeline: document.getElementById('timeline'),
    timelineStart: document.getElementById('timelineStart'),
    timelineEnd: document.getElementById('timelineEnd'),
    eventsList: document.getElementById('eventsList'),
    recordingsList: document.getElementById('recordingsList'),
    eventCount: document.getElementById('eventCount'),
    recordingCount: document.getElementById('recordingCount'),
    videoTitle: document.getElementById('videoTitle'),
    videoMeta: document.getElementById('videoMeta'),
    statusDot: document.getElementById('statusDot'),
    statusText: document.getElementById('statusText')
};

// ==================== API Functions ====================

const api = {
    async getCameras() {
        const resp = await fetch('/api/cameras');
        const data = await resp.json();
        return data.cameras || [];
    },
    
    async getRecordings(cameraId, source = 'shinobi') {
        const resp = await fetch(`/api/recordings/${cameraId}?source=${source}`);
        const data = await resp.json();
        return data.recordings || [];
    },
    
    async getEvents(cameraId, limit = 50) {
        const resp = await fetch(`/api/shinobi-events/${cameraId}?limit=${limit}`);
        const data = await resp.json();
        return data.events || [];
    },
    
    async getTimeline(cameraId, hours = 24) {
        const resp = await fetch(`/api/timeline/${cameraId}?hours=${hours}`);
        return await resp.json();
    },
    
    async checkHealth() {
        try {
            const resp = await fetch('/health');
            return resp.ok;
        } catch {
            return false;
        }
    }
};

// ==================== Render Functions ====================

function renderCameraTabs() {
    elements.cameraTabs.innerHTML = state.cameras.map(cam => `
        <button class="camera-tab ${cam.id === state.currentCamera ? 'active' : ''}" 
                onclick="selectCamera('${cam.id}')">
            ${cam.name}
        </button>
    `).join('');
}

function renderTimeline() {
    const recordings = state.recordings;
    
    if (recordings.length === 0) {
        elements.timeline.innerHTML = '<div class="timeline-empty">No recordings available</div>';
        elements.timelineStart.textContent = '';
        elements.timelineEnd.textContent = '';
        return;
    }
    
    // Set time labels
    const firstRec = recordings[recordings.length - 1];
    const lastRec = recordings[0];
    
    if (firstRec.start_time) {
        elements.timelineStart.textContent = formatTimeShort(firstRec.start_time);
    }
    if (lastRec.end_time || lastRec.start_time) {
        elements.timelineEnd.textContent = formatTimeShort(lastRec.end_time || lastRec.start_time);
    }
    
    // Render segments (show up to 50)
    const displayRecordings = recordings.slice(0, 50).reverse();
    const width = Math.max(100 / displayRecordings.length, 2);
    
    elements.timeline.innerHTML = displayRecordings.map((rec, i) => {
        const actualIndex = recordings.length - 1 - i;
        const hasEvents = hasEventsInRecording(rec);
        const isActive = actualIndex === state.currentRecordingIndex;
        
        return `
            <div class="timeline-segment ${hasEvents ? 'has-events' : ''} ${isActive ? 'active' : ''}" 
                 style="width: ${width}%"
                 onclick="playRecording(${actualIndex})"
                 title="${rec.filename}">
            </div>
        `;
    }).join('');
}

function renderRecordings() {
    const recordings = state.recordings;
    
    if (recordings.length === 0) {
        elements.recordingsList.innerHTML = '<div class="empty-state">No recordings found</div>';
        return;
    }
    
    elements.recordingsList.innerHTML = recordings.slice(0, 50).map((rec, i) => {
        const time = rec.start_time ? formatDateTime(rec.start_time) : rec.filename;
        const size = formatFileSize(rec.size);
        const hasEvents = hasEventsInRecording(rec);
        const isActive = i === state.currentRecordingIndex;
        
        return `
            <div class="recording-item ${isActive ? 'active' : ''}" 
                 onclick="playRecording(${i})">
                <span class="recording-icon">🎞️</span>
                <div class="recording-info">
                    <div class="recording-name">${time}</div>
                    <div class="recording-meta">
                        <span class="recording-size">${size}</span>
                        <span class="recording-source">${rec.source}</span>
                    </div>
                </div>
                ${hasEvents ? '<div class="recording-events"><div class="recording-event-dot"></div></div>' : ''}
            </div>
        `;
    }).join('');
}

function renderEvents() {
    const events = state.events;
    
    if (events.length === 0) {
        elements.eventsList.innerHTML = '<div class="empty-state">No events found</div>';
        return;
    }
    
    const icons = {
        'Motion': '🔵',
        'Person': '🟢',
        'Vehicle': '🟠',
        'Face': '🟣',
        'Intrusion': '🔴'
    };
    
    elements.eventsList.innerHTML = events.map((evt, index) => {
        const icon = icons[evt.type] || '⚪';
        const time = evt.timestamp ? formatDateTime(evt.timestamp) : 'Unknown time';
        const cls = (evt.type || 'motion').toLowerCase();
        const isActive = state.activeEventIndex === index;
        
        return `
            <div class="event-item ${isActive ? 'active' : ''}" onclick="seekToEvent('${evt.timestamp}', ${index})">
                <div class="event-icon ${cls}">${icon}</div>
                <div class="event-info">
                    <div class="event-type">${evt.type}</div>
                    <div class="event-time">${time}</div>
                </div>
                <div class="event-confidence">${evt.confidence}%</div>
            </div>
        `;
    }).join('');
}

function updateConnectionStatus(connected) {
    state.isConnected = connected;
    elements.statusDot.className = `status-dot ${connected ? 'connected' : 'disconnected'}`;
    elements.statusText.textContent = connected ? 'Connected' : 'Disconnected';
}

// ==================== Helper Functions ====================

function hasEventsInRecording(rec) {
    if (!rec.start_time || !rec.end_time) return false;
    
    const start = rec.start_time.substring(0, 19);
    const end = rec.end_time.substring(0, 19);
    
    return state.events.some(evt => {
        const t = (evt.timestamp || '').substring(0, 19);
        return t >= start && t <= end;
    });
}

function formatDateTime(isoString) {
    try {
        const d = new Date(isoString);
        return d.toLocaleString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch {
        return isoString;
    }
}

function formatTimeShort(isoString) {
    try {
        const d = new Date(isoString);
        return d.toLocaleTimeString(undefined, {
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch {
        return '';
    }
}

function formatFileSize(bytes) {
    if (!bytes) return '0 MB';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
}

// ==================== Actions ====================

async function selectCamera(cameraId) {
    state.currentCamera = cameraId;
    state.currentRecordingIndex = -1;
    
    renderCameraTabs();
    
    // Show loading states
    elements.eventsList.innerHTML = '<div class="loading">Loading events...</div>';
    elements.recordingsList.innerHTML = '<div class="loading">Loading recordings...</div>';
    elements.timeline.innerHTML = '<div class="timeline-empty">Loading...</div>';
    
    try {
        // Load data in parallel
        const [recordings, events] = await Promise.all([
            api.getRecordings(cameraId),
            api.getEvents(cameraId)
        ]);
        
        state.recordings = recordings;
        state.events = events;
        
        elements.recordingCount.textContent = recordings.length;
        elements.eventCount.textContent = events.length;
        
        renderTimeline();
        renderRecordings();
        renderEvents();
        
    } catch (error) {
        console.error('Failed to load camera data:', error);
        elements.eventsList.innerHTML = '<div class="error-state">Failed to load events</div>';
        elements.recordingsList.innerHTML = '<div class="error-state">Failed to load recordings</div>';
    }
}

function playRecording(index) {
    const rec = state.recordings[index];
    if (!rec) return;
    
    state.currentRecordingIndex = index;
    
    // Show video, hide placeholder
    elements.placeholder.classList.add('hidden');
    elements.video.classList.add('active');
    
    // Set video source
    elements.video.src = rec.url;
    
    // Handle seeking after video loads
    const pendingSeek = state.pendingSeekTime;
    state.pendingSeekTime = null;
    
    elements.video.onloadedmetadata = function() {
        console.log('Video loaded, duration:', elements.video.duration);
        
        if (pendingSeek !== null && pendingSeek !== undefined) {
            const seekTo = Math.min(pendingSeek, elements.video.duration - 1);
            console.log('Seeking to:', seekTo);
            elements.video.currentTime = seekTo;
        }
        
        elements.video.play().catch(e => console.log('Autoplay prevented:', e));
    };
    
    elements.video.onerror = function(e) {
        console.error('Video error:', e);
        elements.placeholder.classList.remove('hidden');
        elements.placeholder.innerHTML = `
            <div class="icon">❌</div>
            <div>Failed to load video</div>
            <div style="font-size: 11px; margin-top: 8px; color: var(--text-dim);">${rec.filename}</div>
        `;
    };
    
    // Update UI
    elements.videoTitle.textContent = rec.filename;
    
    if (rec.start_time && rec.end_time) {
        const start = formatTimeShort(rec.start_time);
        const end = formatTimeShort(rec.end_time);
        elements.videoMeta.textContent = `${start} - ${end}`;
    } else {
        elements.videoMeta.textContent = formatFileSize(rec.size);
    }
    
    // Re-render to update active states
    renderRecordings();
    renderTimeline();
}

function seekToEvent(timestamp, eventIndex = null) {
    if (!timestamp) return;
    
    // Mark this event as active
    if (eventIndex !== null) {
        state.activeEventIndex = eventIndex;
        renderEvents();
    }
    
    const eventTime = new Date(timestamp);
    console.log('Seeking to event:', timestamp, eventTime);
    
    // Find recording containing this event
    for (let i = 0; i < state.recordings.length; i++) {
        const rec = state.recordings[i];
        if (!rec.start_time) continue;
        
        const start = new Date(rec.start_time);
        // If no end_time, assume 15 minutes duration
        const end = rec.end_time ? new Date(rec.end_time) : new Date(start.getTime() + 15 * 60 * 1000);
        
        console.log(`Checking recording ${i}: ${rec.filename}`, {start, end, eventTime});
        
        if (eventTime >= start && eventTime <= end) {
            // Calculate seek time (seconds from start of recording)
            const seekTime = (eventTime - start) / 1000;
            console.log(`Found! Seeking to ${seekTime} seconds`);
            
            // Store seek time for after video loads
            state.pendingSeekTime = seekTime;
            
            // Play this recording
            playRecording(i);
            
            return;
        }
    }
    
    // If no exact match found, find closest recording
    let closestIndex = -1;
    let closestDiff = Infinity;
    
    for (let i = 0; i < state.recordings.length; i++) {
        const rec = state.recordings[i];
        if (!rec.start_time) continue;
        
        const start = new Date(rec.start_time);
        const diff = Math.abs(eventTime - start);
        
        if (diff < closestDiff) {
            closestDiff = diff;
            closestIndex = i;
        }
    }
    
    if (closestIndex >= 0 && closestDiff < 30 * 60 * 1000) { // Within 30 minutes
        console.log(`No exact match, playing closest recording ${closestIndex}`);
        playRecording(closestIndex);
    } else {
        alert('Recording not found for this event time');
    }
}

// ==================== Initialization ====================

async function init() {
    // Check connection
    const connected = await api.checkHealth();
    updateConnectionStatus(connected);
    
    if (!connected) {
        elements.eventsList.innerHTML = '<div class="error-state">Cannot connect to server</div>';
        elements.recordingsList.innerHTML = '<div class="error-state">Cannot connect to server</div>';
        return;
    }
    
    // Load cameras
    try {
        state.cameras = await api.getCameras();
        renderCameraTabs();
        
        // Select first camera
        if (state.cameras.length > 0) {
            await selectCamera(state.cameras[0].id);
        } else {
            elements.cameraTabs.innerHTML = '<span style="color: var(--text-dim)">No cameras configured</span>';
        }
    } catch (error) {
        console.error('Failed to initialize:', error);
        updateConnectionStatus(false);
    }
    
    // Periodic health check
    setInterval(async () => {
        const connected = await api.checkHealth();
        updateConnectionStatus(connected);
    }, 30000);
}

// ==================== Global Functions (for onclick handlers) ====================

window.selectCamera = selectCamera;
window.playRecording = playRecording;
window.seekToEvent = seekToEvent;

// Start the app
init();