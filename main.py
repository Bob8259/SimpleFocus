import subprocess
import re
import sys
import os

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

def record_screen_and_audio(output_file="output.mp4"):
    """Record the screen and audio from the selected microphone."""
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
    
    print("\nStarting recording... Press Ctrl+C to stop.")
    print(f"Generated Command: {' '.join(command)}")
    
    try:
        # We use a subprocess.Popen to allow for a clean interruption if needed
        # but here subprocess.run is fine for a simple script
        subprocess.run(command)
    except KeyboardInterrupt:
        print("\nRecording stopped by user.")
    except Exception as e:
        print(f"An error occurred during recording: {e}")

if __name__ == "__main__":
    record_screen_and_audio()
