#!/usr/bin/env python3
"""
Shinobi Recording Diagnostic Tool

Checks Shinobi NVR connectivity and recording configuration.
Identifies why events aren't creating permanent recordings.
"""

import json
import requests
from shinobi_client import ShinobiClient
from datetime import datetime

class ShinobiDiagnostic:
    def __init__(self, config_path="config.json"):
        self.config = self._load_config(config_path)
        self.shinobi = self._init_shinobi()
        
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
    
    def test_shinobi_connection(self) -> bool:
        """Test basic Shinobi connectivity"""
        print("🔍 Testing Shinobi Connection...")
        print(f"   URL: {self.shinobi.base_url}")
        print(f"   API Key: {self.shinobi.api_key}")
        print(f"   Group Key: {self.shinobi.group_key}")
        
        try:
            monitors = self.shinobi.get_monitors()
            print(f"✅ Connection successful - Found {len(monitors)} monitors")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def check_monitor_configuration(self):
        """Check if monitors are configured correctly"""
        print("\n📷 Checking Monitor Configuration...")
        
        try:
            monitors = self.shinobi.get_monitors()
            if not monitors:
                print("❌ No monitors found in Shinobi!")
                return
            
            for monitor in monitors:
                mid = monitor.get('mid', 'unknown')
                name = monitor.get('name', 'Unknown')
                mode = monitor.get('mode', 'unknown')
                
                print(f"\n📹 Monitor: {name} ({mid})")
                print(f"   Mode: {mode}")
                
                # Check if mode is correct for recording
                if mode == 'record':
                    print(f"   ✅ Mode is correct (record)")
                elif mode == 'start':
                    print(f"   ⚠️ Mode is 'start' (only records on motion)")
                elif mode == 'idle':
                    print(f"   ❌ Mode is 'idle' (not recording)")
                else:
                    print(f"   ❓ Unknown mode: {mode}")
                
                # Check details if available
                if 'details' in monitor:
                    try:
                        details = json.loads(monitor['details']) if isinstance(monitor['details'], str) else monitor['details']
                        storage_dir = details.get('dir', 'default')
                        max_keep_days = details.get('max_keep_days', 'unknown')
                        print(f"   Storage Dir: {storage_dir}")
                        print(f"   Keep Days: {max_keep_days}")
                    except:
                        print(f"   Details: Could not parse")
                
                # Check if we can get recordings
                print(f"   Checking recordings...")
                try:
                    recordings = self.shinobi.get_recordings(mid)
                    if recordings:
                        print(f"   ✅ Found {len(recordings)} recordings")
                        # Show most recent recording
                        latest = recordings[0] if recordings else None
                        if latest:
                            print(f"   📅 Latest: {latest.get('time', 'unknown')}")
                    else:
                        print(f"   ❌ No recordings found")
                except Exception as e:
                    print(f"   ❌ Error checking recordings: {e}")
                    
        except Exception as e:
            print(f"❌ Error checking monitors: {e}")
    
    def test_motion_trigger(self, monitor_id: str):
        """Test motion trigger for a specific monitor"""
        print(f"\n🎯 Testing Motion Trigger for {monitor_id}...")
        
        try:
            result = self.shinobi.trigger_motion(
                monitor_id=monitor_id,
                event_name="Test Motion",
                reason="Diagnostic test trigger",
                confidence=100
            )
            
            if result:
                print(f"✅ Motion trigger API call successful")
                return True
            else:
                print(f"❌ Motion trigger API call failed")
                return False
                
        except Exception as e:
            print(f"❌ Error triggering motion: {e}")
            return False
    
    def check_storage_space(self):
        """Check Shinobi storage configuration"""
        print("\n💾 Checking Storage Configuration...")
        
        try:
            # Try to get system info (if available)
            # This might not work on all Shinobi versions
            response = requests.get(
                f"{self.shinobi.base_url}/{self.shinobi.api_key}/system",
                timeout=10
            )
            if response.status_code == 200:
                print(f"✅ System info retrieved")
            else:
                print(f"⚠️ System info not available (status: {response.status_code})")
        except Exception as e:
            print(f"⚠️ Could not get system info: {e}")
    
    def suggest_fixes(self):
        """Suggest fixes for recording issues"""
        print("\n🔧 Suggested Fixes:")
        print("=" * 50)
        
        print("1. **Monitor Mode**: Ensure monitors are in 'record' mode")
        print("   - Shinobi UI → Monitors → Select monitor → Mode: Record")
        print("   - Or use: python3 main.py (should auto-configure)")
        
        print("\n2. **Storage Space**: Check Shinobi has available disk space")
        print("   - Shinobi UI → Dashboard → Storage")
        
        print("\n3. **RTSP Streams**: Verify RTSP streams are accessible")
        print(f"   - Camera 1: {self.config['cameras'][0].get('rtsp_url', 'N/A')}")
        print(f"   - Camera 2: {self.config['cameras'][1].get('rtsp_url', 'N/A')}")
        
        print("\n4. **Motion Settings**: Configure motion detection sensitivity")
        print("   - Shinobi UI → Monitors → Select monitor → Motion")
        
        print("\n5. **Test Recording**: Create manual recording")
        print("   - Shinobi UI → Monitors → Select monitor → Record")
    
    def run_diagnostic(self):
        """Run complete diagnostic"""
        print("=" * 60)
        print("🔍 SHINOBI RECORDING DIAGNOSTIC")
        print("=" * 60)
        
        # Test connection
        if not self.test_shinobi_connection():
            print("\n❌ Cannot proceed - Shinobi connection failed")
            return False
        
        # Check monitor configuration
        self.check_monitor_configuration()
        
        # Test motion trigger for each camera
        for cam in self.config.get('cameras', []):
            camera_id = cam['id']
            self.test_motion_trigger(camera_id)
        
        # Check storage
        self.check_storage_space()
        
        # Suggest fixes
        self.suggest_fixes()
        
        print("\n" + "=" * 60)
        print("📋 DIAGNOSTIC COMPLETE")
        print("=" * 60)
        
        return True

def main():
    """Run the diagnostic"""
    diagnostic = ShinobiDiagnostic()
    diagnostic.run_diagnostic()

if __name__ == "__main__":
    main()
