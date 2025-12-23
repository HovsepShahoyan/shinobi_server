# 🎥 Dummy Streams & Complete Testing Guide

## 📋 Overview

This setup creates dummy RTSP streams to test your complete camera recording pipeline:

```
ONVIF Server (Simulated) → Events → Shinobi NVR → Webhook → FastAPI Receiver
                                        ↓
                              Local Storage (Temp/Permanent)
```

## 🏗️ What Was Created

### 1. **Dummy Video Streams**
- `test_videos/cam1_base.mp4` - Colorful test pattern (30 seconds, 1080p, 30fps)
- `test_videos/cam2_base.mp4` - Blue screen (30 seconds, 1080p, 30fps)

### 2. **RTSP Stream Servers**
- `dummy_streams/start_dummy_streams.py` - Creates looping RTSP streams
- **Camera 1**: `rtsp://localhost:8554/cam1`
- **Camera 2**: `rtsp://localhost:8555/cam2`

### 3. **Updated Configuration**
- `config.json` - Now uses dummy streams instead of real cameras
- Webhook server configured on port 8765
- Camera mapping for external IDs

### 4. **Testing Pipeline**
- `complete_test.py` - Automated testing of the complete flow
- `webhook_receiver.py` - Simple FastAPI server that prints webhook events

## 🚀 How to Test (Step by Step)

### Step 1: Start Dummy RTSP Streams
```bash
python3 dummy_streams/start_dummy_streams.py
```
This will create two looping RTSP streams that simulate camera feeds.

### Step 2: Start Your Main Camera System
In a **new terminal**:
```bash
python3 main.py
```
This starts:
- Shinobi client for recording
- Webhook server on port 8765
- Local storage sync

### Step 3: Start Webhook Receiver
In a **third terminal**:
```bash
python3 webhook_receiver.py
```
This starts a simple server that prints all webhook events it receives.

### Step 4: Run Automated Tests
In a **fourth terminal**:
```bash
python3 complete_test.py
```

## 📊 What Gets Tested

### 🎬 **Stream Testing**
- Dummy RTSP streams loop continuously
- Shinobi connects and records continuously (mode="record")
- Local storage sync runs every 30 seconds

### 📤 **Webhook Events**
The test sends these events:
- `motion` on Camera 1
- `person` on Camera 1  
- `vehicle` on Camera 2
- `motion` on Camera 2

### 📥 **Event Processing**
1. Webhook server receives events
2. Normalizes event format
3. Triggers Shinobi motion API
4. Forwards to FastAPI receiver
5. Prints event details
6. Logs to file

### 💾 **Storage Testing**
- Events mark recordings as "permanent"
- Pre/post event buffers (60 seconds each)
- Temp recordings deleted after 1 hour
- Permanent recordings kept forever

## 🔍 Verification Points

### ✅ Check These URLs Work:
```
http://localhost:8765/health          # Webhook server health
http://localhost:8765/stats           # Webhook statistics
http://localhost:8766/health          # Receiver server health
http://localhost:8766/events          # List of received events
```

### ✅ Check These Directories:
```
./temp_recordings/                     # All recordings (deleted after 1 hour)
./permanent_recordings/               # Event recordings (kept forever)
./received_webhooks.log              # Log of all webhook events
./camera_system.log                  # Main system log
```

### ✅ Check These Stream URLs:
```
rtsp://localhost:8554/cam1           # Camera 1 dummy stream
rtsp://localhost:8555/cam2           # Camera 2 dummy stream
```

## 🎯 Expected Output

### Terminal 1 (Dummy Streams):
```
🎬 Starting RTSP stream: rtsp://localhost:8554/cam1
   Video: /home/hovsep/shinobi_server/test_videos/cam1_base.mp4
✅ RTSP stream started successfully
📹 Camera 1 - Test Pattern
   URL: rtsp://localhost:8554/cam1
```

