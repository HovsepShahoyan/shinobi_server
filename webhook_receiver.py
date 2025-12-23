#!/usr/bin/env python3
"""
Camera Webhook Receiver with Video Player & Timeline

Receives webhook events from Shinobi NVR and provides:
- Event logging and storage
- Video streaming API
- Timeline with events
- Web UI for playback (served from static/ folder)

Run with: python3 webhook_receiver.py
Open: http://localhost:8766
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx
import uvicorn

# ==================== Configuration ====================

def load_config(path: str = "config.json") -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

config = load_config()
shinobi_config = config.get('shinobi', {})

SHINOBI_URL = shinobi_config.get('base_url', 'http://localhost:8080')
API_KEY = shinobi_config.get('api_key', '')
GROUP_KEY = shinobi_config.get('group_key', '')

TEMP_DIR = Path(config.get('storage', {}).get('temp_dir', './temp_recordings'))
PERMANENT_DIR = Path(config.get('storage', {}).get('permanent_dir', './permanent_recordings'))
STATIC_DIR = Path("./static")

# ==================== FastAPI App ====================

app = FastAPI(
    title="Camera Webhook Receiver",
    description="Webhook receiver with video playback and timeline",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Webhook Endpoints ====================

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
    """Receive webhook events FROM Shinobi NVR"""
    try:
        body = await request.body()
        
        try:
            event_data = json.loads(body.decode())
        except json.JSONDecodeError:
            return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
        
        # Print the event
        print("\n" + "=" * 80)
        print("📥 RECEIVED WEBHOOK EVENT FROM SHINOBI")
        print("=" * 80)
        print(f"🕒 Timestamp: {datetime.now().isoformat()}")
        print(f"📄 Raw Data:")
        print(json.dumps(event_data, indent=2))
        
        # Extract fields
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
            
            # Log to file
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
        
        print("=" * 80)
        
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
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/events")
async def get_received_events():
    """Get list of received events from log file"""
    try:
        events = []
        if os.path.exists("received_webhooks.log"):
            with open("received_webhooks.log", "r") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        return {"events": events[-100:], "count": len(events)}
    except Exception as e:
        return {"error": str(e), "events": [], "count": 0}


# ==================== Video & Timeline API ====================

@app.get("/api/cameras")
async def get_cameras():
    """Get list of cameras"""
    cameras = config.get('cameras', [])
    return {
        "cameras": [
            {
                "id": cam['id'],
                "name": cam.get('name', cam['id']),
            }
            for cam in cameras
        ]
    }


@app.get("/api/recordings/{camera_id}")
async def get_recordings(camera_id: str, source: str = Query("shinobi")):
    """Get recordings for a camera"""
    recordings = []
    
    # Get from Shinobi
    if source in ["shinobi", "all"]:
        try:
            async with httpx.AsyncClient() as client:
                url = f"{SHINOBI_URL}/{API_KEY}/videos/{GROUP_KEY}/{camera_id}"
                resp = await client.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for v in data.get('videos', []):
                        recordings.append({
                            "filename": v.get('filename'),
                            "start_time": v.get('time'),
                            "end_time": v.get('end'),
                            "size": v.get('size', 0),
                            "source": "shinobi",
                            "url": f"/api/video/{camera_id}/{v.get('filename')}"
                        })
        except Exception as e:
            print(f"Error fetching from Shinobi: {e}")
    
    # Get from local temp
    if source in ["temp", "all"]:
        temp_path = TEMP_DIR / camera_id
        if temp_path.exists():
            for f in sorted(temp_path.glob("*.mp4"), reverse=True):
                recordings.append({
                    "filename": f.name,
                    "start_time": _parse_filename_time(f.name),
                    "size": f.stat().st_size,
                    "source": "temp",
                    "url": f"/api/video/{camera_id}/{f.name}?source=temp"
                })
    
    # Get from permanent
    if source in ["permanent", "all"]:
        perm_path = PERMANENT_DIR / camera_id
        if perm_path.exists():
            for event_dir in perm_path.iterdir():
                if event_dir.is_dir():
                    for f in event_dir.glob("*.mp4"):
                        recordings.append({
                            "filename": f.name,
                            "start_time": _parse_filename_time(f.name),
                            "size": f.stat().st_size,
                            "source": "permanent",
                            "event_folder": event_dir.name,
                            "url": f"/api/video/{camera_id}/{f.name}?source=permanent&event={event_dir.name}"
                        })
    
    # Sort by start time (newest first)
    recordings.sort(key=lambda r: r.get('start_time') or '', reverse=True)
    return {"recordings": recordings, "total": len(recordings)}


@app.get("/api/shinobi-events/{camera_id}")
async def get_shinobi_events(camera_id: str, limit: int = Query(100)):
    """Get detection events from Shinobi"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{SHINOBI_URL}/{API_KEY}/events/{GROUP_KEY}/{camera_id}"
            resp = await client.get(url, timeout=10)
            
            if resp.status_code == 200:
                events = resp.json()
                formatted = []
                
                for evt in events[:limit]:
                    details = evt.get('details', {})
                    if isinstance(details, str):
                        try:
                            details = json.loads(details)
                        except:
                            details = {}
                    
                    formatted.append({
                        "timestamp": evt.get('time'),
                        "type": details.get('name', 'Motion'),
                        "confidence": details.get('confidence', 100),
                        "reason": details.get('reason', ''),
                        "camera_id": camera_id
                    })
                
                return {"events": formatted, "total": len(formatted)}
    except Exception as e:
        print(f"Error fetching events: {e}")
    
    return {"events": [], "total": 0}


