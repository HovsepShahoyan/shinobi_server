#!/bin/bash
#
# Camera System Startup Script
#
# This script starts all components in the correct order:
# 1. Dummy RTSP streams (if needed)
# 2. Webhook receiver
# 3. Main camera system
#
# Usage:
#   ./start_all.sh           # Start everything
#   ./start_all.sh --no-rtsp # Skip RTSP server (for real cameras)
#   ./start_all.sh --test    # Start and run tests
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
START_RTSP=true
RUN_TESTS=false
VENV_PATH="./venv312"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-rtsp)
            START_RTSP=false
            shift
            ;;
        --test)
            RUN_TESTS=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --no-rtsp   Skip starting dummy RTSP server"
            echo "  --test      Run tests after starting services"
            echo "  --help      Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           CAMERA RECORDING SYSTEM - STARTUP                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 not found${NC}"
    exit 1
fi

# Activate virtual environment if exists
if [ -d "$VENV_PATH" ]; then
    echo -e "${GREEN}🐍 Activating virtual environment...${NC}"
    source "$VENV_PATH/bin/activate"
fi

# Check required files
REQUIRED_FILES=("main.py" "webhook_receiver.py" "config.json")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}❌ Missing required file: $file${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✅ Required files found${NC}"

# Function to check if port is available
check_port() {
    if lsof -i:$1 &>/dev/null; then
        return 1
    fi
    return 0
}

# Function to wait for service
wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=0
    
    echo -n "   Waiting for $name..."
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" &>/dev/null; then
            echo -e " ${GREEN}OK${NC}"
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
        echo -n "."
    done
    echo -e " ${RED}TIMEOUT${NC}"
    return 1
}

# PID file for cleanup
PIDS=()
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down services...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    # Kill any remaining processes
    pkill -f "dummy_rtsp_server.py" 2>/dev/null || true
    pkill -f "webhook_receiver.py" 2>/dev/null || true
    pkill -f "main.py" 2>/dev/null || true
    pkill -f "mediamtx" 2>/dev/null || true
    echo -e "${GREEN}✅ Cleanup complete${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Step 1: Start RTSP server (if needed)
if [ "$START_RTSP" = true ]; then
    echo -e "\n${BLUE}📹 Step 1: Starting Dummy RTSP Server${NC}"
    echo "─────────────────────────────────────────"
    
    if ! check_port 8554; then
        echo -e "${YELLOW}⚠️  Port 8554 already in use, assuming RTSP server running${NC}"
    else
        python3 dummy_rtsp_server.py &
        PIDS+=($!)
        sleep 5
        
        if curl -s rtsp://localhost:8554/cam1 &>/dev/null || true; then
            echo -e "${GREEN}✅ RTSP server started${NC}"
        fi
    fi
else
    echo -e "\n${YELLOW}📹 Step 1: Skipping RTSP server (--no-rtsp)${NC}"
fi

# Step 2: Start webhook receiver
echo -e "\n${BLUE}📥 Step 2: Starting Webhook Receiver${NC}"
echo "─────────────────────────────────────────"

if ! check_port 8766; then
    echo -e "${YELLOW}⚠️  Port 8766 already in use, skipping${NC}"
else
    python3 webhook_receiver.py &
    PIDS+=($!)
    wait_for_service "http://localhost:8766/health" "Webhook Receiver"
fi

# Step 3: Start main system
echo -e "\n${BLUE}🎯 Step 3: Starting Main Camera System${NC}"
echo "─────────────────────────────────────────"

if ! check_port 8765; then
    echo -e "${YELLOW}⚠️  Port 8765 already in use, skipping${NC}"
else
    python3 main.py &
    PIDS+=($!)
    wait_for_service "http://localhost:8765/health" "Main System"
fi

# Step 4: Run tests (if requested)
if [ "$RUN_TESTS" = true ]; then
    echo -e "\n${BLUE}🧪 Step 4: Running Tests${NC}"
    echo "─────────────────────────────────────────"
    sleep 2
    python3 simplified_test.py
fi

# Print status
echo -e "\n${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    ALL SERVICES RUNNING                        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Services:${NC}"
echo "  📹 RTSP Streams:    rtsp://localhost:8554/cam1, /cam2"
echo "  🎯 Webhook Server:  http://localhost:8765"
echo "  📥 Event Receiver:  http://localhost:8766"
echo ""
echo -e "${BLUE}Endpoints:${NC}"
echo "  Health checks:"
echo "    curl http://localhost:8765/health"
echo "    curl http://localhost:8766/health"
echo ""
echo "  Test event:"
echo "    curl -X POST http://localhost:8765/test/cam1/motion"
echo ""
echo "  View events:"
echo "    curl http://localhost:8766/events"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for all processes
wait