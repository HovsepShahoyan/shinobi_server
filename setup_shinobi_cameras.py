#!/usr/bin/env python3
"""
Shinobi Camera Setup Script

Adds cameras to Shinobi NVR via the API.
Run this AFTER starting the dummy RTSP streams.

Usage:
    python3 setup_shinobi_cameras.py
    
This will:
1. Check if cameras already exist in Shinobi
2. Add cameras if they don't exist
3. Configure recording mode and motion detection
"""

import json
import requests
import sys
from typing import Optional, Dict, List

class ShinobiSetup:
    """Setup cameras in Shinobi NVR"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.base_url = self.config['shinobi']['base_url'].rstrip('/')
        self.api_key = self.config['shinobi']['api_key']
        self.group_key = self.config['shinobi']['group_key']
        
    def _load_config(self, path: str) -> dict:
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Config file not found: {path}")
            sys.exit(1)
    
    def _api_url(self, endpoint: str) -> str:
        """Build API URL"""
        return f"{self.base_url}/{self.api_key}/{endpoint}/{self.group_key}"
    
    def check_shinobi_connection(self) -> bool:
        """Check if Shinobi is reachable"""
        try:
            # Try to get monitors list
            url = self._api_url("monitor")
            response = requests.get(url, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Cannot connect to Shinobi: {e}")
            return False
    
    def get_existing_monitors(self) -> List[str]:
        """Get list of existing monitor IDs"""
        try:
            url = self._api_url("monitor")
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                monitors = response.json()
                return [m.get('mid', '') for m in monitors if m.get('mid')]
            return []
        except Exception:
            return []
    
    def create_monitor(self, camera_config: dict) -> bool:
        """
        Create a monitor in Shinobi
        
        Shinobi monitor configuration is complex - this creates a basic
        configuration for recording with motion detection webhook support.
        """
        camera_id = camera_config['id']
        name = camera_config.get('name', camera_id)
        rtsp_url = camera_config.get('rtsp_url', '')
        
        # Parse RTSP URL for host/port
        import urllib.parse
        parsed = urllib.parse.urlparse(rtsp_url)
        
        # Shinobi monitor configuration
        # This is a simplified version - Shinobi has MANY options
        monitor_config = {
            "mid": camera_id,
            "name": name,
            "type": "h264",
            "protocol": "rtsp",
            "host": parsed.hostname or "localhost",
            "port": str(parsed.port or 554),
            "path": parsed.path or "/",
            
            # Input settings
            "rtsp_transport": "tcp",
            "accelerator": "0",
            
            # Recording settings
            "mode": "record",  # Continuous recording
            "record_on_motion": "0",  # Record continuously, not just on motion
            
            # Video settings
            "width": "1280",
            "height": "720",
            "fps": "15",
            
            # Storage
            "storage_max": "10000",  # 10GB max per camera
            "delete_older_than": "7",  # Keep 7 days
            
            # Motion detection settings
            "detector": "0",  # Disable Shinobi's built-in detector
            "detector_trigger": "1",  # Allow motion trigger via API
            "detector_webhook": "1",  # Enable webhook on motion
            "detector_webhook_url": "http://localhost:8766/webhook/shinobi",  # Forward to receiver
            
            # Stream settings
            "stream_type": "hls",
            "stream_quality": "0",  # Copy codec
            "snap": "1",  # Enable snapshots
            
            # Output
            "vcodec": "copy",  # Copy video codec (no re-encoding)
            "acodec": "aac",   # AAC audio
            
            # Details (nested JSON in Shinobi)
            "details": json.dumps({
                "auto_host_enable": "1",
                "auto_host": rtsp_url,
                "rtsp_transport": "tcp",
                "muser": camera_config.get('username', 'admin'),
                "mpass": camera_config.get('password', ''),
                "detector_webhook": "1",
                "detector_webhook_url": "http://localhost:8766/webhook/shinobi",
                "detector_trigger": "1",
                "stream_type": "hls",
                "snap": "1",
                "snap_fps": "1",
                "vcodec": "copy",
                "crf": "25"
            })
        }
        
        try:
            # Shinobi uses POST to /api/{apiKey}/configureMonitor/{groupKey}/{monitorId}
            url = f"{self.base_url}/{self.api_key}/configureMonitor/{self.group_key}/{camera_id}"
            
            response = requests.post(
                url,
                json={"data": monitor_config},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok') or 'ok' in str(result).lower():
                    return True
                    
            # Alternative: Try the simpler monitor endpoint
            url = self._api_url(f"monitor/{camera_id}")
            response = requests.post(
                url,
                json=monitor_config,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"❌ Error creating monitor {camera_id}: {e}")
            return False
    
    def trigger_motion(self, camera_id: str) -> bool:
        """Test motion trigger API"""
        try:
            url = f"{self.base_url}/{self.api_key}/motion/{self.group_key}/{camera_id}"
            
            data = {
                "name": "Test Motion",
                "reason": "Setup test",
                "confidence": 100
            }
            
            response = requests.post(url, json=data, timeout=10)
            return response.status_code == 200
            
        except Exception:
            return False
    
    def print_manual_setup_instructions(self, camera_config: dict):
        """Print instructions for manual camera setup in Shinobi UI"""
        camera_id = camera_config['id']
        name = camera_config.get('name', camera_id)
        rtsp_url = camera_config.get('rtsp_url', '')
        
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  MANUAL SETUP INSTRUCTIONS FOR: {name:<35} ║
╚══════════════════════════════════════════════════════════════════════╝

1. Open Shinobi: {self.base_url}

2. Click "+" to add a new monitor

3. Fill in the settings:
   
   IDENTITY:
   ├─ Monitor ID:        {camera_id}
   └─ Name:              {name}

   CONNECTION:
   ├─ Mode:              Record
   ├─ Input Type:        H.264 / H.265
   ├─ Connection Type:   RTSP
   └─ Full URL:          {rtsp_url}
   
   RTSP OPTIONS (under Input):
   └─ RTSP Transport:    TCP

   STREAM (Output):
   ├─ Stream Type:       HLS
   └─ Video Codec:       Copy (no re-encoding)

   RECORDING:
   ├─ Recording:         Yes
   └─ Video Codec:       Copy

   DETECTOR (Motion):
   ├─ Enabled:           No (we use API triggers)
   ├─ Allow Trigger:     Yes ← IMPORTANT!
   └─ Send Events:       Yes
   
   WEBHOOK:
   ├─ Enabled:           Yes
   └─ URL:               http://localhost:8766/webhook/shinobi

4. Click "Save" at the bottom

5. The stream should start within a few seconds
""")
    
    def run_setup(self):
        """Run the complete setup process"""
        print("=" * 70)
        print("🔧 SHINOBI CAMERA SETUP")
        print("=" * 70)
        
        # Check Shinobi connection
        print("\n📡 Checking Shinobi connection...")
        if not self.check_shinobi_connection():
            print(f"""
❌ Cannot connect to Shinobi at {self.base_url}

Please make sure:
1. Shinobi is running
2. The URL in config.json is correct
3. The API key and Group key are correct

Start Shinobi with:
    cd ~/Shinobi
    node camera.js
""")
            return False
        
        print(f"✅ Connected to Shinobi at {self.base_url}")
        
        # Get existing monitors
        existing = self.get_existing_monitors()
        print(f"📹 Found {len(existing)} existing monitors: {existing}")
        
        # Process each camera
        cameras = self.config.get('cameras', [])
        
        for cam in cameras:
            camera_id = cam['id']
            name = cam.get('name', camera_id)
            
            print(f"\n{'─' * 50}")
            print(f"📷 Processing: {name} ({camera_id})")
            
            if camera_id in existing:
                print(f"   ✅ Already exists in Shinobi")
                
                # Test motion trigger
                if self.trigger_motion(camera_id):
                    print(f"   ✅ Motion API working")
                else:
                    print(f"   ⚠️ Motion API not responding")
            else:
                print(f"   ⚠️ Not found in Shinobi")
                print(f"   📋 Attempting to create via API...")
                
                if self.create_monitor(cam):
                    print(f"   ✅ Created successfully!")
                else:
                    print(f"   ❌ API creation failed")
                    print(f"   📋 Please create manually in Shinobi UI")
                    self.print_manual_setup_instructions(cam)
        
        # Final summary
        print("\n" + "=" * 70)
        print("📋 SETUP SUMMARY")
        print("=" * 70)
        
        print(f"""
Shinobi URL:     {self.base_url}
API Key:         {self.api_key}
Group Key:       {self.group_key}

Motion API endpoints:
""")
        for cam in cameras:
            url = f"{self.base_url}/{self.api_key}/motion/{self.group_key}/{cam['id']}"
            print(f"   {cam['id']}: POST {url}")
        
        print(f"""
Stream URLs (VLC):
""")
        for cam in cameras:
            url = f"{self.base_url}/{self.api_key}/hls/{self.group_key}/{cam['id']}/s.m3u8"
            print(f"   {cam['id']}: {url}")
        
        print(f"""
🔗 Webhook receiver should forward to:
   http://localhost:8766/webhook/shinobi

📌 Next steps:
   1. Verify RTSP streams are running (python3 dummy_rtsp_server.py)
   2. Check cameras in Shinobi UI
   3. Start the main system (python3 main.py)
   4. Start the webhook receiver (python3 webhook_receiver.py)
   5. Run tests (python3 simplified_test.py)
""")
        
        return True


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Setup cameras in Shinobi NVR')
    parser.add_argument('-c', '--config', default='config.json', help='Config file path')
    parser.add_argument('--manual', action='store_true', help='Show manual setup instructions only')
    
    args = parser.parse_args()
    
    setup = ShinobiSetup(args.config)
    
    if args.manual:
        for cam in setup.config.get('cameras', []):
            setup.print_manual_setup_instructions(cam)
    else:
        setup.run_setup()


if __name__ == "__main__":
    main()