import subprocess
import re
import sys
import os
import time
import datetime
import keyboard
import json
import threading
from pynput import mouse

mouse_listener = None
mouse_events = []
recording_start_time = None

def on_click(x, y, button, pressed):
    if pressed and button == mouse.Button.left:
        event = {
            "time": time.time(),
            "x": x,
            "y": y,
            "button": "left",
            "action": "pressed"
        }
        mouse_events.append(event)

def start_mouse_listener():
    global mouse_listener, mouse_events
    mouse_events = []
    mouse_listener = mouse.Listener(on_click=on_click)
    mouse_listener.start()

def stop_mouse_listener():
    global mouse_listener
    if mouse_listener:
        mouse_listener.stop()
        mouse_listener = None

def get_audio_devices():
    """List available audio devices using ffmpeg and return them as a list."""
    try:
        # Run ffmpeg to list devices. We use -list_devices true -f dshow -i dummy
        # Ffmpeg sends this info to stderr.
        result = subprocess.run(
            ['ffmpeg', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=False # Get raw bytes to handle encoding
        )
        
        # Try different encodings for Windows
        output = ""
        for encoding in ['utf-8', 'gbk', 'cp936']:
            try:
                output = result.stderr.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
                
        if not output:
            output = result.stderr.decode('utf-8', errors='ignore')

    except Exception as e:
        print(f"Error running ffmpeg: {e}")
        return []

    # The devices are listed in the stderr
    audio_devices = []
    
    # regex to match device names in dshow output
    # example: [dshow @ 000001...]  "Microphone (Realtek Audio)" (audio)
    # We relaxed the check to not depend on "DirectShow audio devices" header
    device_name_pattern = re.compile(r'\"(.*?)\"\s+\(audio\)')
    
    for line in output.split('\n'):
        match = device_name_pattern.search(line)
        if match:
            device_name = match.group(1)
            # Avoid duplicates
            if device_name not in audio_devices:
                audio_devices.append(device_name)
                
    return audio_devices

def select_best_microphone(devices):
    """Select the best microphone based on keywords."""
    priority_keywords = ["耳机", "headphone", "headset"]
    secondary_keywords = ["麦克风", "microphone", "mic"]
    
    # Search for priority keywords first
    for kw in priority_keywords:
        for device in devices:
            if kw.lower() in device.lower():
                return device
                
    # Search for secondary keywords
    for kw in secondary_keywords:
        for device in devices:
            if kw.lower() in device.lower():
                return device
                
    # If no keywords match, return the first one if available
    if devices:
        return devices[0]
        
    return None

def monitor_ffmpeg_output(process):
    """Monitor ffmpeg output to detect when recording starts."""
    global recording_start_time
    started = False
    while True:
        # Read line from stderr
        line = process.stderr.readline()
        if not line:
            break
            
        # Print the line so the user can still see ffmpeg output
        print(line, end='', file=sys.stderr)
        
        # Check for start indicators
        if not started and ("Press [q] to stop" in line or "frame=" in line):
            print("start")
            sys.stdout.flush() # Ensure it prints immediately
            recording_start_time = time.time()
            started = True

def start_recording(output_file=None):
    """Start recording the screen and audio."""
    if output_file is None:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = f"recording_{timestamp}.mp4"
    
    # Load recording area from config
    recording_area = None
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recording_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                recording_area = config.get("recording_area")
        except Exception as e:
            print(f"Error loading config: {e}")

    devices = get_audio_devices()
    print(f"Detected audio devices: {devices}")
    
    mic = select_best_microphone(devices)
    
    if not mic:
        print("No audio devices detected. Proceeding without audio...")
        audio_input = []
    else:
        print(f"Selected microphone: {mic}")
        audio_input = ['-f', 'dshow', '-i', f'audio={mic}']
        
    # FFmpeg command for screen recording (gdigrab) and audio (dshow)
    # -draw_mouse 1: record the mouse cursor
    # -f gdigrab -i desktop: record the entire desktop
    command = [
        'ffmpeg',
        '-y',               # Overwrite output file
        '-f', 'gdigrab',
        '-draw_mouse', '1', # Record mouse
    ]

    # Apply recording area if specified
    if recording_area and len(recording_area) == 4:
        x, y, w, h = recording_area
        print(f"Recording area: x={x}, y={y}, width={w}, height={h}")
        command.extend([
            '-offset_x', str(x),
            '-offset_y', str(y),
            '-video_size', f"{w}x{h}"
        ])
    else:
        print("Recording full screen.")

    command.extend(['-i', 'desktop'])
    command.extend(audio_input)
    
    command.extend([
        '-c:v', 'libx264',   # Video codec
        '-preset', 'ultrafast',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',       # Audio codec
        output_file
    ])
    
    print(f"\nStarting recording to {output_file}...")
    print(f"Generated Command: {' '.join(command)}")
    
    # Use Popen to run in background, redirect stderr to monitor start
    process = subprocess.Popen(
        command, 
        stdin=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        text=True, 
        errors='replace'
    )
    
    # Start output monitoring in a separate thread
    monitor_thread = threading.Thread(target=monitor_ffmpeg_output, args=(process,), daemon=True)
    monitor_thread.start()

    start_mouse_listener()

    return process, output_file

def stop_recording(process, output_file):
    """Stop the recording process gracefully."""
    if process.poll() is None:
        print("Stopping recording...")
        try:
            # Send 'q' to ffmpeg to stop gracefully
            process.stdin.write('q')
            process.stdin.flush()
            process.wait(timeout=5)
        except Exception as e:
            print(f"Error stopping gracefully: {e}")
            process.terminate()
        print("Recording stopped.")
    
    stop_mouse_listener()
    
    if output_file:
        json_path = os.path.splitext(output_file)[0] + ".json"
        try:
            with open(json_path, 'w') as f:
                data = {
                    "start_time": recording_start_time,
                    "events": mouse_events
                }
                json.dump(data, f, indent=4)
            print(f"Mouse events saved to {json_path}")
        except Exception as e:
            print(f"Error saving mouse events: {e}")

    # Auto-run post-processing
    if output_file:
        try:
            print("Starting post-processing...")
            post_process_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'post_process_video.py')
            subprocess.Popen(['python', post_process_script, output_file])
        except Exception as e:
            print(f"Error starting post-processing: {e}")

if __name__ == "__main__":
    print("Press Ctrl+F1 to start recording.")
    print("Press Ctrl+F2 to stop recording.")
    print("Press Ctrl+C to exit.")
    
    recording_process = None
    current_output_file = None
    
    try:
        while True:
            if keyboard.is_pressed('ctrl+f1'):
                if recording_process is None:
                    recording_process, current_output_file = start_recording()
                    # Debounce
                    time.sleep(1)
            
            if keyboard.is_pressed('ctrl+f2'):
                if recording_process is not None:
                    stop_recording(recording_process, current_output_file)
                    recording_process = None
                    current_output_file = None
                    time.sleep(1)
            
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nExiting...")
        if recording_process:
            stop_recording(recording_process, current_output_file)
