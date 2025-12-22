#!/usr/bin/env python3
"""
Dummy RTSP Stream Generator

Creates looped RTSP streams from test videos for camera testing.
This simulates real camera feeds for testing the complete recording pipeline.
"""

import subprocess
import time
import os
import signal
import sys
from pathlib import Path

class RTSPStream:
    def __init__(self, video_path: str, rtsp_port: int, stream_name: str = "stream"):
        self.video_path = video_path
        self.rtsp_port = rtsp_port
        self.stream_name = stream_name
        self.process = None
        
    def start(self):
        """Start RTSP stream using FFmpeg"""
        if not os.path.exists(self.video_path):
            print(f"❌ Video file not found: {self.video_path}")
            return False
            
        # FFmpeg command to create RTSP stream
        cmd = [
            "ffmpeg", "-re",
            "-stream_loop", "-1",  # Loop forever
            "-i", self.video_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-c:a", "aac",
            "-f", "rtsp",
            f"rtsp://localhost:{self.rtsp_port}/{self.stream_name}"
        ]
        
        print(f"🎬 Starting RTSP stream: rtsp://localhost:{self.rtsp_port}/{self.stream_name}")
        print(f"   Video: {self.video_path}")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            time.sleep(2)  # Give FFmpeg time to start
            
            if self.process.poll() is None:
                print(f"✅ RTSP stream started successfully")
                return True
            else:
                print(f"❌ Failed to start RTSP stream")
                return False
                
        except Exception as e:
            print(f"❌ Error starting RTSP stream: {e}")
            return False
    
    def stop(self):
        """Stop RTSP stream"""
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=5)
                print(f"🛑 RTSP stream stopped")
            except Exception as e:
                print(f"⚠️ Error stopping stream: {e}")
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except:
                    pass

def main():
    """Start both dummy streams"""
    # Paths
    base_dir = Path(__file__).parent
    test_videos_dir = base_dir.parent / "test_videos"
    
    # Stream configurations
    streams = [
        {
            "video": test_videos_dir / "cam1_base.mp4",
            "port": 8554,
            "name": "cam1",
            "description": "Camera 1 - Test Pattern"
        },
        {
            "video": test_videos_dir / "cam2_base.mp4", 
            "port": 8555,
            "name": "cam2",
            "description": "Camera 2 - Blue Screen"
        }
    ]
    
    print("=" * 60)
    print("🎥 DUMMY RTSP STREAM GENERATOR")
    print("=" * 60)
    
    # Create and start streams
    rtsp_streams = []
    
    for stream_config in streams:
        stream = RTSPStream(
            video_path=str(stream_config["video"]),
            rtsp_port=stream_config["port"],
            stream_name=stream_config["name"]
        )
        
        if stream.start():
            rtsp_streams.append(stream)
            print(f"📹 {stream_config['description']}")
            print(f"   URL: rtsp://localhost:{stream_config['port']}/{stream_config['name']}")
            print()
    
    if not rtsp_streams:
        print("❌ No streams started successfully")
        sys.exit(1)
    
    print("=" * 60)
    print("🎯 TESTING URLs:")
    print("=" * 60)
    for stream_config in streams:
        print(f"Camera {stream_config['name']}: rtsp://localhost:{stream_config['port']}/{stream_config['name']}")
    print()
    print("💡 Use these URLs in your config.json")
    print("🛑 Press Ctrl+C to stop all streams")
    print("=" * 60)
    
    try:
        # Keep streams running
        while True:
            time.sleep(1)
            
            # Check if any stream died
            for stream in rtsp_streams:
                if stream.process.poll() is not None:
                    print(f"⚠️ Stream died, restarting...")
                    stream.start()
                    
    except KeyboardInterrupt:
        print("\n🛑 Stopping all streams...")
        for stream in rtsp_streams:
            stream.stop()
        print("✅ All streams stopped")

if __name__ == "__main__":
    main()
