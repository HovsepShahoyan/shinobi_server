# 🎯 How to Test Your Camera System (Simple Version)

## 🚀 Quick Test Steps (3 Terminals)

### **Terminal 1: Start Main Camera System**
```bash
python3 main.py
```
This starts:
- Webhook server on port 8765
- Shinobi client for recording
- Local storage management

### **Terminal 2: Start FastAPI Webhook Receiver**
```bash
python3 webhook_receiver.py
```
This starts the server that prints webhook events.

### **Terminal 3: Run the Test**
```bash
python3 simplified_test.py
```
This tests the complete flow automatically.

## 📊 What You'll See

### Terminal 1 Output:
```
🚀 Webhook server starting on 0.0.0.0:8765
✅ Webhook server configured on port 8765
📊 Status: 0 temp (0.0MB), 0 permanent (0.0MB), 📥 0 webhook events
🚨 MOTION on cam1: motion detected
🚨 PERSON on cam1: person detected
🚨 VEHICLE on cam2: vehicle detected
🚨 FACE on cam2: face detected
```

### Terminal 2 Output (FastAPI Receiver):
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

📥 RECEIVED WEBHOOK EVENT FROM SHINOBI
==================================================
🕒 Timestamp: 2024-01-15T14:30:23.456789
🎯 Event Summary:
   Monitor ID: cam1
   Event Type: Person
   Reason: person detected
   Confidence: 100
==================================================
```

### Terminal 3 Output (Test Results):
```
🧪 SIMPLIFIED CAMERA SYSTEM TEST
==================================================
🔍 Step 1: Checking Services
✅ Webhook Server: RUNNING
✅ FastAPI Receiver: RUNNING

📤 Step 2: Testing Webhook Events
✅ Motion detected on Camera 1
✅ Person detected on Camera 1
✅ Vehicle detected on Camera 2
✅ Face detected on Camera 2

📈 Step 3: Checking Webhook Statistics
Total events processed: 4
Events by type: {"motion": 1, "person": 1, "vehicle": 1, "face": 1}
Events by camera: {"cam1": 2, "cam2": 2}

📥 Step 4: Checking Received Events
Events received by FastAPI: 4

🎯 TEST SUMMARY
==================================================
✅ Services: RUNNING
✅ Webhook Events: ALL SENT
✅ Event Processing: WORKING
✅ Event Forwarding: WORKING
```

## 🔗 URLs to Check

Open these in your browser while testing:

### Webhook Server (Port 8765):
- **Health Check**: http://localhost:8765/health
- **Statistics**: http://localhost:8765/stats

### FastAPI Receiver (Port 8766):
- **Health Check**: http://localhost:8766/health
- **Received Events**: http://localhost:8766/events

## 📁 Files to Check

After testing, check these files:
- `./received_webhooks.log` - All webhook events logged
- `./camera_system.log` - Main system log
- `./permanent_recordings/` - Event recordings (if Shinobi is running)

## 🧪 Manual Testing

You can also test manually:

```bash
# Send a motion event
curl -X POST http://localhost:8765/test/cam1/motion

# Send a person event
curl -X POST http://localhost:8765/test/cam2/person

# Check webhook stats
curl http://localhost:8765/stats

# Check received events
curl http://localhost:8766/events
```

## ✅ Success Indicators

You'll know it's working when:

1. **Terminal 1 shows events** being processed
2. **Terminal 2 prints webhook events** as they arrive
3. **Terminal 3 shows all tests passing**
4. **Web pages show statistics** and received events
5. **Log files contain event details**

## 🛠️ If Something Goes Wrong

### "Service not running" error:
- Make sure you started both `main.py` and `webhook_receiver.py`
- Check if ports 8765 and 8766 are available

### "Events not being received":
- Make sure webhook_receiver.py is printing events
- Check if Shinobi API credentials are correct in config.json

### "No permanent recordings":
- Shinobi NVR must be running and accessible
- Check Shinobi web interface for monitor status

That's it! This tests the complete flow you described:
**ONVIF events → Webhook → Shinobi → FastAPI receiver (prints)**
