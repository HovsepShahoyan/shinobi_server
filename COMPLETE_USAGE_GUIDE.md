# Complete Guide: How to Make Shinobi Record Videos with Webhook Events

## 🎯 What You Want to Achieve
- **Shinobi continuously records video from your cameras**
- **When you send events through webhooks, Shinobi saves those specific recordings**
- **Events include custom parameters (person detected, confidence, location, etc.)**

## 📋 System Architecture

```
┌─────────────┐    Webhook Events    ┌─────────────┐    Continuous     ┌─────────────┐
│   Cameras   │ ───────────────────▶ │  Webhook    │ ───────────────▶ │   Shinobi   │
│   (IP, RTSP)│                      │   Server    │                   │     NVR     │
└─────────────┘                      │  :8765      │                   │   :8080     │
                                      └─────────────┘                   └─────────────┘
                                             │                                   │
                                             ▼                                   ▼
                                      ┌─────────────┐                   ┌─────────────┐
                                      │   Your PC   │                   │   Server    │
                                      │   Storage   │                   │  Storage    │
                                      │  - temp/    │                   │             │
                                      │  - permanent│                   │             │
                                      └─────────────┘                   └─────────────┘
```

## 🚀 Step-by-Step Setup

### Step 1: Configure Cameras in Shinobi

Your cameras should already be configured in Shinobi with:
```json
{
  "id": "cam1",  // This is your Shinobi monitor ID
  "mode": "record"  // Continuous recording (this is key!)
}
```

### Step 2: Start the Camera System

```bash
python3 main.py
```

This starts:
- **Webhook server** on port 8765
- **Local storage sync** to your PC
- **Camera monitoring** and event processing

### Step 3: Send Webhook Events

## 📤 How to Send Events with Custom Parameters

### Method 1: Generic Webhook (Any Camera)

```bash
curl -X POST "http://localhost:8765/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "camera_id": "cam1",
    "event_type": "person",
    "confidence": 95,
    "reason": "Person detected at main entrance",
    "timestamp": "2024-01-15T14:30:22Z",
    "objects": [
      {
        "type": "person",
        "confidence": 95,
        "bounding_box": {"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.8},
        "attributes": {
          "location": "main_entrance",
          "direction": "entering",
          "speed": "walking"
        }
      }
    ]
  }'
```

### Method 2: Camera-Specific Endpoint

```bash
curl -X POST "http://localhost:8765/webhook/cam1" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "vehicle",
    "confidence": 88,
    "reason": "Unauthorized car in parking area",
    "objects": [
      {
        "type": "truck",
        "confidence": 88,
        "attributes": {
          "license_plate": "ABC-123",
          "color": "white",
          "area": "employee_parking",
          "duration": "5_minutes"
        }
      }
    ]
  }'
```

### Method 3: Line Crossing Event

```bash
curl -X POST "http://localhost:8765/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "camera_id": "cam2",
    "event_type": "line_crossing",
    "confidence": 98,
    "reason": "A person crossed the entrance line going IN with 95% confidence",
    "objects": [
      {
        "type": "person",
        "confidence": 95,
        "attributes": {
          "line_name": "entrance",
          "direction": "in",
          "object_type": "person"
        }
      }
    ]
  }'
```

## 🎬 What Happens When You Send Events

### 1. Event Processing Flow
```
Your Event → Webhook Server → Shinobi Motion API → Recording Marking
```

### 2. Shinobi Response
- Recent recordings are marked as the event type
- Event appears in Shinobi's interface with your custom parameters
- Recordings are preserved (not auto-deleted)

### 3. Local Storage Response
- Videos move from `temp_recordings/` to `permanent_recordings/`
- Event metadata saved to `event_info.json`

## 📁 File Structure After Events

```
your_pc/
├── temp_recordings/          # All recordings (auto-deleted after 1 hour)
│   ├── cam1/
│   │   ├── video_14-00.mp4
│   │   └── video_14-10.mp4
│   └── cam2/
│       └── video_14-05.mp4
└── permanent_recordings/     # Event recordings (kept forever)
    ├── cam1/
    │   └── 20240115_143022/          # Event timestamp folder
    │       ├── video_14-29.mp4       # 1 min before event
    │       ├── video_14-30.mp4       # During event
    │       ├── video_14-31.mp4       # 1 min after event
    │       └── event_info.json       # Your custom parameters
    └── cam2/
        └── 20240115_144500/
            ├── video_14-44.mp4
            ├── video_14-45.mp4
            └── event_info.json
```

## 🧪 Testing and Monitoring

### Interactive Demo
```bash
python3 webhook_demo.py
```
This provides an interactive interface to test different event types.

### Quick System Check
```bash
python3 quick_test.py
```
This checks if Shinobi and webhook server are working.

