#!/usr/bin/env python3
"""
Shinobi Monitor Mode Fixer

Updates monitor modes to "record" for continuous recording.
This should fix the recording issue.
"""

import json
import requests
import sys

def fix_monitor_modes():
    """Fix monitor modes to record"""
    
    # Load config
    with open('config.json') as f:
        config = json.load(f)
    
    shinobi_cfg = config['shinobi']
    base_url = shinobi_cfg['base_url']
    api_key = shinobi_cfg['api_key']
    group_key = shinobi_cfg['group_key']
    
    print("🔧 FIXING SHINOBI MONITOR MODES")
    print("=" * 50)
    
    try:
        # Get current monitors
        response = requests.get(f'{base_url}/{api_key}/monitor/{group_key}', timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to get monitors: {response.status_code}")
            return False
        
        data = response.json()
        monitors = data if isinstance(data, list) else data.get('monitors', [])
        
        print(f"Found {len(monitors)} monitors")
        
        fixed_count = 0
        
        for monitor in monitors:
            mid = monitor.get('mid', 'unknown')
            name = monitor.get('name', 'Unknown')
            current_mode = monitor.get('mode', 'unknown')
            
            print(f"\n📹 {name} ({mid})")
            print(f"   Current mode: {current_mode}")
            
            # Only fix monitors that are not in "record" mode
            if current_mode != 'record':
                print(f"   🔧 Changing mode from '{current_mode}' to 'record'...")
                
                try:
                    # Update monitor mode to record
                    update_url = f'{base_url}/{api_key}/monitor/{group_key}/{mid}/record'
                    update_response = requests.get(update_url, timeout=10)
                    
                    if update_response.status_code == 200:
                        result = update_response.json()
                        if result.get('ok'):
                            print(f"   ✅ Successfully changed to 'record' mode")
                            fixed_count += 1
                        else:
                            print(f"   ❌ Failed to update: {result}")
                    else:
                        print(f"   ❌ Update request failed: {update_response.status_code}")
                        print(f"      Response: {update_response.text}")
                        
                except Exception as e:
                    print(f"   ❌ Error updating mode: {e}")
            else:
                print(f"   ✅ Already in correct mode")
        
        print(f"\n" + "=" * 50)
        print(f"📊 SUMMARY: Fixed {fixed_count} monitors")
        
        if fixed_count > 0:
            print("✅ All monitors now set to 'record' mode")
            print("💡 This should enable continuous recording")
            print("🔄 Restart your camera system to apply changes")
        else:
            print("✅ All monitors already in correct mode")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_recording_after_fix():
    """Test if recording works after fixing modes"""
    
    print("\n🧪 TESTING RECORDING AFTER FIX")
    print("=" * 50)
    
    # Load config
    with open('config.json') as f:
        config = json.load(f)
    
    shinobi_cfg = config['shinobi']
    base_url = shinobi_cfg['base_url']
    api_key = shinobi_cfg['api_key']
    group_key = shinobi_cfg['group_key']
    
    # Test motion trigger on main cameras
    test_cameras = ['cam1', 'cam2']
    
    for camera_id in test_cameras:
        print(f"\n🎯 Testing motion trigger for {camera_id}...")
        
        try:
            # Trigger motion
            trigger_url = f'{base_url}/{api_key}/motion/{group_key}/{camera_id}'
            params = {
                'data': json.dumps({
                    'plug': camera_id,
                    'name': 'Test Motion',
                    'reason': 'Testing after mode fix',
                    'confidence': 100
                })
            }
            
            response = requests.get(trigger_url, params=params, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    print(f"   ✅ Motion trigger successful")
                else:
                    print(f"   ❌ Motion trigger failed: {result}")
            else:
                print(f"   ❌ Motion trigger request failed: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Error testing motion trigger: {e}")
    
    print(f"\n💡 Check Shinobi web interface to verify recordings are being created")

def main():
    """Main function"""
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        test_recording_after_fix()
    else:
        success = fix_monitor_modes()
        if success:
            print(f"\n🚀 Next steps:")
            print(f"1. Restart your camera system: python3 main.py")
            print(f"2. Test recording: python3 shinobi_fix.py test")
            print(f"3. Check Shinobi web interface for recordings")

if __name__ == "__main__":
    main()
