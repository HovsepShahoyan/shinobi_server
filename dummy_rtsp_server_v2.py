#!/usr/bin/env python3
"""
Dummy RTSP Stream Server v2

Creates test video streams for development/testing.
Multiple fallback methods:
1. MediaMTX (rtsp-simple-server) - preferred
2. GStreamer RTSP server
3. FFmpeg direct RTSP

Requirements:
- FFmpeg installed (sudo apt install ffmpeg)
"""

import subprocess
import signal
import sys
import time
import os
import threading
import shutil
from pathlib import Path

class DummyRTSPServer:
    """Creates dummy RTSP streams for testing"""
    
    def __init__(self, rtsp_port: int = 8554):
        self.rtsp_port = rtsp_port
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
    
    def check_port_available(self, port: int) -> bool:
        """Check if port is available"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('0.0.0.0', port))
            sock.close()
            return True
        except OSError:
            return False
    
    def kill_existing_mediamtx(self):
        """Kill any existing mediamtx processes"""
        try:
            subprocess.run(['pkill', '-9', 'mediamtx'], capture_output=True)
            time.sleep(1)
        except:
            pass
    
    def download_mediamtx(self) -> bool:
        """Download MediaMTX if not present"""
        mediamtx_path = Path("./mediamtx")
        
        if mediamtx_path.exists():
            print("✅ MediaMTX binary exists")
            # Make sure it's executable
            os.chmod('mediamtx', 0o755)
            return True
        
        print("📥 Downloading MediaMTX...")
        
        # Use correct architecture
        arch_name = "amd64"  # x86_64
        version = "v1.9.3"
        
        url = f"https://github.com/bluenviron/mediamtx/releases/download/{version}/mediamtx_{version}_linux_{arch_name}.tar.gz"
        
        try:
            # Download
            print(f"   URL: {url}")
            result = subprocess.run([
                'wget', '-q', '--show-progress', url, '-O', 'mediamtx.tar.gz'
            ], timeout=120)
            
            if result.returncode != 0:
                # Try with curl
                result = subprocess.run([
                    'curl', '-L', '-o', 'mediamtx.tar.gz', url
                ], timeout=120)
            
            if not os.path.exists('mediamtx.tar.gz'):
                print("❌ Download failed")
                return False
            
            # Extract
            subprocess.run([
                'tar', '-xzf', 'mediamtx.tar.gz'
            ], check=True)
            
            os.chmod('mediamtx', 0o755)
            
            # Cleanup
            if os.path.exists('mediamtx.tar.gz'):
                os.remove('mediamtx.tar.gz')
            if os.path.exists('mediamtx.yml'):
                os.remove('mediamtx.yml')  # Remove default config
            
            print("✅ MediaMTX downloaded successfully")
            return True
            
        except Exception as e:
            print(f"❌ Failed to download MediaMTX: {e}")
            return False
    
    def create_mediamtx_config(self) -> str:
        """Create MediaMTX configuration file"""
        config_content = f"""
# MediaMTX configuration
logLevel: info
logDestinations: [stdout]

# RTSP server
rtsp: yes
rtspAddress: :{self.rtsp_port}
protocols: [tcp, udp]

# Disable other protocols we don't need
rtmp: no
hls: no
webrtc: no
srt: no

# Allow publishing from localhost
paths:
  all_others:
    source: publisher
    sourceOnDemand: no
    record: no
