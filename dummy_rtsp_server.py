#!/usr/bin/env python3
"""
Dummy RTSP Stream Server

Creates test video streams for development/testing.
Uses FFmpeg to generate test patterns and streams them via RTSP.

Requirements:
- FFmpeg installed
- MediaMTX (rtsp-simple-server) installed OR use FFmpeg's built-in RTSP output

Two modes:
1. MediaMTX mode (recommended): Streams to MediaMTX RTSP server
2. Direct FFmpeg mode: Uses FFmpeg's built-in RTSP server (less reliable)
"""

import subprocess
import signal
import sys
import time
import os
import threading
from pathlib import Path

class DummyRTSPServer:
    """Creates dummy RTSP streams for testing"""
    
    def __init__(self):
        self.processes = []
        self.mediamtx_process = None
        self.running = False
        
    def check_ffmpeg(self) -> bool:
        """Check if FFmpeg is installed"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                    capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False
    
    def download_mediamtx(self):
        """Download MediaMTX if not present"""
        mediamtx_path = Path("./mediamtx")
        
        if mediamtx_path.exists():
            print("✅ MediaMTX already exists")
            return True
        
        print("📥 Downloading MediaMTX...")
        
        # Detect architecture
        import platform
        arch = platform.machine()
        
        if arch in ['x86_64', 'AMD64']:
            arch_name = "amd64"
        elif arch in ['aarch64', 'arm64']:
            arch_name = "arm64v8"
        else:
            arch_name = "amd64"  # Default
        
        url = f"https://github.com/bluenviron/mediamtx/releases/download/v1.9.3/mediamtx_v1.9.3_linux_{arch_name}.tar.gz"
        
        try:
            subprocess.run([
                'wget', '-q', url, '-O', 'mediamtx.tar.gz'
            ], check=True, timeout=60)
            
            subprocess.run([
                'tar', '-xzf', 'mediamtx.tar.gz', 'mediamtx'
            ], check=True)
            
            os.chmod('mediamtx', 0o755)
            os.remove('mediamtx.tar.gz')
            
            print("✅ MediaMTX downloaded successfully")
            return True
            
        except Exception as e:
            print(f"❌ Failed to download MediaMTX: {e}")
            return False
    
    def start_mediamtx(self, rtsp_port: int = 8554):
        """Start MediaMTX RTSP server"""
        mediamtx_path = Path("./mediamtx")
        
        if not mediamtx_path.exists():
            if not self.download_mediamtx():
                return False
        
        # Create minimal config
        config_content = f"""
rtspAddress: :{rtsp_port}
rtpAddress: :{rtsp_port + 1}
rtcpAddress: :{rtsp_port + 2}
hlsAddress: :{rtsp_port + 1000}
webrtcAddress: :{rtsp_port + 2000}
logLevel: warn

paths:
  all:
    source: publisher
