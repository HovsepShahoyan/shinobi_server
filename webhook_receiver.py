#!/usr/bin/env python3
"""
Simple FastAPI Webhook Receiver

Receives webhook events from Shinobi NVR and prints them.
This is the server mentioned in your requirements that should get 
webhook events and just print them.


Flow: ONVIF Server → Events → Shinobi → Webhook → This Server
"""

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import json
import uvicorn

app = FastAPI(
    title="Camera Webhook Receiver",
    description="Simple webhook receiver for camera events",
    version="1.0.0"
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Camera Webhook Receiver",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/webhook/shinobi")
async def receive_shinobi_webhook(request: Request):
    """
    Receive webhook events FROM Shinobi NVR.
    This is where events are forwarded to after being processed by your webhook server.
    """
    try:
        body = await request.body()
        
        # Parse the event
        try:
            event_data = json.loads(body.decode())
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid JSON"}
            )
        
        # Print the event in a nice format
        print("\n" + "="*80)
        print("📥 RECEIVED WEBHOOK EVENT FROM SHINOBI")
        print("="*80)
        print(f"🕒 Timestamp: {datetime.now().isoformat()}")
        print(f"📄 Raw Data:")
        print(json.dumps(event_data, indent=2))
        
        # Extract common fields if available
        if isinstance(event_data, dict):
            monitor_id = event_data.get('plug') or event_data.get('mid') or event_data.get('camera_id', 'unknown')
            event_name = event_data.get('name', 'Unknown Event')
            reason = event_data.get('reason', 'No reason provided')
            confidence = event_data.get('confidence', 'N/A')
            
            print(f"\n🎯 Event Summary:")
            print(f"   Monitor ID: {monitor_id}")
            print(f"   Event Type: {event_name}")
            print(f"   Reason: {reason}")
            print(f"   Confidence: {confidence}")
            
            # Log to file as well
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "monitor_id": monitor_id,
                "event_name": event_name,
                "reason": reason,
                "confidence": confidence,
                "raw_data": event_data
            }
            
            with open("received_webhooks.log", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        
        print("="*80)
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "received",
                "message": "Event logged successfully",
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.get("/events")
async def get_received_events():
    """Get list of received events (from log file)"""
    try:
        events = []
        if os.path.exists("received_webhooks.log"):
            with open("received_webhooks.log", "r") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        return {"events": events, "count": len(events)}
    except Exception as e:
        return {"error": str(e), "events": [], "count": 0}

if __name__ == "__main__":
    import os
    print("=" * 80)
    print("🎯 CAMERA WEBHOOK RECEIVER")
    print("=" * 80)
    print("📡 Listening for webhook events from Shinobi NVR")
    print("🌐 Server will start on: http://localhost:8766")
    print("📋 Health check: http://localhost:8766/health")
    print("📥 Webhook endpoint: http://localhost:8766/webhook/shinobi")
    print("📊 Events list: http://localhost:8766/events")
    print("=" * 80)
    print("💡 Configure Shinobi to forward events to:")
    print("   http://localhost:8766/webhook/shinobi")
    print("=" * 80)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8766,
        log_level="info"
    )
