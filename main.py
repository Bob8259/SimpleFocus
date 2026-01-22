import subprocess
import re
import sys
import os
import time
import datetime
import keyboard

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

def start_recording(output_file=None):
    """Start recording the screen and audio."""
    if output_file is None:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = f"recording_{timestamp}.mp4"
    
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
    # -draw_mouse 0: hide the mouse cursor
    # -f gdigrab -i desktop: record the entire desktop
    command = [
        'ffmpeg',
        '-y',               # Overwrite output file
        '-f', 'gdigrab',
        '-draw_mouse', '0', # Hide mouse
        '-i', 'desktop',
    ] + audio_input + [
        '-c:v', 'libx264',   # Video codec
        '-preset', 'ultrafast',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',       # Audio codec
        output_file
    ]
    
    print(f"\nStarting recording to {output_file}...")
    print(f"Generated Command: {' '.join(command)}")
    
    # Use Popen to run in background
    return subprocess.Popen(command, stdin=subprocess.PIPE)

def stop_recording(process):
    """Stop the recording process gracefully."""
    if process.poll() is None:
        print("Stopping recording...")
        try:
            # Send 'q' to ffmpeg to stop gracefully
            process.stdin.write(b'q')
            process.stdin.flush()
            process.wait(timeout=5)
        except Exception as e:
            print(f"Error stopping gracefully: {e}")
            process.terminate()
        print("Recording stopped.")

if __name__ == "__main__":
    print("Press Ctrl+F1 to start recording.")
    print("Press Ctrl+F2 to stop recording.")
    print("Press Ctrl+C to exit.")
    
    recording_process = None
    
    try:
        while True:
            if keyboard.is_pressed('ctrl+f1'):
                if recording_process is None:
                    recording_process = start_recording()
                    # Debounce
                    time.sleep(1)
            
            if keyboard.is_pressed('ctrl+f2'):
                if recording_process is not None:
                    stop_recording(recording_process)
                    recording_process = None
                    time.sleep(1)
            
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nExiting...")
        if recording_process:
            stop_recording(recording_process)
