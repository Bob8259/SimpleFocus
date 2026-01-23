import cv2
import json
import argparse
import os
import subprocess
import shutil

def draw_transparent_circle(image, center, radius, color, alpha):
    """Draws a transparent circle on the image."""
    overlay = image.copy()
    cv2.circle(overlay, center, radius, color, -1)
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)

def process_video(video_path):
    json_path = os.path.splitext(video_path)[0] + ".json"
    
    if not os.path.exists(json_path):
        print(f"Error: JSON file not found at {json_path}")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)
        
    # Handle both old and new json formats (list vs dict)
    if isinstance(data, list):
        print("Error: JSON format is outdated (list instead of dict). Please re-record.")
        return
        
    start_time = data.get("start_time")
    events = data.get("events", [])

    if start_time is None:
        print("Error: start_time not found in JSON data.")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    # Video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    temp_output_path = video_path.replace(".mp4", "_temp.mp4")
    final_output_path = video_path.replace(".mp4", "_processed.mp4")

    # Use mp4v codec for temp video
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))

    print(f"Processing video: {video_path}")
    print(f"Total frames: {total_frames}, FPS: {fps}")

    frame_idx = 0
    active_clicks = [] # List of tuples: (x, y, start_frame_idx)
    
    CLICK_DURATION_SEC = 0.5
    CLICK_frames = int(CLICK_DURATION_SEC * fps)
    MAX_RADIUS = 30
    COLOR = (0, 0, 255) # Red in BGR

    # Zoom parameters
    ZOOM_LEVEL = 1.3
    ZOOM_DURATION = 1.5
    ZOOM_SMOOTHING = 0.1
    
    current_zoom = 1.0
    current_center_x = width / 2.0
    current_center_y = height / 2.0
    
    last_click_time = -10.0
    last_click_pos = (width / 2.0, height / 2.0)

    # Initialize last_video_time slightly negative so events at 0.0 are caught
    last_video_time = -1.0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Calculate current timestamp of the frame using frame position
        # CAP_PROP_POS_MSEC returns milliseconds, so divide by 1000
        current_video_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        
        # Add new events to active_clicks
        for event in events:
            # User reported video is delayed by roughly 0.2s, so we delay events to match
            DELAY_OFFSET = 0.7 
            event_video_time = (event['time'] + DELAY_OFFSET) - start_time
            
            # Check if this event happened between the last frame and this frame
            if last_video_time < event_video_time <= current_video_time:
                 if event['action'] == 'pressed' and event['button'] == 'left':
                     active_clicks.append({
                         'x': event['x'],
                         'y': event['y'],
                         'start_time': event_video_time, # Store exact start time, not frame
                     })
                     # Update zoom target on new click
                     if event_video_time > last_click_time:
                         last_click_time = event_video_time
                         last_click_pos = (event['x'], event['y'])

        # Draw active clicks
        clicks_to_keep = []
        for click in active_clicks:
            time_since_click = current_video_time - click['start_time']
            
            if 0 <= time_since_click < CLICK_DURATION_SEC:
                # Shrink effect: Radius goes from MAX to 0
                progress = time_since_click / CLICK_DURATION_SEC
                radius = int(MAX_RADIUS * (1 - progress))
                
                # Draw
                if radius > 0:
                    # Red circle with some transparency
                    draw_transparent_circle(frame, (click['x'], click['y']), radius, COLOR, 0.6)
                
                clicks_to_keep.append(click)
        
        active_clicks = clicks_to_keep
        last_video_time = current_video_time

        # Calculate target zoom state
        time_since_last_click = current_video_time - last_click_time
        if time_since_last_click < ZOOM_DURATION:
            target_zoom = ZOOM_LEVEL
            target_cx, target_cy = last_click_pos
        else:
            target_zoom = 1.0
            target_cx, target_cy = width / 2.0, height / 2.0

        # Smooth update
        current_zoom += (target_zoom - current_zoom) * ZOOM_SMOOTHING
        current_center_x += (target_cx - current_center_x) * ZOOM_SMOOTHING
        current_center_y += (target_cy - current_center_y) * ZOOM_SMOOTHING

        # Apply Zoom via Crop/Resize
        if abs(current_zoom - 1.0) > 0.001:
            view_w = width / current_zoom
            view_h = height / current_zoom
            
            # Top-left corner (clamped)
            x1 = current_center_x - view_w / 2
            y1 = current_center_y - view_h / 2
            
            x1 = max(0, min(x1, width - view_w))
            y1 = max(0, min(y1, height - view_h))
            
            # Crop and Resize
            # Ensure coordinates are integers for slicing
            x1_int = int(x1)
            y1_int = int(y1)
            w_int = int(view_w)
            h_int = int(view_h)

            # Fix rounding issues that might cause empty crop
            if w_int > 0 and h_int > 0:
                crop = frame[y1_int : y1_int + h_int, x1_int : x1_int + w_int]
                # Use INTER_LINEAR for speed, or INTER_CUBIC for quality
                frame = cv2.resize(crop, (width, height), interpolation=cv2.INTER_LINEAR)

        out.write(frame)
        frame_idx += 1
        
        if frame_idx % 100 == 0:
            print(f"Processed {frame_idx}/{total_frames} frames...")

    cap.release()
    out.release()
    print("Video processing complete. Merging audio...")

    # Merge audio from original video using ffmpeg
    # ffmpeg -i temp_video -i original_video -c:v copy -c:a copy -map 0:v:0 -map 1:a:0 output
    # If original has no audio, this might fail or produce silent audio.
    # We use -shortest to avoid issues if lengths differ slightly
    
    try:
        command = [
            'ffmpeg', '-y',
            '-i', temp_output_path,
            '-i', video_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            final_output_path
        ]
        
        # Check if original file has audio stream first? 
        # For simplicity, try merging. If it fails (no audio), just copy video.
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("Warning: FFmpeg audio merge failed (maybe no audio in source?). Copying video only.")
            print(result.stderr)
            shutil.copy(temp_output_path, final_output_path)
            
    except Exception as e:
        print(f"Error during audio merge: {e}")
        shutil.copy(temp_output_path, final_output_path)

    # Cleanup
    if os.path.exists(temp_output_path):
        os.remove(temp_output_path)
        
    print(f"Done! Saved to {final_output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add mouse click effects to recorded video.")
    parser.add_argument("input_video", help="Path to the recorded mp4 file.")
    args = parser.parse_args()
    
    process_video(args.input_video)