### Terminal 2 (Main System):
```
🚀 Webhook server starting on 0.0.0.0:8765
✅ Webhook server configured on port 8765
📊 Status: 0 temp (0.0MB), 0 permanent (0.0MB), 📥 0 webhook events
🚨 MOTION on cam1: motion detected
🚨 PERSON on cam1: person detected
🚨 VEHICLE on cam2: vehicle detected
🚨 MOTION on cam2: motion detected
```

### Terminal 3 (Webhook Receiver):
```
📥 RECEIVED WEBHOOK EVENT FROM SHINOBI
==================================================
🕒 Timestamp: 2024-01-15T14:30:22.123456
🎯 Event Summary:
   Monitor ID: cam1
   Event Type: Motion
   Reason: motion detected
   Confidence: 100
==================================================
```

### Terminal 4 (Test Script):
```
🧪 COMPLETE CAMERA SYSTEM TEST PIPELINE
========================================
✅ Dummy streams started successfully
✅ Webhook server is running
📤 Sending test webhook events...
✅ Motion detected on Camera 1
✅ Person detected on Camera 1
✅ Vehicle detected on Camera 2
✅ Motion detected on Camera 2
📊 Sent 4/4 events successfully
📈 Webhook Statistics:
   Total events: 4
   Events by type: {"motion": 2, "person": 1, "vehicle": 1}
   Events by camera: {"cam1": 2, "cam2": 2}
```

## 🛠️ Troubleshooting

### ❌ "Cannot connect to webhook server"
- Make sure you ran `python3 main.py` first
- Check if port 8765 is available: `netstat -tulpn | grep 8765`

### ❌ "Failed to start RTSP streams"
- Make sure FFmpeg is installed: `which ffmpeg`
- Check if ports 8554, 8555 are available

### ❌ "No recordings in local storage"
- Shinobi NVR must be running and accessible
- Check Shinobi web interface for monitor status
- Verify API credentials in config.json

### ❌ "Webhook events not received"
- Make sure webhook_receiver.py is running on port 8766
- Check firewall settings
- Verify webhook URL configuration

## 📈 Advanced Testing

### Manual Event Testing:
```bash
# Send a motion event to Camera 1
curl -X POST http://localhost:8765/test/cam1/motion

# Send a person event to Camera 2  
curl -X POST http://localhost:8765/test/cam2/person

# Check webhook statistics
curl http://localhost:8765/stats

# Check received events
curl http://localhost:8766/events
```

### Stream Testing:
```bash
# Test RTSP streams with VLC or ffplay
ffplay rtsp://localhost:8554/cam1
ffplay rtsp://localhost:8555/cam2

# Or test with ffmpeg
ffmpeg -i rtsp://localhost:8554/cam1 -t 10 -f null -
```

### Storage Testing:
```bash
# Check storage stats
python3 main.py --stats

# Show stream URLs
python3 main.py --streams

# Show webhook URLs
python3 main.py --webhooks
```

## 🎉 Success Indicators

You'll know everything is working when:

1. **RTSP streams are running** and can be viewed in VLC
2. **Webhook server shows events** in real-time
3. **FastAPI receiver prints events** as they arrive
4. **Local storage creates recordings** in temp_recordings/
5. **Event recordings move to permanent_recordings/**
6. **Log files contain detailed information**

## 🔧 Configuration Tips

### Add More Event Types:
Edit `complete_test.py` to test more event types:
- `face`
- `line_crossing`
- `intrusion`
- `tamper`
- `loitering`

### Adjust Recording Buffers:
Edit `config.json`:
```json
"recording": {
  "pre_event_seconds": 30,    # 30 seconds before event
  "post_event_seconds": 30    # 30 seconds after event
}
```

### Change Webhook Ports:
Edit `config.json`:
```json
"webhook": {
  "port": 9000,              # Change main webhook port
  "host": "0.0.0.0"
}
```

---

## 🎯 Quick Start Summary

```bash
# Terminal 1: Start dummy streams
python3 dummy_streams/start_dummy_streams.py

# Terminal 2: Start main system  
python3 main.py

# Terminal 3: Start webhook receiver
python3 webhook_receiver.py

# Terminal 4: Run tests
python3 complete_test.py
```

**That's it! You now have a complete testing environment for your camera recording system.**
