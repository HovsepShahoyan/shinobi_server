#!/usr/bin/env python3
"""
Camera Recording System - Simplified

This system:
1. Receives webhook events (person, car, motion, etc.)
2. Triggers events in Shinobi for timeline markers
3. Saves event recordings to permanent_recordings/ (only when events occur)

Recordings are streamed directly from Shinobi via FastAPI - no local sync needed.

Run with: python3 main.py
"""

import os
import sys
import json
import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass
from loguru import logger
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)


@dataclass
class CameraConfig:
    id: str
    name: str
    rtsp_url: str = ""
    use_webhook: bool = True


class ShinobiClient:
    """Simple Shinobi API client"""
    
    def __init__(self, base_url: str, api_key: str, group_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.group_key = group_key
    
    def trigger_motion(self, monitor_id: str, event_name: str = "Motion", 
                       reason: str = "External trigger", confidence: int = 100) -> bool:
        """Trigger motion event in Shinobi"""
        import requests
        
        url = f"{self.base_url}/{self.api_key}/motion/{self.group_key}/{monitor_id}"
        params = {
            "data": json.dumps({
                "plug": monitor_id,
                "name": event_name,
                "reason": reason,
                "confidence": confidence
            })
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Failed to trigger motion: {e}")
            return False
    
    def get_monitors(self) -> list:
        """Get list of monitors"""
        import requests
        
        url = f"{self.base_url}/{self.api_key}/monitor/{self.group_key}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return []
    
    def get_recordings(self, monitor_id: str) -> list:
        """Get recordings for a monitor"""
        import requests
        
        url = f"{self.base_url}/{self.api_key}/videos/{self.group_key}/{monitor_id}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('videos', [])
        except:
            pass
        return []
    
    def download_recording(self, monitor_id: str, filename: str, save_path: str) -> bool:
        """Download a recording from Shinobi"""
        import requests
        
        url = f"{self.base_url}/{self.api_key}/videos/{self.group_key}/{monitor_id}/{filename}"
        try:
            resp = requests.get(url, stream=True, timeout=120)
            if resp.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
        return False


class EventRecorder:
    """
    Handles saving recordings when events occur.
    Only saves to permanent storage - no continuous sync.
    """
    
    def __init__(self, shinobi: ShinobiClient, permanent_dir: str = "./permanent_recordings"):
        self.shinobi = shinobi
        self.permanent_dir = Path(permanent_dir)
        self.permanent_dir.mkdir(parents=True, exist_ok=True)
        
        # Track pending events (to save recordings after they complete)
        self.pending_events: Dict[str, datetime] = {}
        self.post_event_seconds = 60
    
    def trigger_event(self, camera_id: str, event_type: str, reason: str = "", confidence: int = 100):
        """
        Called when an event is detected.
        1. Triggers motion in Shinobi (for timeline)
        2. Saves the current recording to permanent storage
        """
        now = datetime.now()
        
        # Trigger motion in Shinobi for timeline marker
        self.shinobi.trigger_motion(camera_id, event_type, reason, confidence)
        
        # Mark event time
        self.pending_events[camera_id] = now
        logger.info(f"🔴 Event triggered: {event_type} on {camera_id}")
        
        # Save most recent recording immediately
        self._save_recording(camera_id, now, event_type)
    
    def _save_recording(self, camera_id: str, event_time: datetime, event_type: str):
        """Save the most recent recording for this camera"""
        recordings = self.shinobi.get_recordings(camera_id)
        
        if not recordings:
            logger.warning(f"No recordings found for {camera_id}")
            return
        
        # Get the most recent recording
        recordings.sort(key=lambda r: r.get('time', ''), reverse=True)
        latest = recordings[0]
        
        filename = latest.get('filename')
        if not filename:
            return
        
        # Create event folder
        event_folder = self.permanent_dir / camera_id / event_time.strftime("%Y%m%d_%H%M%S")
        event_folder.mkdir(parents=True, exist_ok=True)
        
        save_path = event_folder / filename
        
        # Download the recording
        if self.shinobi.download_recording(camera_id, filename, str(save_path)):
            size_mb = save_path.stat().st_size / 1024 / 1024
            logger.info(f"💾 Saved: {filename} ({size_mb:.1f} MB) to permanent/{camera_id}/")
            
            # Save event metadata
            meta = {
                "event_type": event_type,
                "event_time": event_time.isoformat(),
                "camera_id": camera_id,
                "filename": filename,
                "recording_start": latest.get('time'),
                "recording_end": latest.get('end'),
                "size": latest.get('size')
            }
            meta_path = event_folder / "event.json"
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
        else:
            logger.error(f"Failed to save recording {filename}")
    
    def get_stats(self) -> dict:
        """Get storage statistics"""
        total_size = 0
        total_files = 0
        
        for camera_dir in self.permanent_dir.iterdir():
            if camera_dir.is_dir():
                for event_dir in camera_dir.iterdir():
                    if event_dir.is_dir():
                        for f in event_dir.glob("*.mp4"):
                            total_size += f.stat().st_size
                            total_files += 1
        
        return {
            "permanent_recordings": total_files,
            "permanent_size_mb": total_size / 1024 / 1024,
            "pending_events": len(self.pending_events)
        }


class WebhookServer:
    """Webhook server to receive external events"""
    
    def __init__(self, event_recorder: EventRecorder, host: str = "0.0.0.0", port: int = 8765):
        self.event_recorder = event_recorder
        self.host = host
        self.port = port
        self.app = None
        self.event_count = 0
    
    def setup(self):
        """Setup FastAPI app"""
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        
        self.app = FastAPI(title="Camera Webhook Server")
        
        @self.app.get("/health")
        async def health():
            return {"status": "healthy", "events_received": self.event_count}
        
        @self.app.post("/webhook")
        @self.app.post("/webhook/{camera_id}")
        async def webhook(request: Request, camera_id: str = None):
            """Generic webhook endpoint"""
            return await self._handle_webhook(request, camera_id)
        
        @self.app.post("/webhook/hikvision")
        @self.app.post("/webhook/hikvision/{camera_id}")
        async def hikvision_webhook(request: Request, camera_id: str = None):
            """Hikvision webhook endpoint"""
            return await self._handle_webhook(request, camera_id, "hikvision")
        
        @self.app.post("/webhook/dahua")
        @self.app.post("/webhook/dahua/{camera_id}")
        async def dahua_webhook(request: Request, camera_id: str = None):
            """Dahua webhook endpoint"""
            return await self._handle_webhook(request, camera_id, "dahua")
        
        @self.app.post("/test/{camera_id}/{event_type}")
        async def test_event(camera_id: str, event_type: str):
            """Test endpoint to trigger events manually"""
            self.event_recorder.trigger_event(
                camera_id, 
                event_type.title(), 
                "Manual test trigger",
                100
            )
            self.event_count += 1
            return {"status": "triggered", "camera": camera_id, "event": event_type}
        
        return self.app
    
    async def _handle_webhook(self, request: Request, camera_id: str = None, vendor: str = None):
        """Process incoming webhook"""
        try:
            body = await request.body()
            
            try:
                data = json.loads(body.decode()) if body else {}
            except:
                data = {"raw": body.decode() if body else ""}
            
            # Extract event info
            event_type = self._extract_event_type(data, vendor)
            cam_id = camera_id or self._extract_camera_id(data)
            confidence = self._extract_confidence(data)
            reason = self._extract_reason(data, event_type)
            
            if cam_id and event_type:
                logger.info(f"🚨 {event_type.upper()} on {cam_id}: {reason}")
                self.event_recorder.trigger_event(cam_id, event_type, reason, confidence)
                self.event_count += 1
            
            return JSONResponse({"status": "received"})
        
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)
    
    def _extract_event_type(self, data: dict, vendor: str = None) -> str:
        """Extract event type from webhook data"""
        # Common fields
        for field in ['event_type', 'eventType', 'type', 'name', 'event']:
            if field in data:
                return str(data[field])
        
        # Nested
        if 'events' in data and data['events']:
            return data['events'][0].get('type', 'motion')
        
        return "motion"
    
    def _extract_camera_id(self, data: dict) -> str:
        """Extract camera ID from webhook data"""
        for field in ['camera_id', 'cameraId', 'channel', 'monitor_id', 'mid', 'deviceId']:
            if field in data:
                return str(data[field])
        return None
    
    def _extract_confidence(self, data: dict) -> int:
        """Extract confidence from webhook data"""
        for field in ['confidence', 'score', 'probability']:
            if field in data:
                val = data[field]
                if isinstance(val, (int, float)):
                    return int(val * 100 if val <= 1 else val)
        return 100
    
    def _extract_reason(self, data: dict, event_type: str) -> str:
        """Extract reason/description from webhook data"""
        for field in ['reason', 'description', 'message', 'details']:
            if field in data:
                return str(data[field])
        return f"{event_type} detected"
    
    async def run(self):
        """Run the webhook server"""
        import uvicorn
        
        self.setup()
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning")
        server = uvicorn.Server(config)
        
        logger.info(f"🚀 Webhook server starting on {self.host}:{self.port}")
        await server.serve()


class CameraSystem:
    """Main camera recording system"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.cameras: list[CameraConfig] = []
        self.shinobi: Optional[ShinobiClient] = None
        self.event_recorder: Optional[EventRecorder] = None
        self.webhook_server: Optional[WebhookServer] = None
        self.running = False
    
    def _load_config(self, path: str) -> dict:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def setup(self):
        """Initialize all components"""
        # Shinobi client
        shinobi_cfg = self.config.get('shinobi', {})
        self.shinobi = ShinobiClient(
            base_url=shinobi_cfg.get('base_url', 'http://localhost:8080'),
            api_key=shinobi_cfg.get('api_key', ''),
            group_key=shinobi_cfg.get('group_key', '')
        )
        
        # Load cameras
        for cam_cfg in self.config.get('cameras', []):
            self.cameras.append(CameraConfig(
                id=cam_cfg['id'],
                name=cam_cfg.get('name', cam_cfg['id']),
                rtsp_url=cam_cfg.get('rtsp_url', ''),
                use_webhook=cam_cfg.get('use_webhook', True)
            ))
        
        # Event recorder (saves to permanent only)
        storage_cfg = self.config.get('storage', {})
        self.event_recorder = EventRecorder(
            shinobi=self.shinobi,
            permanent_dir=storage_cfg.get('permanent_dir', './permanent_recordings')
        )
        
        # Webhook server
        webhook_cfg = self.config.get('webhook', {})
        if webhook_cfg.get('enabled', True):
            self.webhook_server = WebhookServer(
                event_recorder=self.event_recorder,
                host=webhook_cfg.get('host', '0.0.0.0'),
                port=webhook_cfg.get('port', 8765)
            )
    
    def print_status(self):
        """Print system status"""
        print("\n" + "=" * 70)
        print("📹 CAMERA RECORDING SYSTEM (Simplified)")
        print("=" * 70)
        
        print("\n🌐 Webhook Server:")
        webhook_cfg = self.config.get('webhook', {})
        port = webhook_cfg.get('port', 8765)
        print(f"   Status:           ACTIVE")
        print(f"   Port:             {port}")
        print(f"   Generic endpoint: http://0.0.0.0:{port}/webhook")
        print(f"   Test endpoint:    http://0.0.0.0:{port}/test/{{camera_id}}/{{event_type}}")
        
        print(f"\n📂 Permanent Storage:")
        print(f"   Directory:        {self.config.get('storage', {}).get('permanent_dir', './permanent_recordings')}")
        print(f"   (Recordings saved only when events occur)")
        
        print(f"\n🎬 Video Viewer:")
        print(f"   URL:              http://localhost:8766")
        print(f"   (Run webhook_receiver.py separately)")
        
        shinobi_cfg = self.config.get('shinobi', {})
        print(f"\n📷 Cameras (streaming from Shinobi):")
        for cam in self.cameras:
            print(f"   • {cam.name} ({cam.id})")
            print(f"     Stream: {shinobi_cfg.get('base_url')}/{shinobi_cfg.get('api_key')}/hls/{shinobi_cfg.get('group_key')}/{cam.id}/s.m3u8")
        
        print("\n" + "=" * 70)
        print("How it works:")
        print("  1. Shinobi records continuously (stored on Shinobi server)")
        print("  2. Webhook receives events (person, car, motion, etc.)")
        print("  3. Event triggers Shinobi motion API (timeline marker)")
        print("  4. Recording downloaded to permanent_recordings/ (event clips only)")
        print("  5. View recordings at http://localhost:8766 (streams from Shinobi)")
        print("=" * 70)
        print("Press Ctrl+C to stop\n")
    
    async def status_loop(self):
        """Print periodic status updates"""
        while self.running:
            await asyncio.sleep(60)
            
            stats = self.event_recorder.get_stats()
            event_count = self.webhook_server.event_count if self.webhook_server else 0
            
            logger.info(
                f"📊 Status: {stats['permanent_recordings']} permanent recordings "
                f"({stats['permanent_size_mb']:.1f} MB), "
                f"📥 {event_count} webhook events"
            )
    
    async def run(self):
        """Run the system"""
        logger.info("Starting Camera Recording System (Simplified)...")
        
        self.setup()
        
        # Check Shinobi connection
        monitors = self.shinobi.get_monitors()
        if monitors:
            monitor_ids = {m.get('mid') for m in monitors}
            logger.info(f"Found {len(monitors)} monitors in Shinobi")
            
            for cam in self.cameras:
                if cam.id in monitor_ids:
                    logger.info(f"✅ {cam.name} ({cam.id}) - connected")
                else:
                    logger.warning(f"⚠️ {cam.name} ({cam.id}) - not found in Shinobi")
        
        self.print_status()
        
        self.running = True
        
        # Start tasks
        tasks = [
            asyncio.create_task(self.status_loop())
        ]
        
        if self.webhook_server:
            tasks.append(asyncio.create_task(self.webhook_server.run()))
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            logger.info("Camera Recording System stopped")


async def main():
    system = CameraSystem()
    await system.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")