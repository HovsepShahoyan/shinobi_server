
# Setting Up: ONVIF → Shinobi → FastAPI → Logs

## The Correct Flow You Want

```
ONVIF Camera/NVR → Shinobi NVR → FastAPI Webhook Server → Log/Print
```

## Step 1: Configure Shinobi to Forward Events to Your FastAPI

### Method 1: Shinobi Configuration (Recommended)

In Shinobi's web interface (http://localhost:8080):

1. **Go to Monitor Settings** for cam1 and cam2
2. **Find "Motion/Event Settings"** or "Webhook Configuration"
3. **Set Webhook URL to:**
   ```
   http://localhost:8765/webhook/shinobi
   ```
4. **Enable motion notifications**

### Method 2: API Configuration

```bash
# Configure cam1 to send events to your FastAPI
curl -X POST "http://localhost:8080/ynKZEwCmeGDJE3Y28ySkPKrata2x3N/configureMonitor/hs1234/cam1" \
  -H "Content-Type: application/json" \
  -d '{
    "mid": "cam1",
    "name": "Camera 1",
    "details": {
      "auto_host": "rtsp://admin:Aragats777@192.168.0.21:3333/stream",
      "motion_http_url": "http://localhost:8765/webhook/shinobi",
      "motion_http_method": "POST"
    }
  }'

# Configure cam2 similarly
curl -X POST "http://localhost:8080/ynKZEwCmeGDJE3Y28ySkPKrata2x3N/configureMonitor/hs1234/cam2" \
  -H "Content-Type: application/json" \
  -d '{
    "mid": "cam2",
    "name": "Camera 2", 
    "details": {
      "auto_host": "rtsp://admin:Aragats777@192.168.0.21:1111",
      "motion_http_url": "http://localhost:8765/webhook/shinobi",
      "motion_http_method": "POST"
    }
  }'
```

## Step 2: ✅ COMPLETED - FastAPI Server Updated

I've updated your `webhook_server.py` to include a new endpoint:
- **Endpoint**: `/webhook/shinobi`
- **Function**: Receives events FROM Shinobi and logs them

## Step 3: Start Everything

### Start the FastAPI Server
```bash
python3 main.py
```

### Test the Flow

**Simulate ONVIF event:**
```bash
# Send a test event that simulates what Shinobi would receive from ONVIF
curl -X POST "http://localhost:8080/ynKZEwCmeGDJE3Y28ySkPKrata2x3N/motion/hs1234/cam1" \
  -G -d 'data={"plug": "cam1", "name": "Person", "reason": "Person detected at entrance", "confidence": 95}'
```

**Expected Result:**
- Shinobi receives the event
- Shinobi forwards it to `http://localhost:8765/webhook/shinobi`
- Your FastAPI server logs:
```
🎥 SHINOBI EVENT RECEIVED:
   Monitor: cam1
   Event: Person
   Reason: Person detected at entrance
   Confidence: 95%
   Timestamp: 2024-01-15T14:30:22.123456
```

## Step 4: Monitor the Logs

**Check your FastAPI server logs:**
```bash
tail -f camera_system.log
```

You should see events being logged in real-time!

## Summary

✅ **FastAPI endpoint `/webhook/shinobi` added**
✅ **Event logging implemented**
✅ **Ready to receive events from Shinobi**

Now just configure Shinobi to forward events to your FastAPI server!

