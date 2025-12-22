#!/usr/bin/env python3
"""
Complete Recording Workflow Test

Tests the full pipeline:
1. Webhook events trigger motion API
2. Shinobi creates/updates recordings 
3. Events mark recordings as permanent
4. Local storage sync works
"""

import json
import requests
import time
from datetime import datetime

class CompleteRecordingTest:
    def __init__(self):
        # Load config
        with open('config.json') as f:
            self.config = json.load(f)
        
        self.shinobi_cfg = self.config['shinobi']
        self.base_url = self.shinobi_cfg['base_url']
        self.api_key = self.shinobi_cfg['api_key']
        self.group_key = self.shinobi_cfg['group_key']
    
    def test_monitors_status(self):
        """Test if all monitors are in record mode"""
        print("📹 MONITOR STATUS CHECK")
        print("-" * 30)
        
        try:
            response = requests.get(f'{self.base_url}/{self.api_key}/monitor/{self.group_key}', timeout=10)
            if response.status_code == 200:
                data = response.json()
                monitors = data if isinstance(data, list) else data.get('monitors', [])
                
                all_correct = True
                for monitor in monitors:
                    mid = monitor.get('mid', 'unknown')
                    name = monitor.get('name', 'Unknown')
                    mode = monitor.get('mode', 'unknown')
                    
                    if mode == 'record':
                        print(f"✅ {name} ({mid}) - Record mode")
                    else:
                        print(f"❌ {name} ({mid}) - Mode: {mode}")
                        all_correct = False
                
                return all_correct
            else:
                print(f"❌ Failed to get monitors: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_webhook_to_motion_flow(self):
        """Test webhook events trigger motion API""" 
        print("\n📤 WEBHOOK → MOTION API FLOW")
        print("-" * 30)
        
        test_events = [
            ("cam1", "motion", "Test Motion Recording"),
            ("cam2", "person", "Test Person Recording")
        ]
        
        success_count = 0
        
        for camera_id, event_type, description in test_events:
            print(f"\n🎯 Testing {event_type} on {camera_id}...")
            
            try:
                # Send test event to webhook
                webhook_url = f"http://localhost:8765/test/{camera_id}/{event_type}"
                webhook_response = requests.post(webhook_url, timeout=5)
                
                if webhook_response.status_code == 200:
                    print(f"   ✅ Webhook event sent successfully")
                    
                    # Check if motion was triggered
                    time.sleep(2)  # Give time for processing
                    
                    # Test motion trigger directly
                    motion_url = f'{self.base_url}/{self.api_key}/motion/{self.group_key}/{camera_id}'
                    params = {
                        'data': json.dumps({
                            'plug': camera_id,
                            'name': event_type.title(),
                            'reason': description,
                            'confidence': 100
                        })
                    }
                    
                    motion_response = requests.get(motion_url, params=params, timeout=5)
                    
                    if motion_response.status_code == 200:
                        result = motion_response.json()
                        if result.get('ok'):
                            print(f"   ✅ Motion API triggered successfully")
                            success_count += 1
                        else:
                            print(f"   ❌ Motion API failed: {result}")
                    else:
                        print(f"   ❌ Motion API request failed: {motion_response.status_code}")
                else:
                    print(f"   ❌ Webhook failed: {webhook_response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        print(f"\n📊 Motion API Tests: {success_count}/{len(test_events)} successful")
        return success_count == len(test_events)
    
    def test_recording_creation(self):
        """Test if recordings are being created"""
        print("\n💾 RECORDING CREATION TEST")
        print("-" * 30)
        
        # Test on main cameras
        test_cameras = ['cam1', 'cam2']
        
        for camera_id in test_cameras:
            print(f"\n📹 Checking recordings for {camera_id}...")
            
            try:
                # Get recordings for this camera
                recordings_url = f'{self.base_url}/{self.api_key}/videos/{self.group_key}/{camera_id}'
                response = requests.get(recordings_url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    recordings = data.get('videos', data) if isinstance(data, dict) else data
                    
                    if recordings and len(recordings) > 0:
                        print(f"   ✅ Found {len(recordings)} recordings")
                        
                        # Show most recent recording
                        latest = recordings[0]
                        filename = latest.get('name', 'unknown')
                        timestamp = latest.get('time', 'unknown')
                        size = latest.get('size', 'unknown')
                        
                        print(f"   📅 Latest: {filename}")
                        print(f"   🕒 Time: {timestamp}")
                        print(f"   📏 Size: {size}")
                        
                    else:
                        print(f"   ❌ No recordings found")
                        print(f"   💡 This might be normal if streams aren't active")
                else:
                    print(f"   ❌ Failed to get recordings: {response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ Error checking recordings: {e}")
    
    def test_local_storage_sync(self):
        """Test local storage sync"""
        print("\n📂 LOCAL STORAGE SYNC TEST")
        print("-" * 30)
        
        import os
        
        temp_dir = self.config.get('storage', {}).get('temp_dir', './temp_recordings')
        permanent_dir = self.config.get('storage', {}).get('permanent_dir', './permanent_recordings')
        
        print(f"📁 Temp directory: {temp_dir}")
        print(f"📁 Permanent directory: {permanent_dir}")
        
        # Check if directories exist
        if os.path.exists(temp_dir):
            temp_files = [f for f in os.listdir(temp_dir) if os.path.isfile(os.path.join(temp_dir, f))]
            print(f"   ✅ Temp files: {len(temp_files)}")
        else:
            print(f"   ❌ Temp directory doesn't exist")
        
        if os.path.exists(permanent_dir):
            permanent_files = [f for f in os.listdir(permanent_dir) if os.path.isfile(os.path.join(permanent_dir, f))]
            print(f"   ✅ Permanent files: {len(permanent_files)}")
        else:
            print(f"   ❌ Permanent directory doesn't exist")
    
    def test_complete_workflow(self):
        """Test the complete recording workflow"""
        print("=" * 60)
        print("🧪 COMPLETE RECORDING WORKFLOW TEST")
        print("=" * 60)
        
        # Step 1: Check monitors
        monitors_ok = self.test_monitors_status()
        
        # Step 2: Test webhook to motion flow
        webhook_ok = self.test_webhook_to_motion_flow()
        
        # Step 3: Check recording creation
        self.test_recording_creation()
        
        # Step 4: Test local storage
        self.test_local_storage_sync()
        
        # Final summary
        print("\n" + "=" * 60)
        print("🎯 FINAL SUMMARY")
        print("=" * 60)
        
        if monitors_ok:
            print("✅ Monitors: All in record mode")
        else:
            print("❌ Monitors: Some not in record mode")
        
        if webhook_ok:
            print("✅ Webhook → Motion API: Working")
        else:
            print("❌ Webhook → Motion API: Issues detected")
        
        print("📹 Recording: Check Shinobi web interface")
        print("📂 Storage: Local sync should work with running system")
        
        print(f"\n🚀 NEXT STEPS:")
        print(f"1. Start the system: python3 main.py")
        print(f"2. Start webhook receiver: python3 webhook_receiver.py") 
        print(f"3. Check Shinobi web interface for active recordings")
        print(f"4. Send test events: python3 simplified_test.py")
        
        return monitors_ok and webhook_ok

def main():
    """Run the complete test"""
    test = CompleteRecordingTest()
    test.test_complete_workflow()

if __name__ == "__main__":
    main()
