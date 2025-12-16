"""
Shinobi NVR Client

Supports:
- Monitor registration with continuous recording
- Motion trigger API
- Recording list and download
- Stream URLs for VLC
"""

import requests
import json
import os
from typing import List, Optional
from loguru import logger


class ShinobiClient:
    """Shinobi NVR API client"""
    
    def __init__(self, base_url: str, api_key: str, group_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.group_key = group_key
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, data=None, params=None):
        """Make API request"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'GET':
                resp = self.session.get(url, params=params, timeout=30)
            elif method == 'POST':
                resp = self.session.post(url, json=data, params=params, timeout=30)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"API error: {e}")
            return None

    def add_monitor(self, monitor_id: str, name: str, rtsp_url: str,
                    mode: str = "record",
                    segment_length: str = "600",
                    **kwargs) -> bool:
        """
        Add a monitor configured for continuous recording.
        
        Modes:
        - "record": Continuous recording (what we want)
        - "start": Watch mode (only records on events)
        - "idle": Disabled
        """
        endpoint = f"/{self.api_key}/configureMonitor/{self.group_key}/{monitor_id}"
        
        details = {
            "auto_host": rtsp_url,
            "auto_host_enable": "1",
            "rtsp_transport": kwargs.get("rtsp_transport", "tcp"),
            
            # Video settings
            "stream_vcodec": "copy",
            "stream_acodec": kwargs.get("audio_codec", "no"),
            
            # Recording settings
            "vcodec": "copy",
            "crf": "1",
            
            # Segment length (in seconds) - how long each recording file is
            "cutoff": segment_length,
            
            # Storage
            "max_keep_days": kwargs.get("days_to_keep", "1"),
            "dir": kwargs.get("storage_dir", ""),
            
            # Stream output for VLC
            "stream_type": kwargs.get("stream_type", "hls"),
            "hls_time": "2",
            "hls_list_size": "3",
        }
        
        config = {
            "mid": monitor_id,
            "name": name,
            "type": "h264",
            "protocol": "rtsp",
            "host": rtsp_url,
            "path": "",
            "port": "",
            "ext": "mp4",
            "fps": kwargs.get("fps", ""),
            "width": kwargs.get("width", "1920"),
            "height": kwargs.get("height", "1080"),
            
            # IMPORTANT: mode="record" for continuous recording
            "mode": mode,
            
            # Storage settings
            "storage_max_percent": kwargs.get("storage_max_percent", "95"),
            "delete_old": "1",
            
            "details": json.dumps(details)
        }
        
        result = self._request('POST', endpoint, data=config)
        
        if result and result.get('ok'):
            logger.info(f"✅ Added monitor {monitor_id}: {name} (mode={mode})")
            return True
        else:
            logger.error(f"❌ Failed to add monitor {monitor_id}: {result}")
            return False

    def update_mode(self, monitor_id: str, mode: str) -> bool:
        """Change monitor mode"""
        endpoint = f"/{self.api_key}/monitor/{self.group_key}/{monitor_id}/{mode}"
        result = self._request('GET', endpoint)
        return result and result.get('ok')

    def trigger_motion(self, monitor_id: str, 
                       event_name: str = "Motion",
                       reason: str = "External trigger",
                       confidence: int = 100) -> bool:
        """Trigger motion event"""
        endpoint = f"/{self.api_key}/motion/{self.group_key}/{monitor_id}"
        
        trigger_data = {
            "plug": monitor_id,
            "name": event_name,
            "reason": reason,
            "confidence": confidence
        }
        
        params = {"data": json.dumps(trigger_data)}
        result = self._request('GET', endpoint, params=params)
        
        if result and result.get('ok'):
            logger.debug(f"Motion triggered for {monitor_id}")
            return True
        return False

    def get_monitors(self) -> List[dict]:
        """Get all monitors"""
        endpoint = f"/{self.api_key}/monitor/{self.group_key}"
        result = self._request('GET', endpoint)
        
        if result:
            return result if isinstance(result, list) else result.get('monitors', [])
        return []

    def get_recordings(self, monitor_id: str, 
                       start_date: str = None, 
                       end_date: str = None) -> List[dict]:
        """Get recordings for a monitor"""
        endpoint = f"/{self.api_key}/videos/{self.group_key}/{monitor_id}"
        
        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date
        
        result = self._request('GET', endpoint, params=params)
        
        if result:
            videos = result.get('videos', result) if isinstance(result, dict) else result
            return videos if isinstance(videos, list) else []
        return []

    def get_recording_url(self, monitor_id: str, filename: str) -> str:
        """Get direct URL to a recording"""
        return f"{self.base_url}/{self.api_key}/videos/{self.group_key}/{monitor_id}/{filename}"

    def download_recording(self, monitor_id: str, filename: str, save_path: str) -> bool:
        """Download a recording to local storage"""
        url = self.get_recording_url(monitor_id, filename)
        
        try:
            response = self.session.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False

    def get_stream_url(self, monitor_id: str, stream_type: str = "hls") -> str:
        """Get VLC-compatible stream URL"""
        if stream_type == "hls":
            return f"{self.base_url}/{self.api_key}/hls/{self.group_key}/{monitor_id}/s.m3u8"
        elif stream_type == "mjpeg":
            return f"{self.base_url}/{self.api_key}/mjpeg/{self.group_key}/{monitor_id}"
        elif stream_type == "flv":
            return f"{self.base_url}/{self.api_key}/flv/{self.group_key}/{monitor_id}/s.flv"
        elif stream_type == "mp4":
            return f"{self.base_url}/{self.api_key}/mp4/{self.group_key}/{monitor_id}/s.mp4"
        return self.get_stream_url(monitor_id, "hls")

    def get_snapshot_url(self, monitor_id: str) -> str:
        """Get JPEG snapshot URL"""
        return f"{self.base_url}/{self.api_key}/jpeg/{self.group_key}/{monitor_id}/s.jpg"

    def delete_monitor(self, monitor_id: str) -> bool:
        """Delete a monitor"""
        endpoint = f"/{self.api_key}/configureMonitor/{self.group_key}/{monitor_id}/delete"
        result = self._request('GET', endpoint)
        return result and result.get('ok')