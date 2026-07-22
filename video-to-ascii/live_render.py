"""
Live screen-capture renderer for video-to-ascii.
Captures a region of the screen and renders it as coloured ASCII art
in real time in the terminal.
"""

from __future__ import print_function

import re
import shutil
import sys
import argparse
import time
from datetime import datetime as dt
from threading import Lock, Thread
import cursor
try:
    import mss
except ImportError:
    print("Missing dependency: mss. Install with: uv pip install mss")
    sys.exit(1)
from PIL import Image
try:
    from pynput import keyboard
except ImportError:
    print("Missing dependency: pynput. Install with: uv pip install pynput")
    sys.exit(1)


from ascii_convert import convert_frame
from colours import Colours



_ANSI_STRIP_RE = re.compile(r'\x1b\[[0-9;]*m')
_last_terminal_size = (0, 0)

def _visible_length(s):
    """Return length of string without ANSI escape sequences."""
    return len(_ANSI_STRIP_RE.sub('', s))
# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MONITOR = {"top": 0, "left": 0, "width": 1920, "height": 1080}
args = None

# ---------------------------------------------------------------------------
# Shared mutable state
# ---------------------------------------------------------------------------

stopped = False
watching_video = False   # Toggled with Right-Shift
_watching_video_lock = Lock()
_counter_lock = Lock()
_timing_lock = Lock()
fps_counter = 0
image_buffer = 0
reset = False
has_started = False
last_second = 0
start_time = None


def input_checker(key):
    """Toggle video mode on Right-Shift."""
    global watching_video
    if key == keyboard.Key.shift_r:
        with _watching_video_lock:
            watching_video = not watching_video


def timing_module():
    """Update the timing state every second."""
    global stopped, reset, last_second, has_started, start_time

    with _timing_lock:
        last_second = 0
        start_time = dt.now()
        has_started = True

    while True:
        with _timing_lock:
            if stopped:
                break
        now = dt.now()
        with _timing_lock:
            elapsed = (now - start_time).seconds
            if elapsed >= last_second + 1:
                last_second += 1
                reset = True
        time.sleep(0.05)


