# How Shinobi Records Videos with Webhook Events

## Overview
Your system has two main components working together:
1. **Shinobi NVR** - Continuously records video from cameras
2. **Webhook Server** - Receives events and triggers motion detection in Shinobi

## How Video Recording Works

### 1. Continuous Recording Setup
```python
# In shinobi_client.py, cameras are configured with:
"mode": "record"  # This enables continuous recording

# Once configured, Shinobi records 24/7 regardless of events
```

### 2. Event Processing Flow
```
Camera Event → Webhook Server → Shinobi Motion API → Event Marking
```

When you send a webhook event like:
```json
{
  "camera_id": "cam1",
  "event_type": "person",
  "reason": "Person detected at entrance"
}
```

The webhook server:
1. Receives the event
2. Calls `shinobi.trigger_motion("cam1", "Person", "Person detected at entrance")`
3. Shinobi marks recent recordings as a "Person" event

## How to Send Events with Custom Parameters

### Method 1: Generic Webhook Endpoint
```bash
curl -X POST "http://localhost:8765/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "camera_id": "cam1",
    "event_type": "person",
    "confidence": 95,
    "reason": "Person crossing entrance line",
    "objects": [
      {
        "type": "person",
        "confidence": 95,
        "bounding_box": {"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.8}
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
    "reason": "Car detected in parking area",
    "confidence": 88
  }'
```

### Method 3: Test Endpoint (for debugging)
```bash
curl -X POST "http://localhost:8765/test/cam1/motion"
```

## What Happens When You Send Events

### 1. Event Processing
```python
# webhook_server.py processes the event:
event_name = event_type.replace("_", " ").title()  # "person" → "Person"
reason = f"{object_type}({confidence}%) | original_reason"

# Calls Shinobi API:
shinobi.trigger_motion(
    monitor_id=camera_id,
    event_name=event_name,    # Shows as event type in Shinobi
    reason=reason,            # Shows as description
    confidence=confidence     # Event confidence level
)
```

### 2. Shinobi Response
- Recent recordings (before and after the event) are marked as this event type
- Event appears in Shinobi's event list with your custom parameters
- Recording segments are preserved instead of being auto-deleted

## Key Configuration Points

### Camera Configuration (config.json)
```json
{
  "cameras": [
    {
      "id": "cam1",                    # Shinobi monitor ID
      "name": "Camera 1",              # Display name
      "rtsp_url": "rtsp://...",        # Video stream source
      "use_webhook": true              # Enable webhook events
    }
  ]
}
```

### Recording Settings (config.json)
```json
{
  "recording": {
    "pre_event_seconds": 60,    # Keep 60 seconds before event
    "post_event_seconds": 60    # Keep 60 seconds after event
  }
}
```

## Supported Event Types

The system automatically maps various event types:
- `"motion"` → Motion detected
- `"person"` → Person detected  
- `"vehicle"` / `"car"` → Vehicle detected
- `"face"` → Face detected
- `"line_crossing"` → Line crossing detected
- `"intrusion"` → Intrusion in zone
- `"tamper"` → Camera tampering

## Expected Behavior

### Before Events Are Sent:
- Shinobi records continuously to temp storage
- Files are deleted after 1 hour (configurable)

### After Events Are Sent:
- Event triggers motion API in Shinobi
- Recent recordings are marked as the event type
- Files are moved to permanent storage
- Event appears in Shinobi's interface with your custom parameters

## Troubleshooting

### Check if Shinobi is Recording:
```bash
curl "http://localhost:8080/ynKZEwCmeGDJE3Y28ySkPKrata2x3N/monitor/hs1234"
```

### Check Webhook Server Status:
```bash
curl "http://localhost:8765/health"
```

### Test Event Processing:
```bash
curl -X POST "http://localhost:8765/test/cam1/person"
```

## File Structure After Events:
```
permanent_recordings/
├── cam1/
│   └── 20240115_143022/           # Event timestamp folder
│       ├── recording1.mp4          # 1 min before event
│       ├── recording2.mp4          # During event
│       ├── recording3.mp4          # 1 min after event
│       └── event_info.json        # Your custom parameters
└── cam2/
```

The `event_info.json` contains the original webhook data with your custom parameters.
