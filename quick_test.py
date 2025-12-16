#!/usr/bin/env python3
"""
Quick Test Script for Shinobi + Webhook System

This script helps you test if:
1. Shinobi is accessible and cameras are recording
2. Webhook server is running
3. Events can be sent successfully
"""

import json
import requests
import time
import sys
from datetime import datetime


def check_shinobi_connection():
    """Check if Shinobi NVR is accessible"""
    print("🔍 Checking Shinobi connection...")
    
    try:
        # Check config file
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        shinobi_url = config['shinobi']['base_url']
        api_key = config['shinobi']['api_key']
        group_key = config['shinobi']['group_key']
        
        print(f"   Shinobi URL: {shinobi_url}")
        print(f"   API Key: {api_key[:10]}...")
        print(f"   Group Key: {group_key}")
        
        # Try to get monitors
        resp = requests.get(f"{shinobi_url}/{api_key}/monitor/{group_key}", timeout=10)
        
        if resp.status_code == 200:
            monitors = resp.json()
            print(f"   ✅ Shinobi is accessible")
            print(f"   📊 Found {len(monitors)} monitors")
            
            for monitor in monitors:
                print(f"      • {monitor.get('mid', 'N/A')}: {monitor.get('name', 'Unnamed')}")
                print(f"        Mode: {monitor.get('mode', 'unknown')}")
            
            return True, monitors
        else:
            print(f"   ❌ Shinobi returned status {resp.status_code}")
            return False, []
            
    except Exception as e:
        print(f"   ❌ Cannot connect to Shinobi: {e}")
        print(f"   Make sure Shinobi is running at {config['shinobi']['base_url']}")
        return False, []


def check_webhook_server():
    """Check if webhook server is running"""
    print("\n🔍 Checking webhook server...")
    
    try:
        resp = requests.get("http://localhost:8765/health", timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            print("   ✅ Webhook server is running")
            print(f"   📊 Total events received: {data['stats']['total_events']}")
            return True
        else:
            print(f"   ❌ Webhook server returned status {resp.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Cannot connect to webhook server: {e}")
        print("   Run: python main.py")
        return False


def send_test_event():
    """Send a test event to the webhook"""
    print("\n🧪 Sending test event...")
    
    event_data = {
        "camera_id": "cam1",
        "event_type": "motion",
        "confidence": 100,
        "timestamp": datetime.now().isoformat(),
        "reason": "Test event from quick test script",
        "objects": []
    }
    
    try:
        resp = requests.post(
            "http://localhost:8765/webhook",
            json=event_data,
            timeout=10
        )
        
        if resp.status_code == 200:
            result = resp.json()
            print("   ✅ Test event sent successfully")
            print(f"   Response: {result}")
            return True
        else:
            print(f"   ❌ Failed to send test event: {resp.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error sending test event: {e}")
        return False


def show_cameras_status():
    """Show camera configuration and expected behavior"""
    print("\n📹 Camera Configuration:")
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        for cam in config.get('cameras', []):
            print(f"\n   {cam.get('name', cam['id'])}:")
            print(f"      ID: {cam['id']}")
            print(f"      RTSP: {cam['rtsp_url']}")
            print(f"      Event Source: {'🌐 Webhook' if cam.get('use_webhook') else '📡 ONVIF'}")
            
            if cam.get('use_webhook'):
                print(f"      Webhook URL: http://localhost:8765/webhook/{cam['id']}")
            
    except Exception as e:
        print(f"   ❌ Error reading config: {e}")


def show_stream_urls():
    """Show VLC stream URLs"""
    print("\n🎬 VLC Stream URLs:")
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        shinobi_url = config['shinobi']['base_url']
        api_key = config['shinobi']['api_key']
        group_key = config['shinobi']['group_key']
        
        for cam in config.get('cameras', []):
            camera_id = cam['id']
            name = cam.get('name', camera_id)
            
            print(f"\n   {name}:")
            print(f"      HLS:   {shinobi_url}/{api_key}/hls/{group_key}/{camera_id}/s.m3u8")
            print(f"      MJPEG: {shinobi_url}/{api_key}/mjpeg/{group_key}/{camera_id}")
            print(f"      MP4:   {shinobi_url}/{api_key}/mp4/{group_key}/{camera_id}/s.mp4")
            
    except Exception as e:
        print(f"   ❌ Error generating stream URLs: {e}")


def show_next_steps():
    """Show what to do next"""
    print("\n" + "="*60)
    print("🚀 NEXT STEPS TO GET YOUR SYSTEM WORKING:")
    print("="*60)
    
    print("\n1. START SHINOBI NVR:")
    print("   - Make sure Shinobi is running on http://localhost:8080")
    print("   - Add your cameras as monitors with mode='record'")
    print("   - Verify cameras are recording continuously")
    
    print("\n2. START THE CAMERA SYSTEM:")
    print("   python main.py")
    print("   This will:")
    print("   • Start the webhook server on port 8765")
    print("   • Setup camera monitoring")
    print("   • Start syncing recordings to your PC")
    
    print("\n3. SEND EVENTS TO TRIGGER RECORDINGS:")
    print("   # Person detected")
    print('   curl -X POST "http://localhost:8765/webhook/cam1" \\')
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"event_type": "person", "reason": "Person at entrance"}\'')
    
    print("\n   # Vehicle detected")
    print('   curl -X POST "http://localhost:8765/webhook/cam2" \\')
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"event_type": "vehicle", "reason": "Car in parking"}\'')
    
    print("\n   # Line crossing")
    print('   curl -X POST "http://localhost:8765/webhook" \\')
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"camera_id": "cam1", "event_type": "line_crossing", "reason": "Crossed entrance line"}\'')
    
    print("\n4. VIEW RESULTS:")
    print("   • Check Shinobi web interface for events")
    print("   • Look in permanent_recordings/ for saved videos")
    print("   • Run: python webhook_demo.py for interactive testing")
    
    print("\n5. AUTOMATION:")
    print("   • Configure your cameras to send webhooks to:")
    print("     http://YOUR_PC_IP:8765/webhook")
    print("   • Use AI detection systems to send structured events")
    print("   • Integrate with Home Assistant, Node-RED, etc.")
    
    print("\n" + "="*60)


def main():
    """Main test function"""
    print("="*60)
    print("🎥 SHINOBI + WEBHOOK SYSTEM QUICK TEST")
    print("="*60)
    
    # Check Shinobi
    shinobi_ok, monitors = check_shinobi_connection()
    
    # Check webhook server
    webhook_ok = check_webhook_server()
    
    # Show camera status
    show_cameras_status()
    
    # Show stream URLs if Shinobi is working
    if shinobi_ok:
        show_stream_urls()
    
    # Send test event if webhook is working
    if webhook_ok:
        send_test_event()
    
    # Show next steps
    show_next_steps()


if __name__ == "__main__":
    main()
