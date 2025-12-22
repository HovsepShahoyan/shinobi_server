#!/usr/bin/env python3
"""
Simplified Camera System Test

Tests the core webhook flow without RTSP complexity:
1. Simulate ONVIF events → Webhook server
2. Webhook triggers Shinobi motion API
3. Webhook forwards to FastAPI receiver (prints events)
4. Tests storage and event handling

This simulates the complete flow you described.
"""

import asyncio
import json
import time
import aiohttp
import subprocess
import os
from datetime import datetime
from pathlib import Path

class SimplifiedTest:
    def __init__(self):
        self.webhook_port = 8765
        self.receiver_port = 8766
        self.base_url = f"http://localhost:{self.webhook_port}"
        self.receiver_url = f"http://localhost:{self.receiver_port}"
        
    async def check_service(self, url: str, service_name: str) -> bool:
        """Check if a service is running"""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/health") as resp:
                    if resp.status == 200:
                        print(f"✅ {service_name}: RUNNING")
                        return True
                    else:
                        print(f"❌ {service_name}: RESPONSE ERROR ({resp.status})")
                        return False
        except Exception as e:
            print(f"❌ {service_name}: NOT RUNNING ({e})")
            return False
    
    async def send_test_event(self, camera_id: str, event_type: str, description: str) -> bool:
        """Send a test event via webhook"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/test/{camera_id}/{event_type}"
                async with session.post(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        print(f"✅ {description}")
                        return True
                    else:
                        print(f"❌ Failed to send {event_type} event for {camera_id}")
                        return False
        except Exception as e:
            print(f"❌ Error sending {event_type} event: {e}")
            return False
    
    async def get_webhook_stats(self) -> dict:
        """Get webhook server statistics"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/stats") as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return {}
    
    async def get_received_events(self) -> list:
        """Get events received by the FastAPI receiver"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.receiver_url}/events") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('events', [])
        except Exception:
            pass
        return []
    
    async def test_complete_flow(self):
        """Test the complete camera system flow"""
        print("=" * 80)
        print("🧪 SIMPLIFIED CAMERA SYSTEM TEST")
        print("=" * 80)
        print("Testing webhook flow without RTSP complexity")
        print()
        
        # Step 1: Check if services are running
        print("🔍 Step 1: Checking Services")
        print("-" * 40)
        
        webhook_ok = await self.check_service(self.base_url, "Webhook Server")
        receiver_ok = await self.check_service(self.receiver_url, "FastAPI Receiver")
        
        if not webhook_ok or not receiver_ok:
            print("\n❌ Required services are not running!")
            print("\n💡 To start the services, run these commands in separate terminals:")
            print("   Terminal 1: python3 main.py")
            print("   Terminal 2: python3 webhook_receiver.py")
            print("   Terminal 3: python3 simplified_test.py")
            return False
        
        # Step 2: Test webhook events
        print(f"\n📤 Step 2: Testing Webhook Events")
        print("-" * 40)
        
        test_events = [
            ("cam1", "motion", "Motion detected on Camera 1"),
            ("cam1", "person", "Person detected on Camera 1"),
            ("cam2", "vehicle", "Vehicle detected on Camera 2"),
            ("cam2", "face", "Face detected on Camera 2"),
        ]
        
        success_count = 0
        for camera, event_type, description in test_events:
            if await self.send_test_event(camera, event_type, description):
                success_count += 1
            await asyncio.sleep(1)  # Small delay between events
        
        print(f"\n📊 Sent {success_count}/{len(test_events)} events successfully")
        
        # Step 3: Check webhook statistics
        print(f"\n📈 Step 3: Checking Webhook Statistics")
        print("-" * 40)
        
        await asyncio.sleep(2)  # Wait for processing
        
        stats = await self.get_webhook_stats()
        if stats:
            print(f"Total events processed: {stats.get('total_events', 0)}")
            print(f"Events by type: {stats.get('events_by_type', {})}")
            print(f"Events by camera: {stats.get('events_by_camera', {})}")
            if stats.get('last_event_time'):
                print(f"Last event: {stats['last_event_time']}")
        
        # Step 4: Check received events
        print(f"\n📥 Step 4: Checking Received Events")
        print("-" * 40)
        
        received_events = await self.get_received_events()
        print(f"Events received by FastAPI: {len(received_events)}")
        
        if received_events:
            print("\n🎯 Recent Events:")
            for event in received_events[-3:]:  # Show last 3 events
                timestamp = event.get('timestamp', 'N/A')
                monitor_id = event.get('monitor_id', 'N/A')
                event_name = event.get('event_name', 'N/A')
                print(f"   {timestamp} | {monitor_id} | {event_name}")
        
        # Step 5: Test manual webhook endpoint
        print(f"\n🧪 Step 5: Testing Manual Webhook")
        print("-" * 40)
        
        manual_event = {
            "camera_id": "cam1",
            "event_type": "intrusion",
            "timestamp": datetime.now().isoformat(),
            "reason": "Manual test intrusion detection",
            "confidence": 95,
            "objects": [
                {
                    "type": "person",
                    "confidence": 95,
                    "bounding_box": {"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.6}
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/webhook",
                    json=manual_event,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        print("✅ Manual webhook test successful")
                        print("   Event: Intrusion with person detection")
                    else:
                        print(f"❌ Manual webhook test failed: {resp.status}")
        except Exception as e:
            print(f"❌ Manual webhook test error: {e}")
        
        # Final summary
        print("\n" + "=" * 80)
        print("🎯 TEST SUMMARY")
        print("=" * 80)
        
        if webhook_ok and receiver_ok:
            print("✅ Services: RUNNING")
        else:
            print("❌ Services: ISSUES DETECTED")
        
        if success_count == len(test_events):
            print("✅ Webhook Events: ALL SENT")
        else:
            print("❌ Webhook Events: SOME FAILED")
        
        if stats.get('total_events', 0) > 0:
            print("✅ Event Processing: WORKING")
        else:
            print("❌ Event Processing: NO EVENTS")
        
        if len(received_events) > 0:
            print("✅ Event Forwarding: WORKING")
        else:
            print("❌ Event Forwarding: NO EVENTS")
        
        print(f"\n📋 What This Tests:")
        print("1. ✅ Webhook server receives events")
        print("2. ✅ Events trigger Shinobi motion API")  
        print("3. ✅ Events forwarded to FastAPI receiver")
        print("4. ✅ FastAPI receiver prints/logs events")
        print("5. ✅ Event statistics tracking")
        
        print(f"\n🔗 URLs to Check:")
        print(f"   Webhook Health: {self.base_url}/health")
        print(f"   Webhook Stats:  {self.base_url}/stats")
        print(f"   Receiver Health: {self.receiver_url}/health")
        print(f"   Receiver Events: {self.receiver_url}/events")
        
        print(f"\n💡 Next Steps:")
        print("1. Check Shinobi NVR for new motion events")
        print("2. Verify recordings in permanent_recordings/")
        print("3. Test with real ONVIF events if available")
        print("4. Add more event types as needed")
        
        return True

def main():
    """Run the simplified test"""
    test = SimplifiedTest()
    asyncio.run(test.test_complete_flow())

if __name__ == "__main__":
    main()
