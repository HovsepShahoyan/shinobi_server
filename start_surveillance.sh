#!/bin/bash

# YOLO Surveillance System - Startup Script
# Usage: ./start_surveillance.sh [start|stop|status]

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Paths
SHINOBI_SERVER_DIR="$HOME/shinobi_server"
YOLO_DETECTOR_DIR="$HOME/yolo_detector"
SHINOBI_NVR_DIR="/home/Shinobi"
VIDEO_FILE="$HOME/recording_20260117_145540.mp4.mkv"

# Log directory
LOG_DIR="$SHINOBI_SERVER_DIR/logs"
mkdir -p "$LOG_DIR"

# PID file
PID_FILE="$SHINOBI_SERVER_DIR/.surveillance_pids"

start_services() {
    echo -e "${GREEN}Starting YOLO Surveillance System...${NC}"
    echo ""
    
    # Clear old PIDs
    > "$PID_FILE"
    
    # 1. Start MediaMTX
    echo -e "${YELLOW}[1/6] Starting MediaMTX...${NC}"
    cd "$SHINOBI_SERVER_DIR"
    ./mediamtx > "$LOG_DIR/mediamtx.log" 2>&1 &
    echo $! >> "$PID_FILE"
    sleep 2
    
    if curl -s http://localhost:9997/v3/paths/list > /dev/null 2>&1; then
        echo -e "${GREEN}      ✓ MediaMTX started on port 8554${NC}"
    else
        echo -e "${RED}      ✗ MediaMTX failed to start${NC}"
        return 1
    fi
    
    # 2. Start Shinobi NVR
    echo -e "${YELLOW}[2/6] Starting Shinobi NVR...${NC}"
    cd "$SHINOBI_NVR_DIR"
    sudo node camera.js > "$LOG_DIR/shinobi.log" 2>&1 &
    echo $! >> "$PID_FILE"
    sleep 5
    
    if curl -s http://localhost:8080 > /dev/null 2>&1; then
        echo -e "${GREEN}      ✓ Shinobi started on port 8080${NC}"
    else
        echo -e "${YELLOW}      ? Shinobi may need more time to start${NC}"
    fi
    
    # 3. Start Video Input (fake camera)
    echo -e "${YELLOW}[3/6] Starting Video Input...${NC}"
    if [ -f "$VIDEO_FILE" ]; then
        ffmpeg -re -stream_loop -1 -i "$VIDEO_FILE" \
            -c copy -f rtsp -rtsp_transport tcp \
            rtsp://localhost:8554/input > "$LOG_DIR/ffmpeg_input.log" 2>&1 &
        echo $! >> "$PID_FILE"
        sleep 2
        echo -e "${GREEN}      ✓ Video input streaming to /input${NC}"
    else
        echo -e "${YELLOW}      ! Video file not found: $VIDEO_FILE${NC}"
        echo -e "${YELLOW}        You can manually start a video source later${NC}"
    fi
    
    # 4. Start YOLO Detector
    echo -e "${YELLOW}[4/6] Starting YOLO Detector...${NC}"
    cd "$YOLO_DETECTOR_DIR"
    source venv/bin/activate
    python motion_yolo_detector.py > "$LOG_DIR/yolo_detector.log" 2>&1 &
    echo $! >> "$PID_FILE"
    sleep 5
    
    # Check if detected stream exists
    if curl -s http://localhost:9997/v3/paths/list | grep -q "detected"; then
        echo -e "${GREEN}      ✓ YOLO Detector streaming to /detected${NC}"
    else
        echo -e "${YELLOW}      ? YOLO Detector may need more time to start${NC}"
    fi
    
    # 5. Start Webhook Server
    echo -e "${YELLOW}[5/6] Starting Webhook Server...${NC}"
    cd "$SHINOBI_SERVER_DIR"
    source venv312/bin/activate
    python main.py > "$LOG_DIR/webhook_server.log" 2>&1 &
    echo $! >> "$PID_FILE"
    sleep 2
    
    if curl -s http://localhost:8765/health > /dev/null 2>&1; then
        echo -e "${GREEN}      ✓ Webhook server started on port 8765${NC}"
    else
        echo -e "${YELLOW}      ? Webhook server may need more time${NC}"
    fi
    
    # 6. Start Electron App
    echo -e "${YELLOW}[6/6] Starting Electron App...${NC}"
    cd "$SHINOBI_SERVER_DIR/electron-app"
    if [ -d "node_modules" ]; then
        npm start > "$LOG_DIR/electron.log" 2>&1 &
        echo $! >> "$PID_FILE"
        echo -e "${GREEN}      ✓ Electron app starting...${NC}"
    else
        echo -e "${YELLOW}      ! Electron app not installed. Run: cd electron-app && npm install${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Surveillance System Started!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "URLs:"
    echo "  Shinobi:      http://localhost:8080"
    echo "  Webhook API:  http://localhost:8765"
    echo "  RTSP Input:   rtsp://localhost:8554/input"
    echo "  RTSP Output:  rtsp://localhost:8554/detected"
    echo ""
    echo "Logs directory: $LOG_DIR"
    echo ""
    echo "To stop: ./start_surveillance.sh stop"
}

