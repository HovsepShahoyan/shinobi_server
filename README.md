# YOLO Surveillance System

## Overview

This system provides real-time object detection (cars, trucks, people, buses) on video streams using YOLO, with integration to Shinobi NVR for recording and an Electron app for viewing detections.

## Architecture

```
Video Source → MediaMTX → YOLO Detector → MediaMTX → Shinobi NVR
     ↓              ↓           ↓              ↓           ↓
  (Camera)    (RTSP Server)  (Detection)  (Output Stream) (Recording)
                    ↓           ↓
               /input      /detected
                            ↓
                      Webhook Server → Electron App
                            ↓
                    (Event notifications)
```

## Components

| Component | Location | Purpose |
|-----------|----------|---------|
| MediaMTX | `~/shinobi_server/mediamtx` | RTSP server for streams |
| YOLO Detector | `~/yolo_detector/` | Object detection with colored boxes |
| Shinobi NVR | `/home/Shinobi/` | Video recording & management |
| Webhook Server | `~/shinobi_server/main.py` | Receives detection events |
| Electron App | `~/shinobi_server/electron-app/` | View detections & recordings |

## Detection Features

- **🟢 GREEN box** = Static object (parked car, standing person)
- **🔴 RED box** = Moving object (triggers webhook)
- Detects: person, car, truck, bus
- Webhooks sent only when objects move (not on camera shake)

## Prerequisites

- Ubuntu 24.04
- NVIDIA GPU with CUDA (RTX 4060 or similar)
- Python 3.10+
- Node.js 18+
- MySQL/MariaDB

## Manual Startup (6 Terminals)

### Terminal 1: MediaMTX (RTSP Server)
```bash
cd ~/shinobi_server
./mediamtx
```

### Terminal 2: Video Input (Fake Camera or Real RTSP)
```bash
# For test video file (looped):
ffmpeg -re -stream_loop -1 -i ~/recording_20260117_145540.mp4.mkv \
  -c copy -f rtsp -rtsp_transport tcp rtsp://localhost:8554/input

# For real camera:
# ffmpeg -rtsp_transport tcp -i rtsp://user:pass@camera_ip:554/stream \
#   -c copy -f rtsp -rtsp_transport tcp rtsp://localhost:8554/input
```

### Terminal 3: YOLO Detector
```bash
cd ~/yolo_detector
source venv/bin/activate
python motion_yolo_detector.py
```

### Terminal 4: Shinobi NVR
```bash
cd /home/Shinobi
sudo node camera.js
```

### Terminal 5: Webhook Server
```bash
cd ~/shinobi_server
source venv312/bin/activate
python main.py
```

### Terminal 6: Electron App
```bash
cd ~/shinobi_server/electron-app
npm start
```

## Startup Order

**Important:** Start in this order:
1. MediaMTX (wait for "listener opened")
2. Shinobi NVR (wait for startup message)
3. Video Input (wait for "Stream mapping")
4. YOLO Detector (wait for "Output: rtsp://...")
5. Webhook Server (wait for "Webhook server starting")
6. Electron App

## Automated Startup

Use the provided startup script:
```bash
cd ~/shinobi_server
./start_surveillance.sh
```

To stop all:
```bash
./start_surveillance.sh stop
```

## Configuration

### Shinobi Camera Setup

1. Open http://localhost:8080
2. Login with your credentials
3. Add monitor with:
   - **Input Type:** H.264 / H.265 / H.265+
   - **Protocol:** RTSP
   - **Host:** 127.0.0.1
   - **Port:** 8554
   - **Path:** /detected
   - **RTSP Transport:** TCP
   - **Mode:** Record

### YOLO Detector Config

Edit `~/yolo_detector/motion_yolo_detector.py`:

```python
RTSP_INPUT = "rtsp://localhost:8554/input"      # Input stream
RTSP_OUTPUT = "rtsp://localhost:8554/detected"  # Output stream
WEBHOOK_URL = "http://localhost:8765/webhook"   # Webhook endpoint
CONFIDENCE = 0.15                                # Detection threshold
COOLDOWN_SECONDS = 3                             # Time between webhooks
MOVEMENT_THRESHOLD = 30                          # Pixels to count as movement
```

### Webhook Server Config

Edit `~/shinobi_server/config.json`:

```json
{
  "shinobi": {
    "base_url": "http://localhost:8080",
    "api_key": "YOUR_API_KEY",
    "group_key": "YOUR_GROUP_KEY"
  },
  "cameras": [
    {
      "id": "MONITOR_ID",
      "name": "YOLO Camera",
      "rtsp_url": "rtsp://localhost:8554/detected"
    }
  ],
  "webhook": {
    "port": 8765
  }
}
```

## URLs & Ports

| Service | URL |
|---------|-----|
| Shinobi Web UI | http://localhost:8080 |
| Shinobi Super Admin | http://localhost:8080/super |
| Webhook Server | http://localhost:8765 |
| Electron App Viewer | http://localhost:8766 |
| MediaMTX API | http://localhost:9997 |
| RTSP Input Stream | rtsp://localhost:8554/input |
| RTSP Output Stream | rtsp://localhost:8554/detected |
| HLS Output Stream | http://localhost:8888/detected/index.m3u8 |

## Troubleshooting

### Check if streams are running
```bash
curl http://localhost:9997/v3/paths/list
```

### Test RTSP stream
```bash
ffplay -rtsp_transport tcp rtsp://localhost:8554/detected
```

### Test HLS stream
```bash
ffplay http://localhost:8888/detected/index.m3u8
```

### Check Shinobi monitors
```bash
curl "http://localhost:8080/YOUR_API_KEY/monitor/YOUR_GROUP_KEY"
```

### Common Issues

1. **"No one is publishing to path"** - YOLO detector or video input not running
2. **"Protocol not found"** - Wrong Input Type in Shinobi settings
3. **"Connection refused"** - Service not running on that port
4. **Black screen in Shinobi** - Check RTSP Transport is set to TCP

## Files Structure

```
~/shinobi_server/
├── main.py                 # Webhook server
├── config.json             # Configuration
├── mediamtx                 # RTSP server binary
├── mediamtx.yml            # MediaMTX config
├── shinobi_client.py       # Shinobi API client
├── webhook_receiver.py     # Video viewer
├── start_surveillance.sh   # Startup script
├── venv312/                # Python virtual environment
├── permanent_recordings/   # Saved event clips
└── electron-app/           # Electron viewer app

~/yolo_detector/
├── motion_yolo_detector.py # Main detector script
├── yolo26l.pt              # YOLO model weights
├── venv/                   # Python virtual environment
└── requirements.txt        # Python dependencies

/home/Shinobi/              # Shinobi NVR installation
├── camera.js               # Main Shinobi server
├── conf.json               # Shinobi configuration
├── super.json              # Super admin credentials
└── videos/                 # Recorded videos
```

## Credentials

### Shinobi Super Admin
- URL: http://localhost:8080/super
- Email: admin@shinobi.video
- Password: admin

### Shinobi User
- URL: http://localhost:8080
- Email: (check database)
- Password: (check database)

## API Keys

Located in `~/shinobi_server/config.json`:
- API Key: `ynKZEwCmeGDJE3Y28ySkPKrata2x3N`
- Group Key: `hs1234`
