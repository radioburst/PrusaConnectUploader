import subprocess
import requests
from requests.auth import HTTPDigestAuth
import glob
import time
import json
import os
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

# Load configuration from JSON file
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

# Extract configuration values
PRINTERS = config['printers']
INTERVAL_SECONDS = config['interval_seconds']

# --- CONFIGURATION ---
SNAPSHOT_URL = "https://connect.prusa3d.com/c/snapshot"
INFO_URL = "https://connect.prusa3d.com/c/info"

# Global state for each printer's manual override (keyed by printer name)
manual_overrides = {}

# Initialize GPIO for each printer with LED control enabled
def init_gpio_for_printer(printer):
    if not printer.get('led_control_enabled', False):
        return
    
    led_pin = printer.get('led_pin')
    button_pin = printer.get('button_pin')
    
    if led_pin is None or button_pin is None:
        return
    
    printer_name = printer['name']
    manual_overrides[printer_name] = False
    
    try:
        # Clean up pins first if they were previously used
        try:
            GPIO.cleanup(led_pin)
            GPIO.cleanup(button_pin)
        except:
            pass
        
        GPIO.setup(led_pin, GPIO.OUT)
        GPIO.setup(button_pin, GPIO.IN)
        
        def toggle_light(channel):
            manual_overrides[printer_name] = not manual_overrides[printer_name]
            if manual_overrides[printer_name]:
                GPIO.output(led_pin, GPIO.HIGH)
                print(f"[{printer_name}] Manual Override: LED ON")
            else:
                GPIO.output(led_pin, GPIO.LOW)
                print(f"[{printer_name}] Manual Override: OFF (Back to Flashlight mode)")
        
        # Setup the "Listen" for button press
        GPIO.add_event_detect(button_pin, GPIO.FALLING, callback=toggle_light, bouncetime=300)
        GPIO.output(led_pin, GPIO.LOW)  # Initially turn LED off
        print(f"[{printer_name}] GPIO initialized successfully")
    except Exception as e:
        print(f"[{printer_name}] Warning: Could not initialize GPIO: {e}")
        print(f"[{printer_name}] Continuing without LED control...")
        printer['led_control_enabled'] = False

def is_printer_online(printer):
    """Check if printer is online via Prusa Link API"""
    try:
        ip = printer.get('prusa_link_ip')
        user = printer.get('prusa_link_user')
        password = printer.get('prusa_link_password')
        
        if not ip:
            print(f"[{printer['name']}] No Prusa Link IP configured, skipping online check")
            return True  # If no IP configured, assume online
        
        url = f"http://{ip}/api/printer"
        auth = HTTPDigestAuth(user, password) if user and password else None
        
        response = requests.get(url, auth=auth, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Check if printer state indicates it's operational
            state = data.get('state', {}).get('text', '').lower()
            is_online = state in ['operational', 'printing', 'paused', 'ready']
            print(f"[{printer['name']}] Printer state: {state} - {'Online' if is_online else 'Offline'}")
            return is_online
        else:
            print(f"[{printer['name']}] Prusa Link returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"[{printer['name']}] Error checking printer status: {e}")
        return False

def get_real_temp():
    try:
        device_file = glob.glob('/sys/bus/w1/devices/28*/w1_slave')[0]
        with open(device_file, 'r') as f:
            lines = f.readlines()
        if 'YES' in lines[0]:
            temp_string = lines[1][lines[1].find('t=')+2:]
            return f"{float(temp_string) / 1000.0:.1f}°C"
    except: return "N/A"

def update_cam_info(cam):
    # Sends resolution and name to Prusa Connect
    headers = {"fingerprint": cam["fingerprint"], "token": cam["token"], "content-type": "application/json"}
    payload = {
        "config": {
            "name": cam["name"],
            "driver": "V4L2",
            "resolution": {"width": cam["width"], "height": cam["height"]}
        }
    }
    requests.put(INFO_URL, headers=headers, json=payload)

def process_camera(cam, printer):
    """Process and upload a single camera snapshot"""
    raw_file = f"/tmp/{cam['fingerprint']}_raw.jpg"
    out_file = f"/tmp/{cam['fingerprint']}_final.jpg"
    res_str = f"{cam['width']}x{cam['height']}"
    
    # 1. Capture using the camera's specific resolution
    subprocess.run(["fswebcam", "-d", cam["path"], "-r", res_str, "--no-banner", "-S", "10", raw_file], check=True)

    # 2. Overlay
    img = Image.open(raw_file)
    if cam["overlay_temp"]:
        draw = ImageDraw.Draw(img)
     
        font_size = int(cam["width"] / 35)
        try: 
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except: 
            font = ImageFont.load_default()
        
        text = f"Enclosure: {get_real_temp()}"
        bbox = draw.textbbox((20, 20), text, font=font)
        rect_bg = [bbox[0]-8, bbox[1]-8, bbox[2]+8, bbox[3]+8]
        draw.rectangle(rect_bg, fill=(255, 255, 255))
        text_color = (255, 128, 0)  # Prusa Orange
        draw.text((20, 20), text, fill=text_color, font=font)
    img.save(out_file)

    # 3. Upload
    headers = {"fingerprint": cam["fingerprint"], "token": cam["token"], "content-type": "image/jpg"}
    with open(out_file, "rb") as f:
        r = requests.put(SNAPSHOT_URL, headers=headers, data=f, timeout=15)
        if r.status_code not in [200, 204]:
            print(f"[{printer['name']}] Server rejected {cam['name']} with code {r.status_code}: {r.text}")
            r.raise_for_status()
        else:
            print(f"[{printer['name']}] Successfully uploaded {cam['name']}")

if __name__ == "__main__":
    try:
        GPIO.cleanup()
    except:
        pass
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    
    # Initialize GPIO and cameras for each printer
    for printer in PRINTERS:
        print(f"Initializing printer: {printer['name']}")
        init_gpio_for_printer(printer)
        
        for cam in printer['cameras']:
            try:
                update_cam_info(cam)
                print(f"[{printer['name']}] Initialized camera: {cam['name']}")
            except Exception as e:
                print(f"[{printer['name']}] Failed to init {cam['name']}: {e}")
    
    print(f"Starting camera upload loop (interval: {INTERVAL_SECONDS}s)")
    
    while True:
        for printer in PRINTERS:
            printer_name = printer['name']
            led_enabled = printer.get('led_control_enabled', False)
            led_pin = printer.get('led_pin')
            
            # Check if printer is online before processing cameras
            if not is_printer_online(printer):
                print(f"[{printer_name}] Printer is offline, skipping camera uploads")
                continue
            
            for cam in printer['cameras']:
                # Control LED if enabled
                if led_enabled and led_pin is not None:
                    manual = manual_overrides.get(printer_name, False)
                    if not manual:
                        GPIO.output(led_pin, GPIO.HIGH)
                        time.sleep(1)  # Wait for camera exposure to adjust
                
                try:
                    process_camera(cam, printer)
                    print(f"[{printer_name}] Updated {cam['name']} ({cam['width']}x{cam['height']})")
                except Exception as e:
                    print(f"[{printer_name}] Error on {cam['name']}: {e}")
                
                # Turn LED off if not in manual override mode
                if led_enabled and led_pin is not None:
                    manual = manual_overrides.get(printer_name, False)
                    if not manual:
                        GPIO.output(led_pin, GPIO.LOW)
        
        time.sleep(INTERVAL_SECONDS)  # sleep until next cycle