"""
        
        with open('mediamtx.yml', 'w') as f:
            f.write(config_content)
        
        print(f"🚀 Starting MediaMTX RTSP server on port {rtsp_port}...")
        
        self.mediamtx_process = subprocess.Popen(
            ['./mediamtx', 'mediamtx.yml'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        time.sleep(2)
        
        if self.mediamtx_process.poll() is None:
            print(f"✅ MediaMTX running on rtsp://localhost:{rtsp_port}")
            return True
        else:
            print("❌ MediaMTX failed to start")
            return False
    
    def start_ffmpeg_stream(self, stream_name: str, rtsp_port: int = 8554, 
                            color: str = "blue", text: str = None):
        """
        Start an FFmpeg test pattern stream
        
        Args:
            stream_name: Name of the stream (e.g., 'cam1')
            rtsp_port: RTSP port to stream to
            color: Background color (red, green, blue, yellow, etc.)
            text: Text to overlay on video
        """
        if text is None:
            text = stream_name.upper()
        
        rtsp_url = f"rtsp://localhost:{rtsp_port}/{stream_name}"
        
        # FFmpeg command to generate test pattern with timestamp
        cmd = [
            'ffmpeg',
            '-re',  # Read input at native frame rate
            '-f', 'lavfi',
            '-i', f"color=c={color}:s=1280x720:r=15",  # Color background
            '-f', 'lavfi',
            '-i', f"sine=frequency=1000:sample_rate=44100",  # Beep audio
            '-vf', (
                f"drawtext=text='{text}':fontsize=72:fontcolor=white:"
                f"x=(w-text_w)/2:y=(h-text_h)/2,"
                f"drawtext=text='%{{localtime\\:%Y-%m-%d %H\\\\:%M\\\\:%S}}':"
                f"fontsize=36:fontcolor=white:x=10:y=10,"
                f"drawtext=text='Frame\\: %{{frame_num}}':fontsize=24:"
                f"fontcolor=yellow:x=10:y=h-40"
            ),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-b:v', '1M',
            '-c:a', 'aac',
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',
            rtsp_url
        ]
        
        print(f"📹 Starting stream: {rtsp_url}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        self.processes.append({
            'name': stream_name,
            'process': process,
            'url': rtsp_url
        })
        
        time.sleep(1)
        
        if process.poll() is None:
            print(f"✅ Stream {stream_name} active: {rtsp_url}")
            return True
        else:
            stderr = process.stderr.read().decode() if process.stderr else ""
            print(f"❌ Stream {stream_name} failed: {stderr[:200]}")
            return False
    
    def start_default_streams(self):
        """Start the default cam1 and cam2 streams"""
        streams = [
            {'name': 'cam1', 'color': 'blue', 'text': 'CAMERA 1'},
            {'name': 'cam2', 'color': 'green', 'text': 'CAMERA 2'},
        ]
        
        for stream in streams:
            self.start_ffmpeg_stream(
                stream_name=stream['name'],
                color=stream['color'],
                text=stream['text']
            )
            time.sleep(2)
    
    def stop_all(self):
        """Stop all streams and MediaMTX"""
        print("\n🛑 Stopping all streams...")
        
        for stream in self.processes:
            if stream['process'].poll() is None:
                stream['process'].terminate()
                stream['process'].wait(timeout=5)
                print(f"   Stopped {stream['name']}")
        
        if self.mediamtx_process and self.mediamtx_process.poll() is None:
            self.mediamtx_process.terminate()
            self.mediamtx_process.wait(timeout=5)
            print("   Stopped MediaMTX")
        
        self.processes = []
        self.running = False
    
    def run(self):
        """Main run loop"""
        self.running = True
        
        print("=" * 60)
        print("📹 DUMMY RTSP STREAM SERVER")
        print("=" * 60)
        
        # Check FFmpeg
        if not self.check_ffmpeg():
            print("❌ FFmpeg not installed!")
            print("   Install with: sudo apt install ffmpeg")
            return
        
        print("✅ FFmpeg installed")
        
        # Start MediaMTX
        if not self.start_mediamtx():
            print("❌ Failed to start RTSP server")
            return
        
        # Start streams
        print("\n📹 Starting test streams...")
        self.start_default_streams()
        
        # Print info
        print("\n" + "=" * 60)
        print("🎬 RTSP STREAMS AVAILABLE:")
        print("=" * 60)
        for stream in self.processes:
            print(f"   {stream['name']}: {stream['url']}")
        print()
        print("📺 Test with VLC:")
        print("   vlc rtsp://localhost:8554/cam1")
        print("   vlc rtsp://localhost:8554/cam2")
        print()
        print("🔧 Add to Shinobi with these URLs")
        print("=" * 60)
        print("Press Ctrl+C to stop\n")
        
        # Wait
        try:
            while self.running:
                time.sleep(1)
                # Check if streams are still running
                for stream in self.processes:
                    if stream['process'].poll() is not None:
                        print(f"⚠️ Stream {stream['name']} stopped, restarting...")
                        self.processes.remove(stream)
                        time.sleep(2)
                        if stream['name'] == 'cam1':
                            self.start_ffmpeg_stream('cam1', color='blue', text='CAMERA 1')
                        elif stream['name'] == 'cam2':
                            self.start_ffmpeg_stream('cam2', color='green', text='CAMERA 2')
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_all()


def main():
    server = DummyRTSPServer()
    
    # Handle Ctrl+C
    def signal_handler(sig, frame):
        server.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    server.run()


if __name__ == "__main__":
    main()