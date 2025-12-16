#!/usr/bin/env python3
"""
Camera Recording System with Webhook Support

Complete flow:
1. Shinobi records continuously (mode="record")
2. Webhook server receives ONVIF events (person detection, car detection, etc.)
3. Events trigger Shinobi motion API
4. Recordings synced to local PC with temp/permanent separation

Supports two modes for event detection:
- ONVIF PullPoint (legacy): Polls camera for events
- Webhook Server (recommended): Receives HTTP events from camera/NVR

Your PC has:
├── temp_recordings/      ← All recordings, deleted after 1 hour
│   ├── cam1/
│   └── cam2/
└── permanent_recordings/ ← Event recordings only, kept forever
    ├── cam1/
    │   └── 20240115_143022/  ← Event timestamp folder
    │       ├── recording1.mp4
    │       └── recording2.mp4
    └── cam2/
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from typing import Optional
from loguru import logger

from shinobi_client import ShinobiClient
from onvif_listener import ONVIFEventListener
from webhook_server import WebhookServer, create_webhook_server, ONVIFWebhookEvent

# Import LocalStorageManager if available
try:
    from local_storage import LocalStorageManager
except ImportError:
    LocalStorageManager = None
    logger.warning("LocalStorageManager not available - local storage features disabled")


class CameraSystem:
    """
    Complete camera system:
    - Shinobi for continuous recording
    - Webhook server OR ONVIF polling for motion events
    - Local storage with temp/permanent separation
    """
    
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        
        # Initialize components
        self.shinobi = self._init_shinobi()
        self.onvif = ONVIFEventListener()
        self.webhook_server: Optional[WebhookServer] = None
        self.storage: Optional[LocalStorageManager] = None
        
        self.running = False
        
        # Setup logging
        logger.remove()
        logger.add(sys.stderr, level="INFO",
                   format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
        logger.add("camera_system.log", rotation="50 MB", level="DEBUG")

    def _load_config(self, path: str) -> dict:
        with open(path) as f:
            return json.load(f)

    def _init_shinobi(self) -> ShinobiClient:
        cfg = self.config['shinobi']
        return ShinobiClient(
            base_url=cfg['base_url'],
            api_key=cfg['api_key'],
            group_key=cfg['group_key']
        )

    def _init_storage(self) -> Optional['LocalStorageManager']:
        if LocalStorageManager is None:
            return None
            
        storage_cfg = self.config.get('storage', {})
        recording_cfg = self.config.get('recording', {})
        
        manager = LocalStorageManager(
            shinobi_client=self.shinobi,
            temp_dir=storage_cfg.get('temp_dir', './temp_recordings'),
            permanent_dir=storage_cfg.get('permanent_dir', './permanent_recordings'),
            temp_retention_hours=storage_cfg.get('temp_retention_hours', 1.0),
            sync_interval_seconds=storage_cfg.get('sync_interval', 30),
            cleanup_interval_seconds=storage_cfg.get('cleanup_interval', 300)
        )
        
        manager.set_event_buffers(
            pre_seconds=recording_cfg.get('pre_event_seconds', 60),
            post_seconds=recording_cfg.get('post_event_seconds', 60)
        )
        
        return manager

    def _init_webhook_server(self) -> WebhookServer:
        """Initialize FastAPI webhook server"""
        webhook_cfg = self.config.get('webhook', {})
        
        # Build camera mapping
        camera_mapping = {}
        for cam in self.config.get('cameras', []):
            # Map by various identifiers
            if 'external_id' in cam:
                camera_mapping[cam['external_id']] = cam['id']
            if 'ip' in cam:
                camera_mapping[cam['ip']] = cam['id']
            if 'channel' in cam:
                camera_mapping[str(cam['channel'])] = cam['id']
        
        return WebhookServer(
            shinobi_client=self.shinobi,
            host=webhook_cfg.get('host', '0.0.0.0'),
            port=webhook_cfg.get('port', 8765),
            webhook_secret=webhook_cfg.get('secret'),
            camera_mapping=camera_mapping
        )

    async def setup_cameras(self):
        """Check cameras exist in Shinobi"""
        existing_monitors = self.shinobi.get_monitors()
        existing_ids = {m.get('mid') for m in existing_monitors} if existing_monitors else set()
        
        logger.info(f"Found {len(existing_ids)} existing monitors in Shinobi: {existing_ids}")
        
        for cam in self.config.get('cameras', []):
            camera_id = cam['id']
            name = cam.get('name', camera_id)
            
            if camera_id in existing_ids:
                logger.info(f"✅ {name} ({camera_id}) - already exists in Shinobi")
            else:
                logger.warning(f"⚠️ {name} ({camera_id}) - NOT found in Shinobi!")
                logger.warning(f"   Please create it manually in Shinobi UI with:")
                logger.warning(f"   Monitor ID: {camera_id}")
                logger.warning(f"   RTSP URL: {cam.get('rtsp_url', 'N/A')}")

    async def _on_motion_event(self, camera_id: str, event: dict):
        """Called when ONVIF motion detected (legacy polling mode)"""
        topic = event.get('topic', 'Motion')
        
        event_type = "Motion"
        topic_lower = topic.lower()
        if 'tamper' in topic_lower:
            event_type = "Tampering"
        elif 'linecross' in topic_lower:
            event_type = "Line Crossing"
        elif 'intrusion' in topic_lower:
            event_type = "Intrusion"
        
        logger.info(f"🚨 {event_type} detected on {camera_id}")
        
        # Mark recordings as permanent in local storage
        if self.storage:
            self.storage.trigger_event(camera_id)
        
        # Trigger Shinobi motion API
        self.shinobi.trigger_motion(camera_id, event_type, f"ONVIF: {topic}")

    async def _on_webhook_event(self, event: ONVIFWebhookEvent):
        """Called when webhook server receives an event"""
        logger.info(f"📥 Webhook event: {event.event_type} on {event.camera_id}")
        
        # Mark recordings as permanent in local storage
        if self.storage:
            self.storage.trigger_event(event.camera_id)
        
        # Note: Shinobi trigger is already handled by webhook_server

    async def setup_onvif(self):
        """Setup ONVIF event listeners (legacy polling mode)"""
        await self.onvif.start()
        
        for cam in self.config.get('cameras', []):
            onvif_url = cam.get('onvif_url')
            if not onvif_url:
                continue
            
            # Skip if using webhook mode for this camera
            if cam.get('use_webhook', False):
                continue
            
            camera_id = cam['id']
            
            success = await self.onvif.start_listening(
                camera_id=camera_id,
                onvif_url=onvif_url,
                username=cam.get('username', 'admin'),
                password=cam.get('password', ''),
                callback=self._on_motion_event
            )
            
            if success:
                logger.info(f"✅ ONVIF listener active for {camera_id}")

    async def setup_webhook_server(self):
        """Setup FastAPI webhook server"""
        webhook_cfg = self.config.get('webhook', {})
        
        if not webhook_cfg.get('enabled', True):
            logger.info("Webhook server disabled in config")
            return False
        
        self.webhook_server = self._init_webhook_server()
        
        # Register callback for local storage
        self.webhook_server.add_event_callback(self._on_webhook_event)
        
        logger.info(f"✅ Webhook server configured on port {webhook_cfg.get('port', 8765)}")
        return True

    def print_info(self):
        """Print system status"""
        storage_cfg = self.config.get('storage', {})
        recording_cfg = self.config.get('recording', {})
        webhook_cfg = self.config.get('webhook', {})
        
        print("\n" + "=" * 70)
        print("📹 CAMERA RECORDING SYSTEM")
        print("=" * 70)
        
        # Webhook info
        if self.webhook_server:
            print(f"\n🌐 Webhook Server:")
            print(f"   Status:           ACTIVE")
            print(f"   Port:             {webhook_cfg.get('port', 8765)}")
            print(f"   Generic endpoint: {self.webhook_server.get_webhook_url()}")
            print(f"   Hikvision:        http://0.0.0.0:{webhook_cfg.get('port', 8765)}/webhook/hikvision")
            print(f"   Dahua:            http://0.0.0.0:{webhook_cfg.get('port', 8765)}/webhook/dahua")
            print(f"   Health check:     http://0.0.0.0:{webhook_cfg.get('port', 8765)}/health")
        
        print(f"\n📂 Local Storage (on your PC):")
        print(f"   Temp recordings:      {storage_cfg.get('temp_dir', './temp_recordings')}")
        print(f"   Permanent recordings: {storage_cfg.get('permanent_dir', './permanent_recordings')}")
        print(f"   Temp retention:       {storage_cfg.get('temp_retention_hours', 1)} hour(s)")
        print(f"   Sync interval:        {storage_cfg.get('sync_interval', 30)} seconds")
        
        print(f"\n⏱️ Event Recording:")
        print(f"   Pre-event buffer:     {recording_cfg.get('pre_event_seconds', 60)} seconds")
        print(f"   Post-event buffer:    {recording_cfg.get('post_event_seconds', 60)} seconds")
        
        print(f"\n🎬 VLC Stream URLs:")
        for cam in self.config.get('cameras', []):
            cid = cam['id']
            name = cam.get('name', cid)
            url = self.shinobi.get_stream_url(cid)
            print(f"   {name}: {url}")
        
        print(f"\n📷 Cameras:")
        for cam in self.config.get('cameras', []):
            cid = cam['id']
            name = cam.get('name', cid)
            
            # Determine event source
            if cam.get('use_webhook', False):
                event_src = "🌐 Webhook"
                webhook_url = self.webhook_server.get_webhook_url(cid) if self.webhook_server else "N/A"
                print(f"   • {name} ({cid}) - {event_src}")
                print(f"     Webhook URL: {webhook_url}")
            elif cam.get('onvif_url'):
                print(f"   • {name} ({cid}) - 📡 ONVIF Polling")
            else:
                print(f"   • {name} ({cid}) - ❌ No event source")
        
        print("\n" + "=" * 70)
        print("Recording flow:")
        print("  1. Shinobi records continuously")
        print("  2. Webhook receives events (person, car, motion, etc.)")
        print("  3. Events trigger Shinobi motion API")
        print("  4. Recordings synced to temp_recordings/ on your PC")
        print("  5. On motion event → moved to permanent_recordings/")
        print("=" * 70)
        print("Press Ctrl+C to stop\n")

    async def run(self):
        """Main run loop"""
        self.running = True
        
        logger.info("Starting Camera Recording System...")
        
        # Initialize storage manager
        self.storage = self._init_storage()
        
        # Setup cameras in Shinobi
        await self.setup_cameras()
        
        # Setup webhook server
        webhook_enabled = await self.setup_webhook_server()
        
        # Setup ONVIF listeners (for cameras not using webhook)
        await self.setup_onvif()
        
        # Start local storage sync
        if self.storage:
            await self.storage.start()
        
        # Print info
        self.print_info()
        
        # Create tasks
        tasks = []
        
        # Webhook server task
        if self.webhook_server:
            tasks.append(asyncio.create_task(self._run_webhook_server()))
        
        # Status update task
        tasks.append(asyncio.create_task(self._status_loop()))
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def _run_webhook_server(self):
        """Run webhook server"""
        import uvicorn
        
        webhook_cfg = self.config.get('webhook', {})
        
        config = uvicorn.Config(
            self.webhook_server.app,
            host=webhook_cfg.get('host', '0.0.0.0'),
            port=webhook_cfg.get('port', 8765),
            log_level="warning"  # Reduce noise
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def _status_loop(self):
        """Periodic status updates"""
        while self.running:
            await asyncio.sleep(60)
            
            if self.storage:
                stats = self.storage.get_stats()
                storage_info = (
                    f"{stats['temp_recordings']} temp ({stats['temp_size_mb']:.1f}MB), "
                    f"{stats['permanent_recordings']} permanent ({stats['permanent_size_mb']:.1f}MB)"
                )
            else:
                storage_info = "N/A"
            
            webhook_info = ""
            if self.webhook_server:
                ws = self.webhook_server.stats
                webhook_info = f", 📥 {ws['total_events']} webhook events"
            
            logger.info(f"📊 Status: {storage_info}{webhook_info}")

    async def stop(self):
        """Stop everything"""
        self.running = False
        
        if self.storage:
            await self.storage.stop()
        await self.onvif.stop()
        
        logger.info("Camera Recording System stopped")


# ==================== CLI ====================

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Camera Recording System with Webhook Support')
    parser.add_argument('-c', '--config', default='config.json', help='Config file')
    parser.add_argument('--streams', action='store_true', help='Show stream URLs')
    parser.add_argument('--stats', action='store_true', help='Show storage stats')
    parser.add_argument('--webhooks', action='store_true', help='Show webhook URLs for cameras')
    parser.add_argument('--test-event', type=str, metavar='CAMERA_ID', help='Test motion event')
    parser.add_argument('--test-type', type=str, default='motion', help='Event type for test')
    parser.add_argument('--webhook-only', action='store_true', help='Run only webhook server')
    
    args = parser.parse_args()
    
    system = CameraSystem(args.config)
    
    if args.streams:
        print("\n🎬 VLC Stream URLs:\n")
        for cam in system.config.get('cameras', []):
            cid = cam['id']
            name = cam.get('name', cid)
            print(f"{name}:")
            print(f"  HLS:   {system.shinobi.get_stream_url(cid, 'hls')}")
            print(f"  MJPEG: {system.shinobi.get_stream_url(cid, 'mjpeg')}")
            print()
        return
    
    if args.webhooks:
        webhook_cfg = system.config.get('webhook', {})
        port = webhook_cfg.get('port', 8765)
        host = webhook_cfg.get('host', '0.0.0.0')
        
        print(f"\n🌐 Webhook URLs (configure these in your camera/NVR):\n")
        print(f"Generic endpoint:  http://{host}:{port}/webhook")
        print(f"Hikvision ISAPI:   http://{host}:{port}/webhook/hikvision")
        print(f"Dahua:             http://{host}:{port}/webhook/dahua")
        print()
        print("Camera-specific endpoints:")
        for cam in system.config.get('cameras', []):
            cid = cam['id']
            name = cam.get('name', cid)
            print(f"  {name}: http://{host}:{port}/webhook/{cid}")
        print()
        print(f"Test endpoint:     POST http://{host}:{port}/test/{{camera_id}}/{{event_type}}")
        print(f"Health check:      GET  http://{host}:{port}/health")
        print()
        return
    
    if args.stats:
        system.storage = system._init_storage()
        if system.storage:
            stats = system.storage.get_stats()
            print(f"\n📊 Storage Statistics:")
            print(f"   Temp recordings:      {stats['temp_recordings']} ({stats['temp_size_mb']:.1f} MB)")
            print(f"   Permanent recordings: {stats['permanent_recordings']} ({stats['permanent_size_mb']:.1f} MB)")
        else:
            print("Storage manager not available")
        return
    
    if args.test_event:
        # Use webhook test endpoint
        import aiohttp
        
        webhook_cfg = system.config.get('webhook', {})
        port = webhook_cfg.get('port', 8765)
        url = f"http://localhost:{port}/test/{args.test_event}/{args.test_type}"
        
        print(f"Starting webhook server briefly for test...")
        
        # Start server in background
        system.webhook_server = system._init_webhook_server()
        server_task = asyncio.create_task(system._run_webhook_server())
        
        await asyncio.sleep(2)  # Wait for server to start
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url) as resp:
                result = await resp.json()
                print(f"✅ Test result: {result}")
        
        server_task.cancel()
        return
    
    if args.webhook_only:
        # Run only the webhook server
        print("Starting webhook server only...")
        system.webhook_server = system._init_webhook_server()
        system.print_info()
        await system._run_webhook_server()
        return
    
    # Normal run - full system
    try:
        await system.run()
    except KeyboardInterrupt:
        await system.stop()


if __name__ == "__main__":
    asyncio.run(main())