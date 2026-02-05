# Camera Recording System - Complete Flow Documentation

## Overview

This is an event-driven camera recording system that integrates with Shinobi NVR to provide intelligent video storage and management. The system receives events from various sources (ONVIF cameras, AI detectors, manual triggers) and selectively saves recordings to local storage while maintaining continuous recording on Shinobi.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  ┌──────────┐      RTSP        ┌──────────┐     continuous      Server │
│  │ IP       │ ───────────────▶ │ SHINOBI  │ ──────────────────▶ Storage│
│  │ Cameras  │                  │ NVR      │     recording              │
│  └──────────┘                  └──────────┘                            │
│       │                              │                                  │
│       │ External Events              │ Motion API trigger              │
│       │ (ONVIF, AI, Manual)          ▼                                  │
│       │                    ┌─────────────────────────────────┐         │
│       │                    │         YOUR PC                 │         │
│       │                    │                                 │         │
│       │                    │   permanent_recordings/         │         │
│       │                    │   ├── cam1/                     │         │
│       │                    │   │   └── 20240115_143022/      │         │
│       │                    │   │       ├── video.mp4         │ Event   │
│       │                    │   │       └── event.json        │ clips   │
│       │                    │   └── cam2/                     │ only    │
│       │                    │                                 │         │
│       ▼                    │         │                       │         │
│  ┌──────────┐              │         │                       │         │
│  │  main.py │   webhook    │         │                       │         │
│  │ (Port    │ ◄────────────┼────┐    │                       │         │
│  │  8765)  │   events     │    │    │                       │         │
│  └──────────┘              │    │    │                       │         │
│                            │    │    │                       │         │
│                            │    │    │ Web UI & Timeline     │         │
│                            │    │    │                       │         │
│                            │    └────▶ webhook_receiver.py   │         │
│                            │              (Port 8766)        │         │
│                            │                                 │         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. Shinobi NVR (External Server)
**Location:** Runs separately on `http://localhost:8080`
**Purpose:** Handles continuous video recording and streaming

**Responsibilities:**
- Connects to RTSP camera streams
- Records video continuously (24/7)
- Stores recordings on Shinobi server
- Provides HLS streams for live viewing
- Receives motion API triggers to mark events
- Can send webhooks when it detects motion

### 2. Main System (`main.py`) - Port 8765
**Purpose:** Primary event processing and recording management

**Setup Process:**
1. Loads configuration from `config.json`
2. Initializes Shinobi API client
3. Sets up event recorder for permanent storage
4. Starts FastAPI webhook server

**Event Processing Flow:**
```
External Event → main.py → Shinobi Motion API → Download Recording → permanent_recordings/
```

**Webhook Endpoints:**
- `POST /webhook` - Generic webhook receiver
- `POST /webhook/hikvision` - Hikvision camera events
- `POST /webhook/dahua` - Dahua camera events
- `POST /test/{camera_id}/{event_type}` - Manual test triggers
- `GET /health` - Health check

**Event Handling:**
1. Receives webhook with event details (motion, person, car, etc.)
2. Extracts camera ID and event metadata
3. Calls Shinobi's motion API to create timeline marker
4. Downloads the most recent recording from Shinobi
5. Saves to `permanent_recordings/{camera_id}/{timestamp}/`
6. Includes event metadata in `event.json`

### 3. Webhook Receiver (`webhook_receiver.py`) - Port 8766
**Purpose:** Web interface and Shinobi event logging

**Setup Process:**
1. Starts FastAPI server with static file serving
2. Connects to Shinobi for data retrieval
3. Serves web UI from `static/` directory

**Responsibilities:**
- Receives webhooks FROM Shinobi (when Shinobi detects motion)
- Logs all received events to `received_webhooks.log`
- Provides web interface for viewing recordings and timeline
- Streams videos from Shinobi or local storage

**API Endpoints:**
- `POST /webhook/shinobi` - Receives events from Shinobi
- `GET /api/cameras` - List configured cameras
- `GET /api/recordings/{camera_id}` - Get recordings for camera
- `GET /api/shinobi-events/{camera_id}` - Get events from Shinobi
- `GET /api/timeline/{camera_id}` - Combined timeline with events
- `GET /api/video/{camera_id}/{filename}` - Stream video file
- `GET /events` - View logged webhook events
- `GET /` - Main web interface

## Data Flow Examples

### Example 1: ONVIF Camera Event
```
1. Camera detects motion
2. Camera sends ONVIF event to main.py (/webhook)
3. main.py triggers Shinobi motion API
4. Shinobi marks event in timeline
5. main.py downloads recording to permanent_recordings/
6. User views event in webhook_receiver.py web UI
```