"""
        
        config_path = "mediamtx_config.yml"
        with open(config_path, 'w') as f:
            f.write(config_content)
        
        return config_path
    
    def start_mediamtx(self) -> bool:
        """Start MediaMTX RTSP server"""
        
        # Kill any existing instance
        self.kill_existing_mediamtx()
        
        # Check port
        if not self.check_port_available(self.rtsp_port):
            print(f"⚠️ Port {self.rtsp_port} is in use")
            # Try to find what's using it
            try:
                result = subprocess.run(['lsof', '-i', f':{self.rtsp_port}'], 
                                       capture_output=True, text=True)
                if result.stdout:
                    print(f"   Process using port: {result.stdout.split()[0] if result.stdout else 'unknown'}")
            except:
                pass
            return False
        
        # Download if needed
        if not self.download_mediamtx():
            return False
        
        # Create config
        config_path = self.create_mediamtx_config()
        
        print(f"🚀 Starting MediaMTX RTSP server on port {self.rtsp_port}...")
        
        # Start MediaMTX
        try:
            self.mediamtx_process = subprocess.Popen(
                ['./mediamtx', config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            # Wait and check output
            time.sleep(3)
            
            if self.mediamtx_process.poll() is not None:
                # Process died, get output
                output, _ = self.mediamtx_process.communicate(timeout=1)
                print(f"❌ MediaMTX failed to start:")
                print(f"   {output[:500] if output else 'No output'}")
                return False
            
            # Verify it's listening
            if not self.check_port_available(self.rtsp_port):
                print(f"✅ MediaMTX running on rtsp://localhost:{self.rtsp_port}")
                return True
            else:
                print(f"❌ MediaMTX started but not listening on port {self.rtsp_port}")
                return False
                
        except Exception as e:
            print(f"❌ Error starting MediaMTX: {e}")
            return False
    
    def start_ffmpeg_stream(self, stream_name: str, color: str = "blue", 
                            text: str = None) -> bool:
        """
        Start an FFmpeg test pattern stream
        """
        if text is None:
            text = stream_name.upper()
        
        rtsp_url = f"rtsp://localhost:{self.rtsp_port}/{stream_name}"
        
        # FFmpeg command to generate test pattern with timestamp
        # Using simpler settings for compatibility
        cmd = [
            'ffmpeg',
            '-re',  # Read input at native frame rate
            '-f', 'lavfi',
            '-i', f"color=c={color}:s=1280x720:r=15",  # Color background
            '-vf', (
                f"drawtext=text='{text}':fontsize=72:fontcolor=white:"
                f"x=(w-text_w)/2:y=(h-text_h)/2,"
                f"drawtext=text='%{{localtime\\:%Y-%m-%d %H\\\\:%M\\\\:%S}}':"
                f"fontsize=36:fontcolor=white:x=10:y=10"
            ),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-g', '15',  # GOP size = fps for low latency
            '-b:v', '1500k',
            '-an',  # No audio (simpler)
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',
            rtsp_url
        ]
        
        print(f"📹 Starting stream: {rtsp_url}")
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.processes.append({
                'name': stream_name,
                'process': process,
                'url': rtsp_url,
                'color': color
            })
            
            # Give it a moment to connect
            time.sleep(2)
            
            if process.poll() is None:
                print(f"✅ Stream {stream_name} active: {rtsp_url}")
                return True
            else:
                stderr = process.stderr.read().decode() if process.stderr else ""
                print(f"❌ Stream {stream_name} failed")
                if stderr:
                    # Show last few lines of error
                    lines = stderr.strip().split('\n')[-3:]
                    for line in lines:
                        print(f"   {line}")
                return False
                
        except Exception as e:
            print(f"❌ Error starting stream {stream_name}: {e}")
            return False
    
    def start_default_streams(self) -> int:
        """Start the default cam1 and cam2 streams"""
        streams = [
            {'name': 'cam1', 'color': 'blue', 'text': 'CAMERA 1'},
            {'name': 'cam2', 'color': 'green', 'text': 'CAMERA 2'},
        ]
        
        success = 0
        for stream in streams:
            if self.start_ffmpeg_stream(
                stream_name=stream['name'],
                color=stream['color'],
                text=stream['text']
            ):
                success += 1
            time.sleep(1)
        
        return success
    
    def monitor_streams(self):
        """Monitor and restart failed streams"""
        while self.running:
            time.sleep(5)
            
            for stream in self.processes[:]:  # Copy list to allow modification
                if stream['process'].poll() is not None:
                    print(f"⚠️ Stream {stream['name']} stopped, restarting...")
                    self.processes.remove(stream)
                    time.sleep(1)
                    self.start_ffmpeg_stream(
                        stream['name'], 
                        stream['color'],
                        stream['name'].upper()
                    )
    
    def stop_all(self):
        """Stop all streams and MediaMTX"""
        print("\n🛑 Stopping all streams...")
        self.running = False
        
        for stream in self.processes:
            if stream['process'].poll() is None:
                stream['process'].terminate()
                try:
                    stream['process'].wait(timeout=5)
                except:
                    stream['process'].kill()
                print(f"   Stopped {stream['name']}")
        
        if self.mediamtx_process and self.mediamtx_process.poll() is None:
            self.mediamtx_process.terminate()
            try:
                self.mediamtx_process.wait(timeout=5)
            except:
                self.mediamtx_process.kill()
            print("   Stopped MediaMTX")
        
        # Cleanup config
        if os.path.exists('mediamtx_config.yml'):
            os.remove('mediamtx_config.yml')
        
        self.processes = []
    
    def run(self):
        """Main run loop"""
        self.running = True
        
        print("=" * 60)
        print("📹 DUMMY RTSP STREAM SERVER v2")
        print("=" * 60)
        
        # Check FFmpeg
        if not self.check_ffmpeg():
            print("❌ FFmpeg not installed!")
            print("   Install with: sudo apt install ffmpeg")
            return False
        
        print("✅ FFmpeg installed")
        
        # Start MediaMTX
        if not self.start_mediamtx():
            print("\n❌ Failed to start RTSP server")
            print("\n🔧 Troubleshooting:")
            print("   1. Check if another process is using port 8554:")
            print("      sudo lsof -i :8554")
            print("   2. Kill it if needed:")
            print("      sudo kill -9 <PID>")
            print("   3. Try running MediaMTX manually:")
            print("      ./mediamtx")
            return False
        
        # Start streams
        print("\n📹 Starting test streams...")
        success = self.start_default_streams()
        
        if success == 0:
            print("\n❌ No streams started successfully")
            self.stop_all()
            return False
        
        # Print info
        print("\n" + "=" * 60)
        print("🎬 RTSP STREAMS AVAILABLE:")
        print("=" * 60)
        for stream in self.processes:
            print(f"   {stream['name']}: {stream['url']}")
        print()
        print("📺 Test with VLC:")
        print(f"   vlc rtsp://localhost:{self.rtsp_port}/cam1")
        print(f"   vlc rtsp://localhost:{self.rtsp_port}/cam2")
        print()
        print("📺 Test with FFprobe:")
        print(f"   ffprobe rtsp://localhost:{self.rtsp_port}/cam1")
        print()
        print("🔧 Add to Shinobi with these RTSP URLs")
        print("=" * 60)
        print("Press Ctrl+C to stop\n")
        
        # Monitor streams in background
        monitor_thread = threading.Thread(target=self.monitor_streams, daemon=True)
        monitor_thread.start()
        
        # Wait
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_all()
        
        return True


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Dummy RTSP Stream Server')
    parser.add_argument('-p', '--port', type=int, default=8554, help='RTSP port')
    parser.add_argument('--kill', action='store_true', help='Kill existing MediaMTX')
    
    args = parser.parse_args()
    
    server = DummyRTSPServer(rtsp_port=args.port)
    
    if args.kill:
        server.kill_existing_mediamtx()
        print("Killed existing MediaMTX processes")
        return
    
    # Handle Ctrl+C
    def signal_handler(sig, frame):
        server.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    server.run()


if __name__ == "__main__":
    main()