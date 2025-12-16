#!/usr/bin/env python3
"""
Webhook Event Demonstration Script

This script demonstrates how to send webhook events to the camera system
with custom parameters and see how Shinobi responds.
"""

import json
import requests
import time
from datetime import datetime
from typing import Dict, Any


class WebhookDemo:
    def __init__(self, webhook_url: str = "http://localhost:8765"):
        self.webhook_url = webhook_url
        self.session = requests.Session()
        
    def check_server_status(self) -> bool:
        """Check if webhook server is running"""
        try:
            resp = self.session.get(f"{self.webhook_url}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                print("✅ Webhook server is running")
                print(f"   Total events received: {data['stats']['total_events']}")
                return True
            else:
                print("❌ Webhook server not responding properly")
                return False
        except Exception as e:
            print(f"❌ Cannot connect to webhook server: {e}")
            return False
    
    def send_person_detection(self, camera_id: str = "cam1", confidence: int = 95) -> Dict[str, Any]:
        """Send a person detection event"""
        event_data = {
            "camera_id": camera_id,
            "event_type": "person",
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
            "reason": f"Person detected at entrance with {confidence}% confidence",
            "objects": [
                {
                    "type": "person",
                    "confidence": confidence,
                    "bounding_box": {
                        "x": 0.2, "y": 0.3, "width": 0.4, "height": 0.8
                    },
                    "attributes": {
                        "direction": "entering",
                        "speed": "walking"
                    }
                }
            ]
        }
        
        return self._send_event(event_data, "Person Detection")
    
    def send_vehicle_detection(self, camera_id: str = "cam2", vehicle_type: str = "car") -> Dict[str, Any]:
        """Send a vehicle detection event"""
        event_data = {
            "camera_id": camera_id,
            "event_type": "vehicle",
            "confidence": 92,
            "timestamp": datetime.now().isoformat(),
            "reason": f"{vehicle_type.capitalize()} detected in parking area",
            "objects": [
                {
                    "type": vehicle_type,
                    "confidence": 92,
                    "attributes": {
                        "color": "blue",
                        "speed": "slow"
                    }
                }
            ]
        }
        
        return self._send_event(event_data, f"{vehicle_type.capitalize()} Detection")
    
    def send_line_crossing(self, camera_id: str = "cam1", direction: str = "in") -> Dict[str, Any]:
        """Send a line crossing event"""
        event_data = {
            "camera_id": camera_id,
            "event_type": "line_crossing",
            "confidence": 98,
            "timestamp": datetime.now().isoformat(),
            "reason": f"Person crossed entrance line going {direction}",
            "objects": [
                {
                    "type": "person",
                    "confidence": 98,
                    "attributes": {
                        "line_name": "entrance",
                        "direction": direction,
                        "object_type": "person"
                    }
                }
            ]
        }
        
        return self._send_event(event_data, "Line Crossing")
    
    def send_custom_event(self, camera_id: str, event_type: str, 
                         custom_reason: str, **kwargs) -> Dict[str, Any]:
        """Send a custom event with your own parameters"""
        event_data = {
            "camera_id": camera_id,
            "event_type": event_type,
            "confidence": kwargs.get('confidence', 100),
            "timestamp": datetime.now().isoformat(),
            "reason": custom_reason,
            "objects": kwargs.get('objects', []),
            "raw_data": kwargs  # Include all your custom parameters
        }
        
        return self._send_event(event_data, f"Custom {event_type}")
    
    def _send_event(self, event_data: Dict[str, Any], description: str) -> Dict[str, Any]:
        """Send event to webhook server"""
        print(f"\n📤 Sending {description} event:")
        print(f"   Camera: {event_data['camera_id']}")
        print(f"   Type: {event_data['event_type']}")
        print(f"   Reason: {event_data['reason']}")
        print(f"   Confidence: {event_data['confidence']}%")
        
        try:
            resp = self.session.post(
                f"{self.webhook_url}/webhook",
                json=event_data,
                timeout=10
            )
            
            if resp.status_code == 200:
                result = resp.json()
                print(f"   ✅ Event accepted by webhook server")
                print(f"   Response: {result}")
                return result
            else:
                print(f"   ❌ Failed to send event: {resp.status_code}")
                print(f"   Response: {resp.text}")
                return {}
                
        except Exception as e:
            print(f"   ❌ Error sending event: {e}")
            return {}
    
    def test_all_event_types(self):
        """Test various event types"""
        print("\n🧪 Testing all event types...")
        
        # Test person detection
        self.send_person_detection("cam1", 95)
        time.sleep(2)
        
        # Test vehicle detection  
        self.send_vehicle_detection("cam2", "car")
        time.sleep(2)
        
        # Test line crossing
        self.send_line_crossing("cam1", "in")
        time.sleep(2)
        
        # Test custom event
        self.send_custom_event(
            camera_id="cam1",
            event_type="motion",
            custom_reason="Suspicious activity detected in restricted area",
            confidence=87,
            objects=[
                {
                    "type": "person",
                    "confidence": 87,
                    "attributes": {
                        "area": "restricted_zone",
                        "behavior": "loitering",
                        "duration": "5_minutes"
                    }
                }
            ]
        )
        
        print("\n✅ All test events sent!")
    
    def show_camera_endpoints(self):
        """Show webhook endpoints for each camera"""
        print("\n🌐 Webhook endpoints for cameras:")
        
        cameras = [
            {"id": "cam1", "name": "Camera 1 - Port 3333"},
            {"id": "cam2", "name": "Camera 2 - Port 1111"}
        ]
        
        for cam in cameras:
            print(f"   {cam['name']}:")
            print(f"     Generic:  {self.webhook_url}/webhook")
            print(f"     Specific: {self.webhook_url}/webhook/{cam['id']}")
            print()
    
    def show_example_curl_commands(self):
        """Show example curl commands"""
        print("\n📋 Example curl commands to send events:")
        print()
        

        examples = [
            {
                "title": "Person detection with custom parameters",
                "command": """curl -X POST "http://localhost:8765/webhook" \\
  -H "Content-Type: application/json" \\
  -d '{
    "camera_id": "cam1",
    "event_type": "person",
    "confidence": 95,
    "reason": "Person entered through main door",
    "objects": [{
      "type": "person",
      "confidence": 95,
      "attributes": {
        "entrance": "main_door",
        "time_of_day": "evening"
      }
    }]
  }'"""
            },
            {
                "title": "Vehicle detection",
                "command": """curl -X POST "http://localhost:8765/webhook/cam2" \\
  -H "Content-Type: application/json" \\
  -d '{
    "event_type": "vehicle",
    "reason": "Unauthorized vehicle in parking",
    "confidence": 89,
    "objects": [{
      "type": "truck",
      "confidence": 89,
      "attributes": {
        "license_plate": "ABC-123",
        "color": "white",
        "area": "employee_parking"
      }
    }]
  }'"""
            },
            {
                "title": "Line crossing event",
                "command": """curl -X POST "http://localhost:8765/webhook" \\
  -H "Content-Type: application/json" \\
  -d '{
    "camera_id": "cam1",
    "event_type": "line_crossing",
    "confidence": 98,
    "reason": "A person crossed the entrance line going IN with 95% confidence",
    "objects": [{
      "type": "person",
      "confidence": 95,
      "attributes": {
        "line_name": "entrance",
        "direction": "in",
        "object_type": "person"
      }
    }]
  }'"""
            }
        ]
        
        for i, example in enumerate(examples, 1):
            print(f"{i}. {example['title']}:")
            print(example['command'])
            print()


def main():
    """Main demo function"""
    print("=" * 60)
    print("🎥 SHINOBI WEBHOOK EVENT DEMONSTRATION")
    print("=" * 60)
    
    demo = WebhookDemo()
    
    # Check if server is running
    if not demo.check_server_status():
        print("\n❌ Webhook server is not running!")
        print("Please start the camera system first:")
        print("   python main.py")
        return
    
    # Show endpoints
    demo.show_camera_endpoints()
    
    # Show curl examples
    demo.show_example_curl_commands()
    
    # Ask user what to do
    print("What would you like to do?")
    print("1. Send test events to demonstrate the system")
    print("2. Send a custom event with your own parameters")
    print("3. Show curl command examples only")
    print("4. Exit")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        demo.test_all_event_types()
        
        print("\n⏳ Waiting 10 seconds for processing...")
        time.sleep(10)
        
        # Check server stats again
        demo.check_server_status()
        
        print("\n📋 Next steps:")
        print("1. Check Shinobi interface - events should appear in the event list")
        print("2. Check temp_recordings/ - recent recordings should be moved to permanent_recordings/")
        print("3. Look for event_info.json files with your custom parameters")
        
    elif choice == "2":
        print("\nSend custom event:")
        camera_id = input("Camera ID (cam1/cam2): ").strip() or "cam1"
        event_type = input("Event type (motion/person/vehicle/line_crossing): ").strip() or "motion"
        reason = input("Custom reason/description: ").strip() or "Custom event"
        confidence = input("Confidence (0-100): ").strip() or "100"
        
        try:
            confidence = int(confidence)
        except ValueError:
            confidence = 100
        
        demo.send_custom_event(
            camera_id=camera_id,
            event_type=event_type,
            custom_reason=reason,
            confidence=confidence
        )
        
    elif choice == "3":
        demo.show_example_curl_commands()
        
    else:
        print("Exiting...")
        return
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
