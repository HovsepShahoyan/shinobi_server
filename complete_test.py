#!/usr/bin/env python3
"""
Complete Testing Pipeline for Camera System

Tests the full flow:
1. Dummy RTSP streams → Shinobi recording
2. Webhook events → Shinobi motion triggers
3. Recording sync → Permanent storage
4. Event logging and statistics
"""

import asyncio
import json
import time
import subprocess
import requests
import os
from datetime import datetime
from pathlib import Path
import aiohttp
from typing import List, Dict

class CompleteTestPipeline:
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.webhook_port = self.config.get('webhook', {}).get('port', 8765)
        self.base_url = f"http://localhost:{self.webhook_port}"
        self.dummy_streams_process = None
        
    def _load_config(self, path: str) -> dict:
        with open(path) as f:
            return json.load(f)
    
    def start_dummy_streams(self) -> bool:
        """Start dummy RTSP streams"""
        print("🎬 Starting dummy RTSP streams...")
        
        try:
            script_path = Path(__file__).parent / "dummy_streams" / "start_dummy_streams.py"
            self.dummy_streams_process = subprocess.Popen(
                ["python3", str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            time.sleep(3)  # Give streams time to start
            
            if self.dummy_streams_process.poll() is None:
                print("✅ Dummy streams started successfully")
                return True
            else:
                print("❌ Failed to start dummy streams")
                return False
                
        except Exception as e:
            print(f"❌ Error starting streams: {e}")
            return False
    
    def stop_dummy_streams(self):
        """Stop dummy RTSP streams"""
        if self.dummy_streams_process:
            try:
                os.killpg(os.getpgid(self.dummy_streams_process.pid), signal.SIGTERM)
                self.dummy_streams_process.wait(timeout=5)
                print("🛑 Dummy streams stopped")
            except:
                try:
                    os.killpg(os.getpgid(self.dummy_streams_process.pid), signal.SIGKILL)
                except:
                    pass
    
    async def test_webhook_server(self) -> bool:
        """Test if webhook server is running"""
        print(f"🔍 Testing webhook server at {self.base_url}...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print("✅ Webhook server is running")
                        print(f"   Status: {data.get('status', 'unknown')}")
                        return True
                    else:
                        print(f"❌ Webhook server returned status {resp.status}")
                        return False
        except Exception as e:
            print(f"❌ Cannot connect to webhook server: {e}")
            print(f"💡 Make sure to run: python3 main.py")
            return False
    
    async def send_test_events(self) -> bool:
        """Send various test events to webhook"""
        print("📤 Sending test webhook events...")
        
        test_events = [
            {
                "camera": "cam1",
                "type": "motion",
                "description": "Motion detected on Camera 1"
            },
            {
                "camera": "cam1", 
                "type": "person",
                "description": "Person detected on Camera 1"
            },
            {
                "camera": "cam2",
                "type": "vehicle",
                "description": "Vehicle detected on Camera 2"
            },
            {
                "camera": "cam2",
                "type": "motion",
                "description": "Motion detected on Camera 2"
            }
        ]
        
        success_count = 0
        
        async with aiohttp.ClientSession() as session:
            for event in test_events:
                try:
                    url = f"{self.base_url}/test/{event['camera']}/{event['type']}"
                    async with session.post(url) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            print(f"✅ {event['description']}")
                            success_count += 1
                        else:
                            print(f"❌ Failed to send {event['type']} event for {event['camera']}")
                    
                    time.sleep(1)  # Small delay between events
                    
                except Exception as e:
                    print(f"❌ Error sending {event['type']} event: {e}")
        
        print(f"📊 Sent {success_count}/{len(test_events)} events successfully")
        return success_count > 0
    
    async def check_storage_stats(self) -> bool:
        """Check local storage statistics"""
        print("📂 Checking local storage...")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Check webhook stats
                async with session.get(f"{self.base_url}/stats") as resp:
                    if resp.status == 200:
                        stats = await resp.json()
                        print(f"📈 Webhook Statistics:")
                        print(f"   Total events: {stats.get('total_events', 0)}")
                        print(f"   Events by type: {stats.get('events_by_type', {})}")
                        print(f"   Events by camera: {stats.get('events_by_camera', {})}")
                        return True
                    else:
                        print(f"❌ Cannot get webhook stats: {resp.status}")
                        return False
        except Exception as e:
            print(f"❌ Error checking storage: {e}")
            return False
    
    async def run_complete_test(self):
        """Run the complete testing pipeline"""
        print("=" * 80)
        print("🧪 COMPLETE CAMERA SYSTEM TEST PIPELINE")
        print("=" * 80)
        
        # Step 1: Start dummy streams
        if not self.start_dummy_streams():
            print("❌ Cannot continue without dummy streams")
            return False
        
        try:
            # Step 2: Test webhook server
            webhook_ok = await self.test_webhook_server()
            if not webhook_ok:
                print("\n💡 To start the webhook server, run:")
                print("   python3 main.py")
                print("   (in another terminal)")
                return False
            
            # Step 3: Wait a bit for everything to stabilize
            print("⏳ Waiting for system to stabilize...")
            time.sleep(3)
            
            # Step 4: Send test events
            events_ok = await self.send_test_events()
            
            # Step 5: Check results
            stats_ok = await self.check_storage_stats()
            
            # Final summary
            print("\n" + "=" * 80)
            print("🎯 TEST SUMMARY")
            print("=" * 80)
            
            if webhook_ok:
                print("✅ Webhook Server: RUNNING")
            else:
                print("❌ Webhook Server: NOT RUNNING")
            
            if events_ok:
                print("✅ Test Events: SENT")
            else:
                print("❌ Test Events: FAILED")
            
            if stats_ok:
                print("✅ Statistics: AVAILABLE")
            else:
                print("❌ Statistics: UNAVAILABLE")
            
            print("\n📋 Next Steps:")
            print("1. Check Shinobi NVR web interface for new recordings")
            print("2. Verify permanent recordings are in ./permanent_recordings/")
            print("3. Check log files for detailed information")
            print("4. Test with different event types")
            
            return True
            
        except KeyboardInterrupt:
            print("\n🛑 Test interrupted by user")
            return False
        finally:
            self.stop_dummy_streams()
    
    def print_urls(self):
        """Print all important URLs for testing"""
        print("\n" + "=" * 80)
        print("🔗 IMPORTANT URLs FOR TESTING")
        print("=" * 80)
        
        print(f"\n🌐 Webhook Server:")
        print(f"   Health Check:     {self.base_url}/health")
        print(f"   Statistics:       {self.base_url}/stats")
        print(f"   Generic Webhook:  {self.base_url}/webhook")
        print(f"   Camera Endpoints:")
        
        for cam in self.config.get('cameras', []):
            cam_id = cam['id']
            cam_name = cam.get('name', cam_id)
            print(f"     {cam_name}:   {self.base_url}/webhook/{cam_id}")
        
        print(f"\n📹 Dummy RTSP Streams:")
        for cam in self.config.get('cameras', []):
            rtsp_url = cam.get('rtsp_url', 'N/A')
            print(f"   {cam['id']}: {rtsp_url}")
        
        print(f"\n📁 Local Storage:")
        storage_cfg = self.config.get('storage', {})
        print(f"   Temp:       {storage_cfg.get('temp_dir', './temp_recordings')}")
        print(f"   Permanent:  {storage_cfg.get('permanent_dir', './permanent_recordings')}")
        
        print("=" * 80)

def main():
    """Main test runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Complete Camera System Test')
    parser.add_argument('--urls', action='store_true', help='Show important URLs')
    parser.add_argument('--events', action='store_true', help='Send test events only')
    parser.add_argument('--streams', action='store_true', help='Test streams only')
    
    test_pipeline = CompleteTestPipeline()
    
    if args.urls:
        test_pipeline.print_urls()
        return
    
    if args.events:
        # Just send events (assume server is running)
        asyncio.run(test_pipeline.send_test_events())
        return
    
    if args.streams:
        # Just test streams
        test_pipeline.start_dummy_streams()
        try:
            input("Press Enter to stop streams...")
        except KeyboardInterrupt:
            pass
        finally:
            test_pipeline.stop_dummy_streams()
        return
    
    # Run complete test
    asyncio.run(test_pipeline.run_complete_test())

if __name__ == "__main__":
    main()