### Example 2: AI Detector Event
```
1. AI system detects person
2. AI sends webhook to main.py (/webhook) with metadata
3. main.py processes rich event data (person, confidence, zone)
4. Shinobi motion API called with detailed info
5. Recording saved with event metadata
6. Timeline shows detailed event information
```

### Example 3: Manual Test
```
1. User runs: curl -X POST http://localhost:8765/test/cam1/motion
2. main.py receives test event
3. Shinobi motion API triggered
4. Recording downloaded and saved
5. Event appears in web UI timeline
```

## Storage Structure

### Shinobi Server Storage
- Continuous recordings (managed by Shinobi)
- HLS streams available for live viewing
- Timeline markers for events

### Local Storage
```
your_project/
├── permanent_recordings/     # Event-triggered recordings (kept forever)
│   ├── cam1/
│   │   └── 20240115_143022/  # Event timestamp folder
│   │       ├── video.mp4     # Downloaded recording
│   │       └── event.json    # Event metadata
│   └── cam2/
├── temp_recordings/          # Temporary storage (auto-deleted)
│   ├── cam1/
│   └── cam2/
├── received_webhooks.log     # Log of all webhook events
└── config.json              # System configuration
```

## Configuration (`config.json`)

```json
{
  "shinobi": {
    "base_url": "http://localhost:8080",
    "api_key": "your_api_key",
    "group_key": "your_group_key"
  },
  "cameras": [
    {
      "id": "tnQi3qnNqI",
      "name": "Camera 1",
      "rtsp_url": "rtsp://localhost:8554/cam1",
      "use_webhook": true
    }
  ],
  "webhook": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8765
  },
  "storage": {
    "permanent_dir": "./permanent_recordings",
    "temp_dir": "./temp_recordings"
  }
}
```

## Startup Sequence

### Manual Startup:
1. **Start Shinobi NVR** (external process)
2. **Start main.py**: `python3 main.py`
3. **Start webhook_receiver.py**: `python3 webhook_receiver.py`

### Automated Startup:
Run `./start_all.sh` which:
1. Starts dummy RTSP streams (if needed)
2. Starts webhook_receiver.py (port 8766)
3. Starts main.py (port 8765)

## Key Integration Points

### Shinobi API Usage
- **Motion Trigger**: `GET /{api_key}/motion/{group_key}/{monitor_id}`
- **Get Recordings**: `GET /{api_key}/videos/{group_key}/{monitor_id}`
- **Download Video**: `GET /{api_key}/videos/{group_key}/{monitor_id}/{filename}`
- **Get Monitors**: `GET /{api_key}/monitor/{group_key}`

### Webhook Communication
- **External → main.py**: Events from cameras/detectors
- **Shinobi → webhook_receiver.py**: Events detected by Shinobi
- **main.py → Shinobi**: Motion API triggers

## Web Interface

Access at: `http://localhost:8766`

Features:
- Live camera viewing (streams from Shinobi)
- Recording playback with seeking support
- Event timeline with filtering
- Event details and metadata display
- Test event triggering

## Testing and Monitoring

### Health Checks:
- `curl http://localhost:8765/health` - Main system
- `curl http://localhost:8766/health` - Webhook receiver

### Test Events:
- `curl -X POST http://localhost:8765/test/cam1/motion`
- `curl -X POST http://localhost:8765/test/cam2/person`

### View Events:
- `curl http://localhost:8766/events` - Recent webhook events

## Event Metadata

Each saved recording includes `event.json`:
```json
{
  "event_type": "motion",
  "event_time": "2024-01-15T14:30:22.123456",
  "camera_id": "cam1",
  "filename": "video_14-30.mp4",
  "recording_start": "2024-01-15T14:29:00",
  "recording_end": "2024-01-15T14:31:00",
  "size": 15234567
}
```

## Advantages of This Architecture

1. **Efficient Storage**: Only saves recordings when events occur
2. **Rich Metadata**: Preserves detailed event information
3. **Flexible Integration**: Accepts events from any source
4. **Web Interface**: Easy management and viewing
5. **Shinobi Integration**: Leverages professional NVR features
6. **Scalable**: Can handle multiple cameras and event types

## Troubleshooting

### Common Issues:
- **No recordings saved**: Check Shinobi connection and API keys
- **Webhooks not received**: Verify ports 8765/8766 are accessible
- **Videos not playing**: Check Shinobi HLS stream URLs
- **Events not logged**: Check `received_webhooks.log`

### Logs:
- Main system: Console output from `main.py`
- Webhook events: `received_webhooks.log`
- Shinobi: Check Shinobi server logs

This system provides a complete event-driven recording solution that combines the reliability of Shinobi NVR with flexible event processing and intelligent storage management.
