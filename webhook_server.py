"""
FastAPI Webhook Server for ONVIF Events

Receives webhook events from ONVIF-compatible cameras/NVRs for:
- Person detection
- Car/Vehicle detection
- Motion detection
- Line crossing
- Intrusion detection
- Face detection
- And other analytics events

Forwards events to Shinobi NVR motion API to trigger recording.
"""

import asyncio
import json
import hashlib
import hmac
from datetime import datetime
from typing import Optional, Dict, Any, Callable, List
from enum import Enum
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from loguru import logger

from shinobi_client import ShinobiClient


# ==================== Event Models ====================

class EventType(str, Enum):
    """Supported ONVIF/Analytics event types"""
    MOTION = "motion"
    PERSON = "person"
    VEHICLE = "vehicle"
    CAR = "car"
    FACE = "face"
    LINE_CROSSING = "line_crossing"
    INTRUSION = "intrusion"
    TAMPER = "tamper"
    LOITERING = "loitering"
    OBJECT_LEFT = "object_left"
    OBJECT_REMOVED = "object_removed"
    CROWD = "crowd"
    AUDIO = "audio"
    UNKNOWN = "unknown"


class BoundingBox(BaseModel):
    """Object bounding box in frame"""
    x: float = Field(ge=0, le=1, description="X coordinate (0-1)")
    y: float = Field(ge=0, le=1, description="Y coordinate (0-1)")
    width: float = Field(ge=0, le=1, description="Width (0-1)")
    height: float = Field(ge=0, le=1, description="Height (0-1)")


class DetectedObject(BaseModel):
    """Detected object details"""
    type: str = Field(description="Object type (person, car, face, etc.)")
    confidence: float = Field(ge=0, le=100, description="Detection confidence 0-100")
    bounding_box: Optional[BoundingBox] = None
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ONVIFWebhookEvent(BaseModel):
    """
    Standard webhook event payload.
    Supports various camera manufacturers and ONVIF formats.
    """
    # Required fields
    camera_id: str = Field(description="Camera/Monitor ID matching Shinobi")
    event_type: str = Field(description="Event type (motion, person, vehicle, etc.)")
    
    # Optional fields
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp")
    topic: Optional[str] = Field(default=None, description="ONVIF topic path")
    source: Optional[str] = Field(default=None, description="Event source identifier")
    state: Optional[str] = Field(default="active", description="Event state (active/inactive)")
    confidence: Optional[float] = Field(default=100, ge=0, le=100)
    reason: Optional[str] = Field(default=None, description="Event description")
    
    # Detection details
    objects: Optional[List[DetectedObject]] = Field(default_factory=list)
    
    # Raw data passthrough
    raw_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class HikvisionEvent(BaseModel):
    """Hikvision ISAPI event format"""
    ipAddress: Optional[str] = None
    channelID: Optional[str] = None
    dateTime: Optional[str] = None
    eventType: Optional[str] = None
    eventState: Optional[str] = None
    eventDescription: Optional[str] = None
    DetectionRegionList: Optional[List[Dict]] = None


class DahuaEvent(BaseModel):
    """Dahua event format"""
    Code: Optional[str] = None
    Action: Optional[str] = None
    Index: Optional[int] = None
    Data: Optional[Dict] = None


# ==================== Webhook Server ====================

