"""
Local Recording Sync Manager

Downloads ALL recordings from Shinobi to local PC and manages storage:
- temp_recordings/: Auto-deleted after 1 hour
- permanent_recordings/: Event recordings kept forever

When ONVIF motion detected → marks recordings as permanent (won't be deleted)
"""

import os
import shutil
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Set, Dict, Optional
from dataclasses import dataclass, field
from loguru import logger


def make_naive(dt: datetime) -> datetime:
    """Convert datetime to naive (no timezone) for comparison"""
    if dt is None:
        return datetime.now()
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


@dataclass
class LocalRecording:
    """Tracks a downloaded recording"""
    filename: str
    camera_id: str
    filepath: str
    downloaded_at: datetime
    recording_time: datetime
    is_permanent: bool = False
    shinobi_url: str = ""


class LocalStorageManager:
    """
    Manages local storage of recordings downloaded from Shinobi.
    
    - Downloads new recordings periodically
    - Marks event recordings as permanent
    - Auto-deletes old temp recordings (>1 hour)
    """
    
    def __init__(self, 
                 shinobi_client,
                 temp_dir: str = "./temp_recordings",
                 permanent_dir: str = "./permanent_recordings",
                 temp_retention_hours: float = 1.0,
                 sync_interval_seconds: int = 30,
                 cleanup_interval_seconds: int = 300):
        
        self.shinobi = shinobi_client
        self.temp_dir = Path(temp_dir)
        self.permanent_dir = Path(permanent_dir)
        self.temp_retention = timedelta(hours=temp_retention_hours)
        self.sync_interval = sync_interval_seconds
        self.cleanup_interval = cleanup_interval_seconds
        
        # Track downloaded files
        self.recordings: Dict[str, LocalRecording] = {}  # filepath -> recording
        self.downloaded_files: Set[str] = set()  # shinobi filenames already downloaded
        
        # Event tracking - files to mark as permanent
        self.pending_permanent: Dict[str, datetime] = {}  # camera_id -> event_time
        self.pre_event_seconds = 60
        self.post_event_seconds = 60
        
        self.running = False
        self._sync_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Create directories
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.permanent_dir.mkdir(parents=True, exist_ok=True)

    def set_event_buffers(self, pre_seconds: int, post_seconds: int):
        """Set pre and post event buffer times"""
        self.pre_event_seconds = pre_seconds
        self.post_event_seconds = post_seconds

    def trigger_event(self, camera_id: str):
        """
        Called when motion event detected.
        Marks current time so recordings around this time become permanent.
        """
        now = datetime.now()
        self.pending_permanent[camera_id] = now
        logger.info(f"🔴 Event marked for {camera_id} at {now.strftime('%H:%M:%S')}")
        
        # Mark existing recordings that fall within pre-buffer as permanent
        self._mark_existing_as_permanent(camera_id, now)

    def _mark_existing_as_permanent(self, camera_id: str, event_time: datetime):
        """Mark existing downloaded recordings as permanent if within buffer window"""
        event_time = make_naive(event_time)
        # Use a larger window - pre_event_seconds before to post_event_seconds after
        window_start = event_time - timedelta(seconds=self.pre_event_seconds)
        window_end = event_time + timedelta(seconds=self.post_event_seconds)
        
        marked_count = 0
        for filepath, rec in list(self.recordings.items()):
            if rec.camera_id != camera_id:
                continue
            if rec.is_permanent:
                continue
            
            rec_time = make_naive(rec.recording_time)
            
            # Check if recording falls within the event window
            # Also mark recent recordings (within last 5 minutes) as a fallback
            recent_threshold = event_time - timedelta(minutes=5)
            
            if (window_start <= rec_time <= window_end) or (rec_time >= recent_threshold):
                self._move_to_permanent(rec, event_time)
                marked_count += 1
        
        if marked_count > 0:
            logger.info(f"📁 Marked {marked_count} recordings as permanent for {camera_id}")
        else:
            # Log available recordings for debugging
            available = [r.filename for r in self.recordings.values() 
                        if r.camera_id == camera_id and not r.is_permanent]
            if available:
                logger.debug(f"No recordings matched time window. Available: {available[:5]}")

    def _move_to_permanent(self, rec: LocalRecording, event_time: datetime):
        """Move a recording from temp to permanent storage"""
        if rec.is_permanent:
            return
        
        event_time = make_naive(event_time)
        
        # Create event folder
        event_folder = self.permanent_dir / rec.camera_id / event_time.strftime("%Y%m%d_%H%M%S")
        event_folder.mkdir(parents=True, exist_ok=True)
        
        new_path = event_folder / os.path.basename(rec.filepath)
        
        try:
            if os.path.exists(rec.filepath):
                shutil.copy2(rec.filepath, new_path)  # Copy instead of move to keep temp copy too
                rec.filepath = str(new_path)
                rec.is_permanent = True
                logger.info(f"✅ Saved to permanent: {new_path.name}")
        except Exception as e:
            logger.error(f"Failed to copy {rec.filepath}: {e}")

    async def _sync_loop(self):
        """Periodically download new recordings from Shinobi"""
        while self.running:
            try:
                await self._sync_recordings()
                await asyncio.sleep(self.sync_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync error: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                await asyncio.sleep(self.sync_interval)

    async def _sync_recordings(self):
        """Download new recordings from Shinobi"""
        monitors = self.shinobi.get_monitors()
        if not monitors:
            return
        
        for monitor in monitors:
            camera_id = monitor.get('mid')
            if not camera_id:
                continue
            
            # Get recent recordings
            recordings = self.shinobi.get_recordings(camera_id)
            if not recordings:
                continue
            
            for rec in recordings:
                filename = rec.get('filename') or rec.get('name')
                if not filename:
                    continue
                
                # Skip if already downloaded
                file_key = f"{camera_id}_{filename}"
                if file_key in self.downloaded_files:
                    continue
                
                # Download to temp
                await self._download_recording(camera_id, filename, rec)

    async def _download_recording(self, camera_id: str, filename: str, rec_info: dict):
        """Download a single recording from Shinobi"""
        file_key = f"{camera_id}_{filename}"
        
        # Determine save location
        camera_temp_dir = self.temp_dir / camera_id
        camera_temp_dir.mkdir(parents=True, exist_ok=True)
        
        save_path = camera_temp_dir / filename
        
        # Download
        success = self.shinobi.download_recording(camera_id, filename, str(save_path))
        
        if success:
            self.downloaded_files.add(file_key)
            
            # Parse recording time from filename or metadata
            rec_time = self._parse_recording_time(filename, rec_info)
            
            local_rec = LocalRecording(
                filename=filename,
                camera_id=camera_id,
                filepath=str(save_path),
                downloaded_at=datetime.now(),
                recording_time=rec_time,
                shinobi_url=self.shinobi.get_recording_url(camera_id, filename)
            )
            
            self.recordings[str(save_path)] = local_rec
            
            # Check if this should be permanent (falls within event window)
            self._check_if_permanent(local_rec)
            
            logger.debug(f"Downloaded: {filename}")

    def _parse_recording_time(self, filename: str, rec_info: dict) -> datetime:
        """Parse recording timestamp from filename or metadata"""
        # Try metadata first
        time_str = rec_info.get('time') or rec_info.get('timestamp') or rec_info.get('start')
        if time_str:
            try:
                # Handle various formats
                if isinstance(time_str, str):
                    # Remove timezone info for consistent comparison
                    time_str = time_str.replace('Z', '').replace('+00:00', '')
                    if 'T' in time_str:
                        return datetime.fromisoformat(time_str.split('.')[0])
                    else:
                        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logger.debug(f"Failed to parse time from metadata: {e}")
        
        # Try parsing from filename (common formats)
        # e.g., 2024-01-15T14-30-22.mp4 or 2024-01-15_14-30-22.mp4
        import re
        patterns = [
            (r'(\d{4}-\d{2}-\d{2})T(\d{2}-\d{2}-\d{2})', '%Y-%m-%d %H-%M-%S'),
            (r'(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', '%Y-%m-%d %H-%M-%S'),
            (r'(\d{4})(\d{2})(\d{2})[_T](\d{2})(\d{2})(\d{2})', None),
        ]
        
        for pattern, fmt in patterns:
            match = re.search(pattern, filename)
            if match:
                try:
                    groups = match.groups()
                    if fmt and len(groups) == 2:
                        date_str = groups[0]
                        time_str = groups[1]
                        return datetime.strptime(f"{date_str} {time_str}", fmt)
                    elif len(groups) == 6:
                        return datetime(int(groups[0]), int(groups[1]), int(groups[2]),
                                       int(groups[3]), int(groups[4]), int(groups[5]))
                except Exception as e:
                    logger.debug(f"Failed to parse time from filename: {e}")
        
        # Fallback to now
        logger.debug(f"Could not parse time from {filename}, using current time")
        return datetime.now()

    def _check_if_permanent(self, rec: LocalRecording):
        """Check if a newly downloaded recording should be permanent"""
        camera_id = rec.camera_id
        
        if camera_id not in self.pending_permanent:
            return
        
        event_time = make_naive(self.pending_permanent[camera_id])
        rec_time = make_naive(rec.recording_time)
        
        pre_start = event_time - timedelta(seconds=self.pre_event_seconds)
        post_end = event_time + timedelta(seconds=self.post_event_seconds)
        
        # Check if recording falls within event window
        if pre_start <= rec_time <= post_end:
            self._move_to_permanent(rec, event_time)
        
        # Clear pending event if we're past post-buffer
        now = datetime.now()
        if now > post_end:
            del self.pending_permanent[camera_id]

    async def _cleanup_loop(self):
        """Periodically delete old temp recordings"""
        while self.running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                self._cleanup_old_recordings()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    def _cleanup_old_recordings(self):
        """Delete temp recordings older than retention period"""
        now = datetime.now()
        deleted_count = 0
        
        to_delete = []
        
        for filepath, rec in self.recordings.items():
            # Skip permanent recordings
            if rec.is_permanent:
                continue
            
            # Check age
            downloaded_at = make_naive(rec.downloaded_at)
            age = now - downloaded_at
            if age > self.temp_retention:
                to_delete.append(filepath)
        
        for filepath in to_delete:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    deleted_count += 1
                del self.recordings[filepath]
            except Exception as e:
                logger.error(f"Failed to delete {filepath}: {e}")
        
        if deleted_count > 0:
            logger.info(f"🗑️ Cleaned up {deleted_count} old recordings")
        
        # Also clean empty directories
        self._cleanup_empty_dirs()

    def _cleanup_empty_dirs(self):
        """Remove empty directories in temp storage"""
        for camera_dir in self.temp_dir.iterdir():
            if camera_dir.is_dir():
                try:
                    if not any(camera_dir.iterdir()):
                        camera_dir.rmdir()
                except:
                    pass

    async def start(self):
        """Start the sync and cleanup tasks"""
        self.running = True
        
        # Load existing downloaded files to avoid re-downloading
        self._scan_existing_files()
        
        self._sync_task = asyncio.create_task(self._sync_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info(f"📁 Local Storage Manager started")
        logger.info(f"   Temp: {self.temp_dir} (auto-delete after {self.temp_retention})")
        logger.info(f"   Permanent: {self.permanent_dir}")

    def _scan_existing_files(self):
        """Scan existing files and load them into tracking system"""
        temp_count = 0
        perm_count = 0
        
        # Scan temp recordings
        for camera_dir in self.temp_dir.iterdir():
            if camera_dir.is_dir():
                camera_id = camera_dir.name
                for f in camera_dir.glob("*"):
                    if f.is_file() and f.suffix in ['.mp4', '.mkv', '.avi']:
                        file_key = f"{camera_id}_{f.name}"
                        self.downloaded_files.add(file_key)
                        
                        # Create LocalRecording object to track it
                        rec_time = self._parse_recording_time(f.name, {})
                        local_rec = LocalRecording(
                            filename=f.name,
                            camera_id=camera_id,
                            filepath=str(f),
                            downloaded_at=datetime.fromtimestamp(f.stat().st_mtime),
                            recording_time=rec_time,
                            is_permanent=False
                        )
                        self.recordings[str(f)] = local_rec
                        temp_count += 1
        
        # Scan permanent recordings
        for camera_dir in self.permanent_dir.iterdir():
            if camera_dir.is_dir():
                camera_id = camera_dir.name
                for event_dir in camera_dir.iterdir():
                    if event_dir.is_dir():
                        for f in event_dir.glob("*"):
                            if f.is_file() and f.suffix in ['.mp4', '.mkv', '.avi']:
                                file_key = f"{camera_id}_{f.name}"
                                self.downloaded_files.add(file_key)
                                
                                rec_time = self._parse_recording_time(f.name, {})
                                local_rec = LocalRecording(
                                    filename=f.name,
                                    camera_id=camera_id,
                                    filepath=str(f),
                                    downloaded_at=datetime.fromtimestamp(f.stat().st_mtime),
                                    recording_time=rec_time,
                                    is_permanent=True
                                )
                                self.recordings[str(f)] = local_rec
                                perm_count += 1
        
        if temp_count > 0 or perm_count > 0:
            logger.info(f"📂 Loaded {temp_count} temp + {perm_count} permanent existing recordings")

    async def stop(self):
        """Stop all tasks"""
        self.running = False
        
        if self._sync_task:
            self._sync_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        logger.info("Local Storage Manager stopped")

    def get_stats(self) -> dict:
        """Get storage statistics"""
        temp_count = sum(1 for r in self.recordings.values() if not r.is_permanent)
        perm_count = sum(1 for r in self.recordings.values() if r.is_permanent)
        
        temp_size = sum(
            os.path.getsize(r.filepath) 
            for r in self.recordings.values() 
            if not r.is_permanent and os.path.exists(r.filepath)
        )
        
        perm_size = sum(
            os.path.getsize(r.filepath)
            for r in self.recordings.values()
            if r.is_permanent and os.path.exists(r.filepath)
        )
        
        return {
            'temp_recordings': temp_count,
            'permanent_recordings': perm_count,
            'temp_size_mb': temp_size / 1024 / 1024,
            'permanent_size_mb': perm_size / 1024 / 1024,
            'pending_events': len(self.pending_permanent)
        }