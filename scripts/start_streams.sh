#!/bin/bash
#
# Start FFmpeg test streams
# Run this AFTER MediaMTX is already running
#

echo "============================================================"
echo "📹 Starting FFmpeg Test Streams"
echo "============================================================"
echo ""
echo "⚠️  Make sure MediaMTX is running first!"
echo "   You should see: [RTSP] listener opened on :8554"
echo ""

# Check if MediaMTX is running
if ! nc -z localhost 8554 2>/dev/null; then
    echo "❌ Port 8554 not open. Start MediaMTX first:"
    echo "   ./mediamtx"
    exit 1
fi

echo "✅ Port 8554 is open (MediaMTX running)"
echo ""

# Function to start a stream
start_stream() {
    local name=$1
    local color=$2
    local text=$3
    
    echo "📹 Starting $name ($color background)..."
    
    ffmpeg -re -f lavfi -i "color=c=$color:s=1280x720:r=15" \
        -vf "drawtext=text='$text':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2,drawtext=text='%{localtime\:%Y-%m-%d %H\:%M\:%S}':fontsize=36:fontcolor=white:x=10:y=10" \
        -c:v libx264 -preset ultrafast -tune zerolatency -b:v 1500k -an \
        -f rtsp -rtsp_transport tcp "rtsp://localhost:8554/$name" \
        2>/dev/null &
    
    echo "   PID: $!"
}

# Start both streams
start_stream "cam1" "blue" "CAMERA 1"
sleep 2
start_stream "cam2" "green" "CAMERA 2"
sleep 2

echo ""
echo "============================================================"
echo "✅ Streams Started!"
echo "============================================================"
echo ""
echo "📺 RTSP URLs:"
echo "   cam1: rtsp://localhost:8554/cam1"
echo "   cam2: rtsp://localhost:8554/cam2"
echo ""
echo "📺 Test with VLC:"
echo "   vlc rtsp://localhost:8554/cam1"
echo ""
echo "📺 Test with FFprobe:"
echo "   ffprobe -rtsp_transport tcp rtsp://localhost:8554/cam1"
echo ""
echo "🔧 Verify in Shinobi:"
echo "   1. Open http://localhost:8080"
echo "   2. Check if cam1 and cam2 show video"
echo "   3. Start recording if not already"
echo ""
echo "Press Ctrl+C to stop streams"
echo ""

# Wait for Ctrl+C
wait