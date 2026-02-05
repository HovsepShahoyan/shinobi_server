# save as: motion_yolo_detector.py
import cv2
import subprocess
import requests
import time
from ultralytics import YOLO
from datetime import datetime
import threading
import queue

# ============ CONFIGURATION ============
RTSP_INPUT = "rtsp://user:pass@192.168.1.100:554/stream"  # your camera
RTSP_OUTPUT = "rtsp://localhost:8554/cam1"  # Shinobi connects here
CAMERA_ID = "cam1"
WEBHOOK_URL = f"http://localhost:8000/event/{CAMERA_ID}/motion"

MOTION_THRESHOLD = 5000  # adjust for sensitivity
CONFIDENCE = 0.15
COOLDOWN_SECONDS = 3
DETECTION_INTERVAL = 5  # run YOLO every N frames when motion detected
# =======================================

# Load YOLO
model = YOLO("yolo26l.pt")
CLASS_MAP = {0: "person", 2: "car", 5: "bus", 7: "truck"}
DETECT_CLASSES = list(CLASS_MAP.keys())

# State
last_webhook = {}
prev_gray = None

def detect_motion(frame, prev_gray):
    """Returns True if motion detected"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)
    
    if prev_gray is None:
        return False, gray
    
    diff = cv2.absdiff(prev_gray, gray)
    thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
    score = thresh.sum() / 255
    
    return score > MOTION_THRESHOLD, gray

def send_webhook(obj_type, conf):
    global last_webhook
    now = time.time()
    
    if obj_type not in last_webhook or (now - last_webhook[obj_type]) > COOLDOWN_SECONDS:
        payload = {
            "object_type": obj_type,
            "confidence": int(conf * 100),
            "timestamp": datetime.now().isoformat(),
            "camera": CAMERA_ID
        }
        try:
            requests.post(WEBHOOK_URL, json=payload, timeout=1)
            print(f"[WEBHOOK] {obj_type} detected ({conf:.0%})")
            last_webhook[obj_type] = now
            return True
        except Exception as e:
            print(f"[WEBHOOK ERROR] {e}")
    return False

# Open input stream
cap = cv2.VideoCapture(RTSP_INPUT)
if not cap.isOpened():
    print(f"ERROR: Cannot open {RTSP_INPUT}")
    exit(1)

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25

print(f"Input: {width}x{height} @ {fps}fps")

# FFmpeg re-stream (always running)
ffmpeg_cmd = [
    'ffmpeg', '-y',
    '-f', 'rawvideo',
    '-pix_fmt', 'bgr24',
    '-s', f'{width}x{height}',
    '-r', str(fps),
    '-i', '-',
    '-c:v', 'libx264',
    '-preset', 'ultrafast',
    '-tune', 'zerolatency',
    '-b:v', '2M',
    '-f', 'rtsp',
    RTSP_OUTPUT
]

ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

print(f"")
print(f"=== Motion + YOLO Detector ===")
print(f"Input:   {RTSP_INPUT}")
print(f"Output:  {RTSP_OUTPUT}  <-- Shinobi connects here")
print(f"Webhook: {WEBHOOK_URL}")
print(f"")
print(f"Streaming... (Ctrl+C to stop)")

frame_count = 0
motion_frames = 0
detections_sent = 0

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Stream lost, reconnecting...")
            time.sleep(2)
            cap.release()
            cap = cv2.VideoCapture(RTSP_INPUT)
            continue
        
        frame_count += 1
        
        # Always re-stream the frame
        try:
            ffmpeg_proc.stdin.write(frame.tobytes())
        except BrokenPipeError:
            print("FFmpeg died, restarting...")
            ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            continue
        
        # Check motion every frame
        motion_detected, prev_gray = detect_motion(frame, prev_gray)
        
        if motion_detected:
            motion_frames += 1
            
            # Run YOLO only every N frames during motion (to save GPU)
            if motion_frames % DETECTION_INTERVAL == 0:
                results = model(frame, conf=CONFIDENCE, classes=DETECT_CLASSES, imgsz=1280, verbose=False)
                
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    obj_type = CLASS_MAP.get(cls_id)
                    
                    if obj_type:
                        if send_webhook(obj_type, conf):
                            detections_sent += 1
        else:
            motion_frames = 0
        
        # Print stats every 500 frames
        if frame_count % 500 == 0:
            print(f"[STATS] Frames: {frame_count}, Webhooks sent: {detections_sent}")

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    cap.release()
    ffmpeg_proc.stdin.close()
    ffmpeg_proc.wait()
    print(f"Done. Total frames: {frame_count}, Webhooks sent: {detections_sent}")