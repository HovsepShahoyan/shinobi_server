"""
PTZ endpoints for webhook_receiver.py
Based on REAL Aragats-ONVIF Django backend API (views.py)

Real API endpoints discovered:
  POST /api/system/set_ptz_direction/  → {"direction": "ptz_up/ptz_down/ptz_left/ptz_right/ptz_middle/range_finder/near_focus/far_focus", "start": true/false}
  POST /api/system/move_ptz/           → {"azimuth": int, "elevation": int}
  POST /api/system/set_zoom/           → {"level": 1-6}
  GET  /api/system/current_zoom/       → {"zoom": int}
  GET  /api/system/ptz_position/       → {"az": int, "el": int}
  GET  /api/system/telemetry/          → {"azimuth_degrees": float, "elevation_degrees": float, "distance": float}
  POST /api/system/set_speed/          → {"speed": 1-8}
  POST /api/system/send_control/       → {"prop": "UserControls", "key": str, "value": any}
  POST /api/v1/users/measure-range/    → needs Bearer token, triggers range finder
  GET  /api/system/snapshot/           → returns JPEG image
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
import requests
import asyncio

# ==================== CONFIGURATION ====================

# CHANGE THIS to your Jetson's IP address
JETSON_URL = "http://192.168.1.100:8000"

# Jetson auth token (get from your login API)
# The range finder requires this token
JETSON_AUTH_TOKEN = ""  # Set after login

# Day camera zoom levels (index 0-5 → level 1-6)
DAY_ZOOM_VALUES = [1, 5, 15, 30, 60, 68]

# Digital (IR/night) zoom values
DIGITAL_ZOOM_VALUES = [1, 2, 4, 8]

# ==================== MODELS ====================

class PTZDirectionRequest(BaseModel):
    direction: str   # ptz_up, ptz_down, ptz_left, ptz_right, ptz_middle, near_focus, far_focus
    start: bool      # True = start moving, False = stop

class PTZMoveAbsoluteRequest(BaseModel):
    azimuth: int     # absolute azimuth encoder value
    elevation: int   # absolute elevation encoder value

class ZoomRequest(BaseModel):
    level: int       # 1-6 for day camera

class SpeedRequest(BaseModel):
    speed: int       # 1-8

class SendControlRequest(BaseModel):
    prop: str        # e.g. "UserControls"
    key: str         # e.g. "day_zoom", "digital_zoom", "brightness", "contrast", "palette"
    value: Any       # depends on key

class DayZoomRequest(BaseModel):
    direction: str   # "up" or "down"

class DigitalZoomRequest(BaseModel):
    direction: str   # "up" or "down"

class BrightnessRequest(BaseModel):
    direction: str   # "up" or "down"

class ContrastRequest(BaseModel):
    direction: str   # "up" or "down"

class ThermalModeRequest(BaseModel):
    mode: str        # "blackhot" or "whitehot"

# ==================== ROUTER ====================

ptz_router = APIRouter(prefix="/api/jetson", tags=["Jetson PTZ Control"])

# ==================== HELPER ====================

def jetson_post(endpoint: str, data: dict, token: str = None) -> dict:
    """POST to Jetson backend"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        resp = requests.post(
            f"{JETSON_URL}{endpoint}",
            json=data,
            headers=headers,
            timeout=5
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {"success": True}
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail=f"Cannot connect to Jetson at {JETSON_URL}")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Jetson request timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def jetson_get(endpoint: str, token: str = None) -> dict:
    """GET from Jetson backend"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        resp = requests.get(
            f"{JETSON_URL}{endpoint}",
            headers=headers,
            timeout=5
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail=f"Cannot connect to Jetson at {JETSON_URL}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PTZ DIRECTION (START/STOP) ====================

@ptz_router.post("/ptz/direction")
async def ptz_direction(req: PTZDirectionRequest):
    """
    Start or stop PTZ movement in a direction.
    Frontend should call with start=True on mousedown, start=False on mouseup.
    
    Directions: ptz_up, ptz_down, ptz_left, ptz_right, ptz_middle, near_focus, far_focus
    """
    return jetson_post("/api/system/set_ptz_direction/", {
        "direction": req.direction,
        "start": req.start
    })

@ptz_router.post("/ptz/move-absolute")
async def ptz_move_absolute(req: PTZMoveAbsoluteRequest):
    """
    Move PTZ to absolute azimuth/elevation encoder position.
    Used when clicking on video to point camera at that location.
    """
    return jetson_post("/api/system/move_ptz/", {
        "azimuth": req.azimuth,
        "elevation": req.elevation
    })

# ==================== ZOOM ====================

@ptz_router.post("/zoom/set")
async def set_zoom(req: ZoomRequest):
    """Set zoom level directly (1-6 for day camera)"""
    if not 1 <= req.level <= 6:
        raise HTTPException(status_code=400, detail="Level must be 1-6")
    return jetson_post("/api/system/set_zoom/", {"level": req.level})

@ptz_router.post("/zoom/day")
async def day_zoom(req: DayZoomRequest):
    """
    Step day camera zoom up or down.
    Day zoom values: [1x, 5x, 15x, 30x, 60x, 68x] → levels 1-6
    """
    # Get current zoom to determine index
    try:
        current = jetson_get("/api/system/current_zoom/")
        current_level = current.get("zoom", 1)
        current_index = current_level - 1  # level is 1-based
    except:
        current_index = 0
    
    if req.direction == "up":
        new_index = min(len(DAY_ZOOM_VALUES) - 1, current_index + 1)
    else:
        new_index = max(0, current_index - 1)
    
    new_level = new_index + 1
    zoom_value = DAY_ZOOM_VALUES[new_index]
    
    # Set zoom level on camera
    jetson_post("/api/system/set_zoom/", {"level": new_level})
    
    # Also send via send_control (as Svelte frontend does)
    jetson_post("/api/system/send_control/", {
        "prop": "UserControls",
        "key": "day_zoom",
        "value": zoom_value
    })
    
    return {"success": True, "level": new_level, "zoom_value": zoom_value, "display": f"{zoom_value}x"}

@ptz_router.post("/zoom/digital")
async def digital_zoom(req: DigitalZoomRequest):
    """
    Step IR/digital zoom up or down.
    Digital zoom values: [1x, 2x, 4x, 8x]
    """
    # We need to track digital zoom index separately
    # For now, use send_control directly
    current_index = 0  # TODO: track state
    
    if req.direction == "up":
        new_index = min(len(DIGITAL_ZOOM_VALUES) - 1, current_index + 1)
    else:
        new_index = max(0, current_index - 1)
    
    zoom_value = DIGITAL_ZOOM_VALUES[new_index]
    
    jetson_post("/api/system/send_control/", {
        "prop": "UserControls",
        "key": "digital_zoom",
        "value": zoom_value
    })
    
    return {"success": True, "zoom_value": zoom_value, "display": f"{zoom_value}x"}

@ptz_router.get("/zoom/current")
async def get_current_zoom():
    """Get current zoom level"""
    return jetson_get("/api/system/current_zoom/")

# ==================== POSITION ====================

@ptz_router.get("/ptz/position")
async def get_ptz_position():
    """Get current PTZ position (azimuth + elevation encoder values)"""
    return jetson_get("/api/system/ptz_position/")

@ptz_router.get("/telemetry")
async def get_telemetry():
    """Get telemetry: azimuth_degrees, elevation_degrees, distance"""
    return jetson_get("/api/system/telemetry/")

# ==================== RANGE FINDER ====================

@ptz_router.post("/rangefinder/measure")
async def measure_range(token: Optional[str] = None):
    """
    Trigger range finder measurement.
    Requires auth token from Jetson login.
    Also triggers hardware via set_ptz_direction range_finder.
    """
    import time
    
    errors = []
    
    # Step 1: Log to backend (needs auth token)
    if token or JETSON_AUTH_TOKEN:
        auth_token = token or JETSON_AUTH_TOKEN
        try:
            jetson_post("/api/v1/users/measure-range/", {}, token=auth_token)
        except Exception as e:
            errors.append(f"Auth log failed: {e}")
    
    # Step 2: Trigger hardware button (start)
    try:
        jetson_post("/api/system/set_ptz_direction/", {
            "direction": "range_finder",
            "start": True
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Range finder trigger failed: {e}")
    
    # Step 3: Release after 100ms (same as Svelte frontend)
    await asyncio.sleep(0.1)
    
    jetson_post("/api/system/set_ptz_direction/", {
        "direction": "range_finder",
        "start": False
    })
    
    # Step 4: Get distance from telemetry
    await asyncio.sleep(0.5)  # Wait for measurement
    try:
        telemetry = jetson_get("/api/system/telemetry/")
        return {
            "success": True,
            "distance": telemetry.get("distance"),
            "warnings": errors
        }
    except:
        return {"success": True, "distance": None, "warnings": errors}

# ==================== SPEED ====================

@ptz_router.post("/speed")
async def set_speed(req: SpeedRequest):
    """Set PTZ movement speed (1-8)"""
    if not 1 <= req.speed <= 8:
        raise HTTPException(status_code=400, detail="Speed must be 1-8")
    return jetson_post("/api/system/set_speed/", {"speed": req.speed})

# ==================== IMAGE CONTROLS ====================

@ptz_router.post("/image/brightness")
async def set_brightness(req: BrightnessRequest):
    """Adjust brightness up or down by 10"""
    # Fetch current (not stored on backend, use default 50)
    current = 50  # TODO: track state
    
    if req.direction == "up":
        new_val = min(100, current + 10)
    else:
        new_val = max(0, current - 10)
    
    jetson_post("/api/system/send_control/", {
        "prop": "UserControls",
        "key": "brightness",
        "value": new_val
    })
    return {"success": True, "value": new_val}

@ptz_router.post("/image/contrast")
async def set_contrast(req: ContrastRequest):
    """Adjust contrast up or down by 10"""
    current = 50
    
    if req.direction == "up":
        new_val = min(100, current + 10)
    else:
        new_val = max(0, current - 10)
    
    jetson_post("/api/system/send_control/", {
        "prop": "UserControls",
        "key": "contrast",
        "value": new_val
    })
    return {"success": True, "value": new_val}

@ptz_router.post("/image/thermal-mode")
async def set_thermal_mode(req: ThermalModeRequest):
    """Set thermal mode: blackhot or whitehot"""
    palette_value = 1 if req.mode == "blackhot" else 0
    
    jetson_post("/api/system/send_control/", {
        "prop": "UserControls",
        "key": "palette",
        "value": palette_value
    })
    return {"success": True, "mode": req.mode}

# ==================== SEND CONTROL (GENERIC) ====================

@ptz_router.post("/control/send")
async def send_control(req: SendControlRequest):
    """
    Generic control sender.
    Keys: day_zoom, digital_zoom, brightness, contrast, palette, alphaD1, alphaD2
    """
    return jetson_post("/api/system/send_control/", {
        "prop": req.prop,
        "key": req.key,
        "value": req.value
    })

# ==================== SNAPSHOT ====================

@ptz_router.get("/snapshot")
async def get_snapshot():
    """Get camera snapshot (proxied from Jetson)"""
    from fastapi.responses import StreamingResponse
    import io
    
    try:
        resp = requests.get(f"{JETSON_URL}/api/system/snapshot/", timeout=5)
        resp.raise_for_status()
        return StreamingResponse(io.BytesIO(resp.content), media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== STATUS ====================

@ptz_router.get("/status")
async def get_jetson_status():
    """Check if Jetson backend is reachable"""
    try:
        resp = requests.get(f"{JETSON_URL}/", timeout=3)
        return {"online": True, "jetson_url": JETSON_URL}
    except:
        return {"online": False, "jetson_url": JETSON_URL}