def render_image_thread(tid):
    """Capture screen region → convert to ASCII → display."""
    global fps_counter, image_buffer, reset

    sct = mss.mss()
    try:
        framerate = args.framerate if (args and hasattr(args, "framerate")) else 30
        scale = args.scale if (args and hasattr(args, "scale")) else None
        contrast = args.contrast if (args and hasattr(args, "contrast")) else 1.0
        brightness = args.brightness if (args and hasattr(args, "brightness")) else 1.0
        dither = args.dither if (args and hasattr(args, "dither")) else "none"

        while True:
            with _timing_lock:
                if stopped:
                    break
                curr_reset = reset
                if reset:
                    reset = False
                curr_last_second = last_second
                curr_has_started = has_started

            if curr_has_started and curr_last_second > 0:
                desired = framerate * (curr_last_second + 1)
                with _counter_lock:
                    ib = image_buffer
                if ib >= desired:
                    time.sleep(0.005)
                    continue

            # Get target dimensions
            if scale is not None:
                height = max(MONITOR["height"] // scale, 1)
                width = max(MONITOR["width"] // scale, 1)
            else:
                cols, lines = shutil.get_terminal_size((80, 24))
                max_w = max(1, (cols - 2) // 2)
                max_h = max(1, lines - 4)
                aspect_ratio = MONITOR["width"] / MONITOR["height"]
                
                w1 = max_w
                h1 = int(w1 / aspect_ratio)
                if h1 <= max_h:
                    width = w1
                    height = max(1, h1)
                else:
                    height = max_h
                    width = max(1, int(height * aspect_ratio))

            # Grab and resize
            try:
                sct_img = sct.grab(MONITOR)
            except Exception:
                time.sleep(0.05)
                continue
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            if hasattr(Image, "Resampling"):
                resample_filter = Image.Resampling.LANCZOS
            else:
                resample_filter = Image.ANTIALIAS
                
                
            img = img.resize((width, height), resample_filter)

            with _watching_video_lock:
                vm = watching_video
            ascii_lines = convert_frame(img, video_mode=vm, contrast=contrast, brightness=brightness, dither=dither)
            display_frame("\n".join(ascii_lines), tid)

            with _counter_lock:
                fps_counter += 1
                image_buffer += 1
    finally:
        sct.close()


def display_frame(item, tid):
    """Print a single frame to the terminal."""
    global _last_terminal_size
    with _timing_lock:
        curr_start_time = start_time
    elapsed = dt.now() - curr_start_time if curr_start_time else 0
    elapsed_sec = int(elapsed.total_seconds()) if elapsed else 0
    elapsed_str = f"{elapsed_sec // 60:02d}:{elapsed_sec % 60:02d}"

    with _watching_video_lock:
        _vm = watching_video

    cols, lines = shutil.get_terminal_size((80, 24))
    if (cols, lines) != _last_terminal_size:
        _last_terminal_size = (cols, lines)
        # Clear terminal completely to avoid residual layout artifacts on resize
        print("\033[2J\033[H", end="", flush=True)

    # Parse video dimensions and calculate margins
    video_lines = item.splitlines()
    vw = _visible_length(video_lines[0]) if video_lines else 0
    pad_w = max(0, (cols - 2 - vw) // 2)
    pad_right = max(0, cols - 2 - vw - pad_w)

    # Style colors
    border_color = "\033[90m"
    border_end = "\033[0m"

    # 1. Header
    header_text = f" LIVE SCREEN CAPTURE - THREAD {tid} "
    header_styled = f"\033[96;1m{header_text}\033[0m"
    header_len = len(header_text)

    if cols - 2 >= header_len:
        left_dashes = (cols - 2 - header_len) // 2
        right_dashes = cols - 2 - header_len - left_dashes
        top_line = f"{border_color}┌{'─' * left_dashes}{border_end}{header_styled}{border_color}{'─' * right_dashes}┐{border_end}"
    else:
        top_line = f"{border_color}┌{'─' * (cols - 2)}┐{border_end}"

    # 2. Body lines (centered)
    body_rows = []
    for vl in video_lines:
        body_rows.append(f"{border_color}│{border_end}{' ' * pad_w}{vl}{' ' * pad_right}{border_color}│{border_end}")

    # 3. Divider
    divider_line = f"{border_color}├{'─' * (cols - 2)}┤{border_end}"

    # 4. Footer
    footer_text = f"Status: ACTIVE  |  Video Mode: {_vm}  |  Elapsed: {elapsed_str}"
    footer_visible_len = len(footer_text)
    left_margin = 2
    right_space = cols - 2 - left_margin - footer_visible_len
    if right_space < 0:
        footer_line = f"{border_color}│{border_end}{footer_text}{border_color}│{border_end}"
    else:
        footer_line = f"{border_color}│{border_end}{' ' * left_margin}{footer_text}{' ' * right_space}{border_color}│{border_end}"

    # 5. Bottom border
    bottom_line = f"{border_color}└{'─' * (cols - 2)}┘{border_end}"

    # Assemble and print
    dashboard = []
    dashboard.append(top_line)
    dashboard.extend(body_rows)
    dashboard.append(divider_line)
    dashboard.append(footer_line)
    dashboard.append(bottom_line)

    print(f"\033[H" + "\n".join(dashboard), end="", flush=True)

def main():
    global stopped, fps_counter, image_buffer, watching_video, start_time, args, MONITOR

    parser = argparse.ArgumentParser(description="Live screen-capture renderer for video-to-ascii.")
    parser.add_argument("--monitor", type=int, default=1, help="Monitor index to capture.")
    parser.add_argument("--region", type=str, help="Bounding box coordinates as left,top,width,height.")
    parser.add_argument("--framerate", type=int, default=30, help="Target frame rate.")
    parser.add_argument("--scale", type=int, help="Fixed scale divisor.")
    parser.add_argument("--video-mode", action="store_true", help="Start in video mode blocks.")
    parser.add_argument("--threads", type=int, default=4, help="Number of capture/rendering threads.")
    parser.add_argument("--contrast", type=float, default=1.0, help="contrast enhancement factor")
    parser.add_argument("--brightness", type=float, default=1.0, help="brightness enhancement factor")
    parser.add_argument("--dither", choices=["none", "ordered", "floyd"], default="none", help="dither method")
    args = parser.parse_args()

    with _watching_video_lock:
        watching_video = args.video_mode

    # Fetch actual coordinates using mss
    with mss.mss() as sct:
        monitor_idx = args.monitor
        # Fall back to index 0 if the default index 1 is out of range (e.g. single-monitor VM or container)
        if monitor_idx == 1 and len(sct.monitors) == 1:
            monitor_idx = 0

        if monitor_idx < 0 or monitor_idx >= len(sct.monitors):
            print(f"Error: Monitor index {monitor_idx} is out of range. Available monitors: 0 to {len(sct.monitors)-1}", file=sys.stderr)
            sys.exit(1)
        monitor_info = dict(sct.monitors[monitor_idx])

    if args.region:
        try:
            parts = [int(p.strip()) for p in args.region.split(',')]
            if len(parts) == 4:
                monitor_info = {
                    "left": parts[0],
                    "top": parts[1],
                    "width": parts[2],
                    "height": parts[3]
                }
            else:
                raise ValueError("Expected 4 comma-separated values (left,top,width,height)")
        except ValueError as e:
            print(f"Error parsing region: {e}. Format must be left,top,width,height", file=sys.stderr)
            sys.exit(1)

    MONITOR = monitor_info

    # Start keyboard listener
    listener = None
    try:
        listener = keyboard.Listener(on_press=input_checker)
        listener.start()
    except Exception as e:
        print(f"{Colours.WARNING}Warning: Could not start keyboard listener. "
              f"Keyboard shortcuts will be disabled. (Error: {e}){Colours.END}")

    # Start capture threads
    num_threads = args.threads
    if num_threads < 1:
        print("Error: --threads must be at least 1", file=sys.stderr)
        sys.exit(1)
    threads = []
    for i in range(num_threads):
        t = Thread(target=render_image_thread, args=[i])
        t.start()
        threads.append(t)
        time.sleep(1 / 8)  # Stagger starts

    try:
        cursor.hide()
        timing_module()
    except KeyboardInterrupt:
        pass
    finally:
        with _timing_lock:
            stopped = True
        cursor.show()
        for t in threads:
            t.join()
        if listener:
            try:
                listener.stop()
            except Exception:
                pass
        print(f"\n{Colours.FAIL}{Colours.BOLD}Stopped.{Colours.END}")

if __name__ == "__main__":
    if sys.platform == "darwin":
        print(f"{Colours.WARNING}Note: On macOS, screen capture requires "
              f"Screen Recording permission in System Settings.{Colours.END}")
    main()