### Monitor Event Statistics
```bash
curl http://localhost:8765/stats
```

### Check Webhook Server Health
```bash
curl http://localhost:8765/health
```

## 📊 Supported Event Types

| Event Type | Description | Example Usage |
|------------|-------------|---------------|
| `motion` | General motion detected | Basic movement detection |
| `person` | Person detected | Human detection, trespassing |
| `vehicle` / `car` | Vehicle detected | Parking violations, theft |
| `face` | Face detected | Facial recognition events |
| `line_crossing` | Line crossing | Perimeter breach, entry/exit |
| `intrusion` | Zone intrusion | Unauthorized area access |
| `tamper` | Camera tampering | Camera obstruction, movement |
| `loitering` | Prolonged presence | Suspicious activity |

## 🔧 Custom Event Examples

### Security Alert
```bash
curl -X POST "http://localhost:8765/webhook/cam1" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "intrusion",
    "confidence": 92,
    "reason": "Unauthorized person in restricted area",
    "objects": [
      {
        "type": "person",
        "confidence": 92,
        "attributes": {
          "area": "server_room",
          "behavior": "loitering",
          "duration": "3_minutes",
          "threat_level": "high"
        }
      }
    ]
  }'
```

### Traffic Monitoring
```bash
curl -X POST "http://localhost:8765/webhook/cam2" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "vehicle",
    "confidence": 95,
    "reason": "Speeding vehicle detected",
    "objects": [
      {
        "type": "car",
        "confidence": 95,
        "attributes": {
          "speed": "85_kmh",
          "limit": "60_kmh",
          "lane": "lane_1",
          "license_plate": "XYZ-789"
        }
      }
    ]
  }'
```

### Retail Analytics
```bash
curl -X POST "http://localhost:8765/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "camera_id": "cam1",
    "event_type": "person",
    "confidence": 89,
    "reason": "Customer interaction at display",
    "objects": [
      {
        "type": "person",
        "confidence": 89,
        "attributes": {
          "location": "electronics_display",
          "interaction_time": "2_minutes",
          "age_estimate": "25-35",
          "group_size": 1
        }
      }
    ]
  }'
```

## 🎯 Key Configuration Parameters

### Recording Buffers (config.json)
```json
{
  "recording": {
    "pre_event_seconds": 60,    // Keep 60 seconds before event
    "post_event_seconds": 60    // Keep 60 seconds after event
  }
}
```

### Camera Configuration
```json
{
  "cameras": [
    {
      "id": "cam1",              // Shinobi monitor ID
      "use_webhook": true,       // Enable webhook events
      "name": "Front Door"       // Display name
    }
  ]
}
```

### Storage Configuration
```json
{
  "storage": {
    "temp_retention_hours": 1.0,     // Delete temp files after 1 hour
    "sync_interval": 30               // Sync every 30 seconds
  }
}
```

## 🔍 Troubleshooting

### Events Not Working?
1. Check webhook server is running: `curl http://localhost:8765/health`
2. Verify camera ID matches your Shinobi monitor
3. Check Shinobi logs for API errors

### Videos Not Being Saved?
1. Confirm cameras are in "record" mode
2. Check temp_recordings/ directory exists
3. Verify storage permissions on your PC

### Want to See Live Events?
```bash
tail -f camera_system.log
```

## 🚀 Advanced Usage

### Automated Camera Integration
Configure your IP cameras to send webhooks directly:
- **Hikvision**: Configure ISAPI webhook to `http://YOUR_PC:8765/webhook/hikvision`
- **Dahua**: Configure event notification to `http://YOUR_PC:8765/webhook/dahua`
- **Generic**: Configure HTTP push to `http://YOUR_PC:8765/webhook`

### AI Integration
Connect AI detection systems:
- **YOLO/Darknet**: Send detection results as webhook events
- **OpenCV**: Send motion/object detection events
- **Home Assistant**: Use webhook integration for automation

### Multi-Camera Coordination
Send events to specific cameras:
```bash
# Send to camera 1
curl -X POST "http://localhost:8765/webhook/cam1" -d '{...}'

# Send to camera 2  
curl -X POST "http://localhost:8765/webhook/cam2" -d '{...}'

# Send to all cameras
curl -X POST "http://localhost:8765/webhook" -d '{"camera_id": "cam1", ...}'
curl -X POST "http://localhost:8765/webhook" -d '{"camera_id": "cam2", ...}'
```

## ✅ Summary

1. **Shinobi records continuously** (mode="record")
2. **Webhook server receives events** with custom parameters
3. **Events trigger Shinobi motion API** to mark recordings
4. **Recordings are saved permanently** with your event data
5. **Everything syncs to your PC** for easy access

Your system is designed to capture the exact moments you care about while maintaining continuous recording for backup!