stop_services() {
    echo -e "${YELLOW}Stopping YOLO Surveillance System...${NC}"
    
    # Kill processes from PID file
    if [ -f "$PID_FILE" ]; then
        while read pid; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null
                echo "  Stopped PID $pid"
            fi
        done < "$PID_FILE"
        rm "$PID_FILE"
    fi
    
    # Also kill by name (in case PIDs were lost)
    pkill -f "mediamtx" 2>/dev/null
    pkill -f "motion_yolo_detector" 2>/dev/null
    pkill -f "main.py" 2>/dev/null
    sudo pkill -f "camera.js" 2>/dev/null
    pkill -f "ffmpeg.*8554/input" 2>/dev/null
    pkill -f "electron" 2>/dev/null
    
    echo -e "${GREEN}All services stopped.${NC}"
}

show_status() {
    echo -e "${GREEN}YOLO Surveillance System Status${NC}"
    echo "================================"
    
    # MediaMTX
    if curl -s http://localhost:9997/v3/paths/list > /dev/null 2>&1; then
        echo -e "MediaMTX:       ${GREEN}Running${NC}"
        
        # Check streams
        streams=$(curl -s http://localhost:9997/v3/paths/list)
        if echo "$streams" | grep -q "input"; then
            echo -e "  /input:       ${GREEN}Active${NC}"
        else
            echo -e "  /input:       ${RED}Not active${NC}"
        fi
        if echo "$streams" | grep -q "detected"; then
            echo -e "  /detected:    ${GREEN}Active${NC}"
        else
            echo -e "  /detected:    ${RED}Not active${NC}"
        fi
    else
        echo -e "MediaMTX:       ${RED}Not running${NC}"
    fi
    
    # Shinobi
    if curl -s http://localhost:8080 > /dev/null 2>&1; then
        echo -e "Shinobi NVR:    ${GREEN}Running${NC}"
    else
        echo -e "Shinobi NVR:    ${RED}Not running${NC}"
    fi
    
    # Webhook Server
    if curl -s http://localhost:8765/health > /dev/null 2>&1; then
        echo -e "Webhook Server: ${GREEN}Running${NC}"
    else
        echo -e "Webhook Server: ${RED}Not running${NC}"
    fi
    
    # YOLO Detector
    if pgrep -f "motion_yolo_detector" > /dev/null; then
        echo -e "YOLO Detector:  ${GREEN}Running${NC}"
    else
        echo -e "YOLO Detector:  ${RED}Not running${NC}"
    fi
    
    # Electron
    if pgrep -f "electron" > /dev/null; then
        echo -e "Electron App:   ${GREEN}Running${NC}"
    else
        echo -e "Electron App:   ${RED}Not running${NC}"
    fi
}

show_logs() {
    echo "Available logs in $LOG_DIR:"
    ls -la "$LOG_DIR"/*.log 2>/dev/null || echo "  No logs found"
    echo ""
    echo "To view a log: tail -f $LOG_DIR/<logfile>.log"
}

# Main
case "${1:-start}" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        sleep 2
        start_services
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