class WebhookServer:
    """
    FastAPI-based webhook server for ONVIF events.
    """
    
    def __init__(
        self,
        shinobi_client: ShinobiClient,
        host: str = "0.0.0.0",
        port: int = 8765,
        webhook_secret: Optional[str] = None,
        camera_mapping: Optional[Dict[str, str]] = None
    ):
        self.shinobi = shinobi_client
        self.host = host
        self.port = port
        self.webhook_secret = webhook_secret
        
        # Map external camera IDs to Shinobi monitor IDs
        self.camera_mapping = camera_mapping or {}
        
        # Event callbacks for custom handling
        self.event_callbacks: List[Callable] = []
        
        # Event statistics
        self.stats = {
            "total_events": 0,
            "events_by_type": {},
            "events_by_camera": {},
            "last_event_time": None,
            "errors": 0
        }
        
        # Create FastAPI app
        self.app = self._create_app()
    
    def _create_app(self) -> FastAPI:
        """Create FastAPI application with routes"""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            logger.info(f"🚀 Webhook server starting on {self.host}:{self.port}")
            yield
            logger.info("Webhook server shutting down")
        
        app = FastAPI(
            title="ONVIF Webhook Server",
            description="Receives ONVIF camera events and forwards to Shinobi NVR",
            version="1.0.0",
            lifespan=lifespan
        )
        
        # Routes
        @app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "stats": self.stats
            }
        
        @app.get("/stats")
        async def get_stats():
            """Get event statistics"""
            return self.stats
        
        @app.post("/webhook")
        async def receive_webhook(
            request: Request,
            background_tasks: BackgroundTasks,
            x_signature: Optional[str] = Header(None, alias="X-Signature"),
            x_camera_id: Optional[str] = Header(None, alias="X-Camera-ID")
        ):
            """
            Main webhook endpoint for receiving events.
            Accepts multiple formats and normalizes them.
            """
            body = await request.body()
            
            # Verify signature if secret is configured
            if self.webhook_secret and x_signature:
                expected = hmac.new(
                    self.webhook_secret.encode(),
                    body,
                    hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(x_signature, expected):
                    raise HTTPException(status_code=401, detail="Invalid signature")
            
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                # Try to parse as form data or XML
                content_type = request.headers.get("content-type", "")
                if "xml" in content_type:
                    data = await self._parse_xml_event(body.decode())
                else:
                    raise HTTPException(status_code=400, detail="Invalid JSON")
            
            # Normalize event to standard format
            event = await self._normalize_event(data, x_camera_id)
            
            if event:
                # Process in background to respond quickly
                background_tasks.add_task(self._process_event, event)
                return {"status": "accepted", "event_id": id(event)}
            
            return {"status": "ignored", "reason": "Could not parse event"}
        
        @app.post("/webhook/hikvision")
        async def receive_hikvision(
            request: Request,
            background_tasks: BackgroundTasks
        ):
            """Hikvision ISAPI format endpoint"""
            body = await request.body()
            
            try:
                data = json.loads(body)
            except:
                data = await self._parse_xml_event(body.decode())
            
            event = await self._normalize_hikvision(data)
            
            if event:
                background_tasks.add_task(self._process_event, event)
                return {"status": "accepted"}
            
            return {"status": "ignored"}
        
        @app.post("/webhook/dahua")
        async def receive_dahua(
            request: Request,
            background_tasks: BackgroundTasks
        ):
            """Dahua format endpoint"""
            body = await request.body()
            data = json.loads(body)
            
            event = await self._normalize_dahua(data)
            
            if event:
                background_tasks.add_task(self._process_event, event)
                return {"status": "accepted"}
            
            return {"status": "ignored"}
        
        @app.post("/webhook/{camera_id}")
        async def receive_camera_webhook(
            camera_id: str,
            request: Request,
            background_tasks: BackgroundTasks
        ):
            """Camera-specific webhook endpoint"""
            body = await request.body()
            
            try:
                data = json.loads(body)
            except:
                data = {"raw": body.decode()}
            
            event = await self._normalize_event(data, camera_id)
            
            if event:
                background_tasks.add_task(self._process_event, event)
                return {"status": "accepted"}
            
            return {"status": "ignored"}
        
        @app.post("/test/{camera_id}/{event_type}")
        async def test_event(
            camera_id: str,
            event_type: str,
            background_tasks: BackgroundTasks
        ):
            """Test endpoint to trigger events manually"""
            event = ONVIFWebhookEvent(
                camera_id=camera_id,
                event_type=event_type,
                timestamp=datetime.now().isoformat(),
                reason="Manual test trigger",
                confidence=100
            )
            
            background_tasks.add_task(self._process_event, event)
            return {"status": "test event triggered", "camera": camera_id, "type": event_type}
        
        return app
    
    async def _parse_xml_event(self, xml_content: str) -> Dict:
        """Parse XML event data (ONVIF/ISAPI format)"""
        import re
        
        result = {}
        
        # Extract common fields with regex
        patterns = {
            "eventType": r"<eventType>([^<]+)</eventType>",
            "eventState": r"<eventState>([^<]+)</eventState>",
            "channelID": r"<channelID>([^<]+)</channelID>",
            "dateTime": r"<dateTime>([^<]+)</dateTime>",
            "ipAddress": r"<ipAddress>([^<]+)</ipAddress>",
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, xml_content, re.IGNORECASE)
            if match:
                result[key] = match.group(1)
        
        # Check for detection types
        if "VideoMotion" in xml_content:
            result["eventType"] = "motion"
        elif "linedetection" in xml_content.lower():
            result["eventType"] = "line_crossing"
        elif "fielddetection" in xml_content.lower() or "intrusion" in xml_content.lower():
            result["eventType"] = "intrusion"
        
        result["raw_xml"] = xml_content
        return result
    
    async def _normalize_event(
        self,
        data: Dict,
        camera_id_hint: Optional[str] = None
    ) -> Optional[ONVIFWebhookEvent]:
        """Normalize various event formats to standard format"""
        
        # Try to extract camera ID
        camera_id = (
            camera_id_hint or
            data.get("camera_id") or
            data.get("cameraId") or
            data.get("channelID") or
            data.get("channel") or
            data.get("monitor_id") or
            data.get("source") or
            "unknown"
        )
        
        # Map to Shinobi monitor ID if configured
        camera_id = self.camera_mapping.get(camera_id, camera_id)
        
        # Determine event type
        event_type = self._detect_event_type(data)
        
        # Check if event is active (not an "end" event)
        state = str(data.get("state", data.get("eventState", data.get("Action", "active")))).lower()
        if state in ["inactive", "stop", "end", "off", "false", "0"]:
            logger.debug(f"Ignoring inactive event for {camera_id}")
            return None
        
        # Extract timestamp
        timestamp = (
            data.get("timestamp") or
            data.get("dateTime") or
            data.get("time") or
            datetime.now().isoformat()
        )
        
        # Extract confidence
        confidence = float(data.get("confidence", data.get("probability", 100)))
        
        # Extract detected objects
        objects = self._extract_objects(data)
        
        # Build reason string
        reason = data.get("reason") or data.get("eventDescription") or f"{event_type} detected"
        if objects:
            object_types = [obj.type for obj in objects]
            reason = f"{event_type}: {', '.join(object_types)}"
        
        return ONVIFWebhookEvent(
            camera_id=camera_id,
            event_type=event_type,
            timestamp=timestamp,
            topic=data.get("topic", ""),
            source=data.get("source", "webhook"),
            state="active",
            confidence=confidence,
            reason=reason,
            objects=objects,
            raw_data=data
        )
    
    def _detect_event_type(self, data: Dict) -> str:
        """Detect event type from various field names"""
        # Check explicit event type fields
        event_type = str(
            data.get("event_type") or
            data.get("eventType") or
            data.get("type") or
            data.get("Code") or
            data.get("topic", "")
        ).lower()
        
        # Map to standard types
        type_mapping = {
            "motion": EventType.MOTION,
            "videomotion": EventType.MOTION,
            "cellmotion": EventType.MOTION,
            "person": EventType.PERSON,
            "human": EventType.PERSON,
            "pedestrian": EventType.PERSON,
            "vehicle": EventType.VEHICLE,
            "car": EventType.CAR,
            "face": EventType.FACE,
            "facedetection": EventType.FACE,
            "line": EventType.LINE_CROSSING,
            "linecross": EventType.LINE_CROSSING,
            "linedetection": EventType.LINE_CROSSING,
            "tripwire": EventType.LINE_CROSSING,
            "intrusion": EventType.INTRUSION,
            "field": EventType.INTRUSION,
            "regionentrance": EventType.INTRUSION,
            "tamper": EventType.TAMPER,
            "videotamper": EventType.TAMPER,
            "loitering": EventType.LOITERING,
            "abandoned": EventType.OBJECT_LEFT,
            "objectremoval": EventType.OBJECT_REMOVED,
            "crowd": EventType.CROWD,
            "audio": EventType.AUDIO,
        }
        
        for key, value in type_mapping.items():
            if key in event_type:
                return value.value
        
        # Check for object types in data
        if "objects" in data or "detections" in data:
            objects = data.get("objects") or data.get("detections", [])
            for obj in objects:
                obj_type = str(obj.get("type", obj.get("class", ""))).lower()
                if obj_type in ["person", "human"]:
                    return EventType.PERSON.value
                elif obj_type in ["car", "vehicle", "truck", "bus"]:
                    return EventType.VEHICLE.value
        
        return EventType.MOTION.value
    
    def _extract_objects(self, data: Dict) -> List[DetectedObject]:
        """Extract detected objects from event data"""
        objects = []
        
        raw_objects = data.get("objects") or data.get("detections") or data.get("targets", [])
        
        for obj in raw_objects:
            try:
                bbox = None
                if "boundingBox" in obj or "bbox" in obj or "region" in obj:
                    box_data = obj.get("boundingBox") or obj.get("bbox") or obj.get("region", {})
                    bbox = BoundingBox(
                        x=float(box_data.get("x", 0)),
                        y=float(box_data.get("y", 0)),
                        width=float(box_data.get("width", box_data.get("w", 0))),
                        height=float(box_data.get("height", box_data.get("h", 0)))
                    )
                
                detected = DetectedObject(
                    type=obj.get("type") or obj.get("class") or "unknown",
                    confidence=float(obj.get("confidence", obj.get("probability", 100))),
                    bounding_box=bbox,
                    attributes=obj.get("attributes", {})
                )
                objects.append(detected)
            except Exception as e:
                logger.debug(f"Failed to parse object: {e}")
        
        return objects
    
    async def _normalize_hikvision(self, data: Dict) -> Optional[ONVIFWebhookEvent]:
        """Normalize Hikvision ISAPI format"""
        camera_id = data.get("channelID", data.get("ipAddress", "unknown"))
        camera_id = self.camera_mapping.get(camera_id, camera_id)
        
        event_type = self._detect_event_type(data)
        
        state = data.get("eventState", "active")
        if state.lower() in ["inactive", "stop"]:
            return None
        
        return ONVIFWebhookEvent(
            camera_id=camera_id,
            event_type=event_type,
            timestamp=data.get("dateTime", datetime.now().isoformat()),
            topic=data.get("eventType", ""),
            state="active",
            reason=data.get("eventDescription", f"Hikvision {event_type}"),
            raw_data=data
        )
    
    async def _normalize_dahua(self, data: Dict) -> Optional[ONVIFWebhookEvent]:
        """Normalize Dahua format"""
        camera_id = str(data.get("Index", 0))
        camera_id = self.camera_mapping.get(camera_id, camera_id)
        
        action = data.get("Action", "Start")
        if action.lower() == "stop":
            return None
        
        event_type = self._detect_event_type(data)
        
        return ONVIFWebhookEvent(
            camera_id=camera_id,
            event_type=event_type,
            timestamp=datetime.now().isoformat(),
            topic=data.get("Code", ""),
            state="active",
            reason=f"Dahua {data.get('Code', event_type)}",
            raw_data=data
        )
    
    async def _process_event(self, event: ONVIFWebhookEvent):
        """Process normalized event - forward to Shinobi with detection type as event name"""
        try:
            # Update statistics
            self.stats["total_events"] += 1
            self.stats["events_by_type"][event.event_type] = \
                self.stats["events_by_type"].get(event.event_type, 0) + 1
            self.stats["events_by_camera"][event.camera_id] = \
                self.stats["events_by_camera"].get(event.camera_id, 0) + 1
            self.stats["last_event_time"] = datetime.now().isoformat()
            
            # Log event
            logger.info(f"🚨 {event.event_type.upper()} on {event.camera_id}: {event.reason}")
            
            if event.objects:
                for obj in event.objects:
                    logger.info(f"   └─ {obj.type}: {obj.confidence:.1f}% confidence")
            
            # ===== BUILD EVENT NAME FOR SHINOBI =====
            # This is what shows up in Shinobi's event list!
            # Format: "Person" or "Vehicle: car, truck" or "Motion"
            
            event_name = event.event_type.replace("_", " ").title()
            
            # If we have specific objects detected, include them
            if event.objects:
                object_types = list(set([obj.type for obj in event.objects]))
                if object_types and object_types[0].lower() != event.event_type.lower():
                    event_name = f"{event_name}: {', '.join(object_types[:3])}"
            
            # Build detailed reason
            reason_parts = []
            if event.objects:
                for obj in event.objects[:3]:
                    reason_parts.append(f"{obj.type}({obj.confidence:.0f}%)")
            if event.reason and event.reason != f"{event.event_type} detected":
                reason_parts.append(event.reason)
            
            reason = " | ".join(reason_parts) if reason_parts else event.reason
            
            # ===== TRIGGER SHINOBI MOTION API =====
            success = self.shinobi.trigger_motion(
                monitor_id=event.camera_id,
                event_name=event_name,  # This shows as the event type in Shinobi!
                reason=reason,
                confidence=int(event.confidence)
            )
            
            if success:
                logger.debug(f"✅ Shinobi triggered: {event_name} for {event.camera_id}")
            else:
                logger.warning(f"⚠️ Failed to trigger Shinobi for {event.camera_id}")
            
            # Call registered callbacks
            for callback in self.event_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
            
        except Exception as e:
            logger.error(f"Event processing error: {e}")
            self.stats["errors"] += 1
    
    def add_event_callback(self, callback: Callable):
        """Register callback for processed events"""
        self.event_callbacks.append(callback)
    
    def get_webhook_url(self, camera_id: Optional[str] = None) -> str:
        """Get webhook URL to configure in camera"""
        base = f"http://{self.host}:{self.port}"
        if camera_id:
            return f"{base}/webhook/{camera_id}"
        return f"{base}/webhook"
    
    async def run(self):
        """Run the webhook server"""
        import uvicorn
        
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()


# ==================== Standalone Usage ====================

def create_webhook_server(config: dict) -> WebhookServer:
    """Create webhook server from config dict"""
    shinobi_cfg = config.get('shinobi', {})
    webhook_cfg = config.get('webhook', {})
    
    shinobi = ShinobiClient(
        base_url=shinobi_cfg.get('base_url'),
        api_key=shinobi_cfg.get('api_key'),
        group_key=shinobi_cfg.get('group_key')
    )
    
    # Build camera mapping from config
    camera_mapping = {}
    for cam in config.get('cameras', []):
        if 'external_id' in cam:
            camera_mapping[cam['external_id']] = cam['id']
        if 'ip' in cam:
            camera_mapping[cam['ip']] = cam['id']
        if 'channel' in cam:
            camera_mapping[str(cam['channel'])] = cam['id']
    
    return WebhookServer(
        shinobi_client=shinobi,
        host=webhook_cfg.get('host', '0.0.0.0'),
        port=webhook_cfg.get('port', 8765),
        webhook_secret=webhook_cfg.get('secret'),
        camera_mapping=camera_mapping
    )


async def main():
    """Run webhook server standalone"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ONVIF Webhook Server')
    parser.add_argument('-c', '--config', default='config.json', help='Config file')
    parser.add_argument('-p', '--port', type=int, default=8765, help='Server port')
    parser.add_argument('--host', default='0.0.0.0', help='Server host')
    
    args = parser.parse_args()
    
    with open(args.config) as f:
        config = json.load(f)
    
    # Override from command line
    if 'webhook' not in config:
        config['webhook'] = {}
    config['webhook']['port'] = args.port
    config['webhook']['host'] = args.host
    
    server = create_webhook_server(config)
    
    print(f"\n🌐 Webhook URLs to configure in your cameras:")
    print(f"   Generic:   {server.get_webhook_url()}")
    print(f"   Hikvision: http://{args.host}:{args.port}/webhook/hikvision")
    print(f"   Dahua:     http://{args.host}:{args.port}/webhook/dahua")
    
    for cam in config.get('cameras', []):
        print(f"   {cam.get('name', cam['id'])}: {server.get_webhook_url(cam['id'])}")
    
    print(f"\n📊 Health check: http://{args.host}:{args.port}/health")
    print(f"🧪 Test event:   POST http://{args.host}:{args.port}/test/{{camera_id}}/{{event_type}}\n")
    
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())