@app.get("/api/timeline/{camera_id}")
async def get_timeline(camera_id: str, hours: int = Query(24)):
    """Get combined timeline with recordings and events"""
    recordings_resp = await get_recordings(camera_id, source="shinobi")
    recordings = recordings_resp.get('recordings', [])
    
    events_resp = await get_shinobi_events(camera_id)
    events = events_resp.get('events', [])
    
    # Match events to recordings
    for rec in recordings:
        rec['events'] = []
        rec_start = (rec.get('start_time') or '')[:19]
        rec_end = (rec.get('end_time') or '')[:19]
        
        for evt in events:
            evt_time = (evt.get('timestamp') or '')[:19]
            if rec_start and rec_end and rec_start <= evt_time <= rec_end:
                rec['events'].append(evt)
    
    return {
        "camera_id": camera_id,
        "recordings": recordings,
        "events": events,
        "total_recordings": len(recordings),
        "total_events": len(events)
    }


@app.get("/api/video/{camera_id}/{filename}")
async def get_video(
    request: Request,
    camera_id: str,
    filename: str,
    source: str = Query("shinobi"),
    event: Optional[str] = None
):
    """Stream video with range support for seeking"""
    
    # Determine file path based on source
    file_path = None
    
    if source == "temp":
        file_path = TEMP_DIR / camera_id / filename
    elif source == "permanent":
        if event:
            file_path = PERMANENT_DIR / camera_id / event / filename
        else:
            # Search in all event folders
            perm_path = PERMANENT_DIR / camera_id
            if perm_path.exists():
                for event_dir in perm_path.iterdir():
                    potential = event_dir / filename
                    if potential.exists():
                        file_path = potential
                        break
    else:
        # Proxy from Shinobi
        url = f"{SHINOBI_URL}/{API_KEY}/videos/{GROUP_KEY}/{camera_id}/{filename}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=120)
            if resp.status_code == 200:
                return StreamingResponse(
                    iter([resp.content]),
                    media_type="video/mp4",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Disposition": f"inline; filename={filename}"
                    }
                )
        raise HTTPException(status_code=404, detail="Video not found in Shinobi")
    
    # Local file streaming with range support
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")
    
    if range_header:
        start, end = _parse_range_header(range_header, file_size)
        
        def iterfile():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                chunk_size = 1024 * 1024  # 1MB chunks
                while remaining > 0:
                    data = f.read(min(chunk_size, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
        
        return StreamingResponse(
            iterfile(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(end - start + 1)
            }
        )
    
    return FileResponse(file_path, media_type="video/mp4")


# ==================== Helper Functions ====================

def _parse_filename_time(filename: str) -> Optional[str]:
    """Parse timestamp from filename like 2025-12-22T12-30-11.mp4"""
    try:
        base = filename.replace('.mp4', '').replace('.mkv', '')
        if 'T' in base:
            date_part, time_part = base.split('T')
            time_part = time_part.replace('-', ':')
            return f"{date_part}T{time_part}"
    except:
        pass
    return None


def _parse_range_header(range_header: str, file_size: int) -> tuple:
    """Parse HTTP Range header for video seeking"""
    try:
        range_spec = range_header.replace("bytes=", "")
        start_str, end_str = range_spec.split("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        return start, min(end, file_size - 1)
    except:
        return 0, file_size - 1


# ==================== Static Files & Index ====================

# Mount static files directory
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    """Serve the main HTML page"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse(
        status_code=404,
        content={"error": "Frontend not found. Please ensure static/index.html exists."}
    )


# ==================== Run Server ====================

if __name__ == "__main__":
    print("=" * 80)
    print("🎯 CAMERA WEBHOOK RECEIVER + VIDEO VIEWER")
    print("=" * 80)
    print(f"📡 Shinobi URL: {SHINOBI_URL}")
    print(f"📁 Static files: {STATIC_DIR.absolute()}")
    print()
    print("🌐 Web UI:           http://localhost:8766")
    print("📋 Health check:     http://localhost:8766/health")
    print("📥 Webhook endpoint: http://localhost:8766/webhook/shinobi")
    print("📊 Events API:       http://localhost:8766/events")
    print("🎬 Recordings API:   http://localhost:8766/api/recordings/{camera_id}")
    print("=" * 80)
    
    uvicorn.run(app, host="0.0.0.0", port=8766, log_level="info")