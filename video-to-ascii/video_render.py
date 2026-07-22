"""
Video renderer for video-to-ascii.
Downloads YouTube videos or loads local files and renders them as
coloured ASCII art in the terminal.
"""


import argparse
import atexit
import datetime
import os
import re
import shutil
import signal
import sys
import tempfile
import time
from threading import Lock, Thread
import queue
import cursor
import cv2
from PIL import Image


from ascii_convert import convert_frame, list_charsets
from ascii_html import write_html
from audio import detect_player, play_audio, stop_audio, pause_audio, resume_audio
from colours import Colours
from controls import PlaybackControls

import youtubedl_saver as ydls
class VideoNotYoutubeLink(Exception):
    def __init__(self, video_link: str, message: str = "The video entered was not a youtube video"):
        self.video_link = video_link
        self.message = message
        super().__init__(self.message)


def intro():
    print("\033[2J\033[H", end="", flush=True)
    print(f"{Colours.FAIL}{Colours.BOLD}{Colours.UNDERLINE}Video is starting...{Colours.END}")
    for countdown in range(3, 0, -1):
        print(f"{Colours.WARNING}{Colours.BOLD}{countdown}{Colours.END}")
        time.sleep(1)
    return True


__version__ = "1.1.0"

_ANSI_STRIP_RE = re.compile(r'\x1b\[[0-9;]*m')

def _visible_length(s):
    """Return length of string without ANSI escape sequences."""
    return len(_ANSI_STRIP_RE.sub('', s))



def parse_args():
    parser = argparse.ArgumentParser(
        description="Render a YouTube video or local file as coloured ASCII art "
                    "in the terminal."
    )
    parser.add_argument("vid", nargs="?",
                        help="YouTube URL or path to a local video file")
    parser.add_argument("--framerate", type=int, default=30,
                        help="Target framerate (default: 30, auto-detected for local files)")
    parser.add_argument("--buffer", type=float, default=0,
                        help="Pre-buffer amount as fraction of total frames, 0-1 (default: 0)")
    parser.add_argument("--video-mode", dest="video_mode", action="store_true",
                        help="Use background-coloured blocks for more vibrant output")
    parser.add_argument("--chars", default="standard",
                        help="Character set for colour mode: "
                             + ", ".join(list_charsets().keys())
                             + " (default: standard)")
    parser.add_argument("--list-charsets", action="store_true",
                        help="List available character sets and exit")
    parser.add_argument("--export-html", metavar="FILE",
                        help="Save ASCII animation to an HTML file for sharing")
    parser.add_argument("--no-audio", action="store_true",
                        help="Disable audio playback")
    parser.add_argument("--width", type=int, default=0,
                        help="Override output width in character columns")
    parser.add_argument("--height", type=int, default=0,
                        help="Override output height in character rows")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Playback speed multiplier (e.g. 0.5 = half speed, 2.0 = double)")
    parser.add_argument("--version", action="store_true",
                        help="Show version number and exit")
    parser.add_argument("--no-intro", action="store_true",
                        help="Skip the 3-2-1 countdown before playback")
    parser.add_argument("--loop", nargs="?", const=-1, default=0, type=int,
                        help="Loop playback: --loop for infinite, "
                             "--loop N for N times total (default: play once)")
    parser.add_argument("--contrast", type=float, default=1.0,
                        help="contrast enhancement factor")
    parser.add_argument("--brightness", type=float, default=1.0,
                        help="brightness enhancement factor")
    parser.add_argument("--dither", choices=["none", "ordered", "floyd"], default="none",
                        help="dither method")
    return parser.parse_args()


def cleanup():
    """Restore cursor visibility on exit."""
    try:
        cursor.show()
    except BrokenPipeError:
        pass


def _signal_handler(signum, frame):
    """Convert termination signals into KeyboardInterrupt."""
    raise KeyboardInterrupt()


class ASCIIVideoPlayer:
    """Orchestrates loading, buffering, and terminal playback of a video as ASCII."""

    def __init__(self, args):
        self.args = args
        self.watching_video = args.video_mode
        self.charset = args.chars
        self.no_audio = args.no_audio
        self.speed = args.speed if args.speed > 0 else 1.0
        self.loop_count = args.loop
        self.no_intro = args.no_intro
        self.override_w = args.width
        self.override_h = args.height

        # Populated by load_video()
        self.framerate = args.framerate
        self.total_frames = 0
        self.duration = 0
        self.video_cap = None
        self.audio_path = None
        self._owned_video_path = None   # set only for downloaded YouTube files

        self.export_html = args.export_html
        self._all_ascii_frames = []       # accumulated for loop cache / HTML export
        self.seek_request_frame = None
        self.terminal_resized = False
        # Threading state
        self.stopped = False
        self.frames_written = 0     # frames saved as JPEG
        self.frames_converted = 0   # frames turned into ASCII (sequential watermark)
        self.all_frames_read = False
        self.playback_started = False

        self.queue = {}             # index -> ASCII string
        self.lock = Lock()
        self.frame_queue = queue.Queue(maxsize=120)

        self.begin_time = None
        self.frame_begin_time = None
        self.audio_process = None
        self.audio_player = None    # name of detected audio player
        self.controls = PlaybackControls()
        self._last_terminal_size = (0, 0)
        self._last_shown_item = None
        self._last_shown_idx = 0
        self.times_played = 0
        # Thread references
        self._reader = None
        self._converters = []
        self._player = None

    def _start_processing_threads(self, start_frame=0):
        """Recreate and start reader and converter threads starting at start_frame."""
        with self.lock:
            if self._reader and self._reader.is_alive():
                return
            self.all_frames_read = False
            self.frames_written = start_frame
            self.stopped = False
            if self.video_cap:
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            # Flush the queue
            while not self.frame_queue.empty():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    break
            self._reader = Thread(target=self._read_frames, daemon=True)
            self._reader.start()
            self._converters = []
            nconv = 3
            for i in range(nconv):
                t = Thread(target=self._convert_frames, args=(i, nconv), daemon=True)
                t.start()
                self._converters.append(t)
    # ------------------------------------------------------------------
    # Video loading
    # ------------------------------------------------------------------

    def load_video(self):
        """Open a local file or download a YouTube URL.  Returns True on success."""
        vid = self.args.vid

        if os.path.isfile(vid):
            # --- Local file ---
            cap = cv2.VideoCapture(vid)
            if not cap.isOpened():
                print(f"{Colours.FAIL}Error: cannot open video file '{vid}'{Colours.END}")
                return False
            self.framerate = cap.get(cv2.CAP_PROP_FPS) or float(self.args.framerate)
            if self.framerate <= 0:
                self.framerate = 30.0
            self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.duration = self.total_frames / self.framerate if self.framerate > 0 else 0
            cap.release()
            self.video_cap = cv2.VideoCapture(vid)
            self.audio_path = vid
            print(f"{Colours.GREEN}Local file: {vid}  "
                  f"{self.total_frames} frames @ {self.framerate:.1f} fps, "
                  f"{self.duration:.1f}s{Colours.END}")
            return True

        # --- YouTube URL ---
        if not re.match(
            r'^(http(s)?://)?(www\.)?((youtube\.com/watch\?v=)|(youtu\.be/))([a-zA-Z0-9_-]{11})',
            vid
        ):
            if vid.startswith("http") or "youtube" in vid or "youtu.be" in vid:
                raise VideoNotYoutubeLink(vid)
            print(f"{Colours.FAIL}Error: not a valid file path or YouTube URL{Colours.END}")
            return False
        # Download to a unique temp path so we never collide with user files
        temp_download = os.path.join(tempfile.mkdtemp(prefix="ytdl_"), "video.mp4")
        video_location, self.framerate, self.total_frames, self.duration = ydls.save_file(
            vid, outtmpl=temp_download
        )
        if video_location == "error":
            return False
        if self.framerate <= 0:
            self.framerate = 30.0
        self.audio_path = video_location
        self._owned_video_path = video_location
        self.video_cap = cv2.VideoCapture(video_location)
        return True

    # ------------------------------------------------------------------
    # Sizing
    # ------------------------------------------------------------------

    def _render_size(self, frame_w, frame_h):
        """Return (target_w, target_h) in character-cells."""
        if self.override_w > 0 and self.override_h > 0:
            return self.override_w, self.override_h

        cols, lines = shutil.get_terminal_size((80, 24))

        if not hasattr(self, '_aspect_ratio_cache'):
            self._aspect_ratio_cache = {}
        cache_key = (cols, lines, frame_w, frame_h, self.watching_video, self.charset)
        if cache_key in self._aspect_ratio_cache:
            return self._aspect_ratio_cache[cache_key]

        if self.charset == "minimal" and not self.watching_video:
            max_w = cols - 2
        else:
            max_w = (cols - 2) // 2

        max_h = max(lines - 8, 5)

        if self.override_w > 0:
            max_w = self.override_w
        if self.override_h > 0:
            max_h = self.override_h

        scale = min(max_w / frame_w, max_h / frame_h)
        res = max(int(frame_w * scale), 1), max(int(frame_h * scale), 1)
        self._aspect_ratio_cache[cache_key] = res
        return res
    # ------------------------------------------------------------------
    # Thread targets
    def _read_frames(self):
        """Reader thread: read video -> resize -> enqueue for conversion."""
        try:
            render_size = None
            while not self.stopped:
                with self.lock:
                    if self.terminal_resized:
                        self.terminal_resized = False
                        render_size = None
                    if self.seek_request_frame is not None:
                        target = self.seek_request_frame
                        self.seek_request_frame = None
                        if self.video_cap:
                            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                        self.frames_written = target
                        # Flush the queue
                        while not self.frame_queue.empty():
                            try:
                                self.frame_queue.get_nowait()
                            except queue.Empty:
                                break

                ok, frame = self.video_cap.read()
                if not ok:
                    with self.lock:
                        self.all_frames_read = True
                    break
                h, w = frame.shape[:2]
                if render_size is None:
                    render_size = self._render_size(w, h)
                tw, th = render_size
                resized = cv2.resize(frame, (tw, th))
                with self.lock:
                    idx = self.frames_written
                    self.frames_written = idx + 1

                # Retry loop for putting frame into queue
                placed = False
                while not self.stopped and not placed:
                    with self.lock:
                        if self.seek_request_frame is not None:
                            break
                    try:
                        self.frame_queue.put((idx, resized), timeout=0.1)
                        placed = True
                    except queue.Full:
                        pass
        except KeyboardInterrupt:
            self.stopped = True

    def _convert_frames(self, tid, nthreads):
        """Converter thread: pull frames from queue and convert to ASCII."""
        while not self.stopped:
            try:
                idx, frame = self.frame_queue.get(timeout=0.1)
            except queue.Empty:
                with self.lock:
                    if self.all_frames_read and self.frame_queue.empty():
                        break
                continue

            # Skip conversion if already converted
            with self.lock:
                if idx < len(self._all_ascii_frames) and self._all_ascii_frames[idx] is not None:
                    continue

            try:
                pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                lines = convert_frame(pil_img, charset=self.charset,
                                      video_mode=self.watching_video,
                                      contrast=self.args.contrast,
                                      brightness=self.args.brightness,
                                      dither=self.args.dither)
                ascii_str = "\n".join(lines)
                with self.lock:
                    self.queue[idx] = ascii_str
                    if idx >= len(self._all_ascii_frames):
                        self._all_ascii_frames.extend([None] * (idx + 1 - len(self._all_ascii_frames)))
                    self._all_ascii_frames[idx] = ascii_str
                    while self.frames_converted < len(self._all_ascii_frames) and self._all_ascii_frames[self.frames_converted] is not None:
                        self.frames_converted += 1
            except Exception as e:
                if not self.stopped:
                    print(f"{Colours.FAIL}Error converting frame {idx}: {e}{Colours.END}", file=sys.stderr)
                with self.lock:
                    self.queue[idx] = ""
                    if idx >= len(self._all_ascii_frames):
                        self._all_ascii_frames.extend([None] * (idx + 1 - len(self._all_ascii_frames)))
                    self._all_ascii_frames[idx] = ""
    def _play_loop(self):
        """Playback thread: consume queue at the correct framerate.
        Supports --loop (infinite or N repeats).
        """
        delay = 1.0 / (self.framerate * self.speed)
        idx = 0
        all_cached = False
        audio_was_paused = False
        max_plays = self.loop_count  # 0 = once, -1 = infinite, N = N times
        pause_start = None

        try:
            while not self.stopped:
                if self.controls.should_quit():
                    self.stopped = True
                    break

                # --- Seek ---
                seek = self.controls.consume_seek()
                if seek != 0:
                    # seek is in seconds; convert to frames
                    seek_frames = int(seek * self.framerate) if self.framerate > 0 else int(seek * 30)
                    idx = max(0, min(idx + seek_frames, self.total_frames - 1))
                    with self.lock:
                        for stale in range(idx):
                            self.queue.pop(stale, None)

                    item_ready = False
                    if idx < len(self._all_ascii_frames):
                        with self.lock:
                            item_ready = (self._all_ascii_frames[idx] is not None)

                    if not item_ready:
                        with self.lock:
                            reader_alive = (self._reader and self._reader.is_alive())
                        if reader_alive:
                            with self.lock:
                                self.seek_request_frame = idx
                        else:
                            self._start_processing_threads(start_frame=idx)
                    
                    # Seek the audio by stopping and restarting at the new timestamp
                    stop_audio(self.audio_process)
                    current_time = idx / self.framerate if self.framerate > 0 else 0
                    self.audio_process = play_audio(self.audio_path, self.audio_player, start_time=current_time)
                    if audio_was_paused:
                        pause_audio(self.audio_process)

                    # Fix seek timing
                    now = datetime.datetime.now()
                    self.begin_time = now - datetime.timedelta(seconds=current_time)
                    self.frame_begin_time = now
                    if pause_start is not None:
                        pause_start = now

                # --- Pause ---
                if self.controls.is_paused():
                    if pause_start is None:
                        pause_start = datetime.datetime.now()
                    if not audio_was_paused:
                        # Suspend audio. If not supported (e.g. Windows), stop it.
                        if not pause_audio(self.audio_process):
                            stop_audio(self.audio_process)
                        audio_was_paused = True
                    cols, _ = shutil.get_terminal_size((80, 24))
                    if self._last_shown_item is not None:
                        self._show_frame(self._last_shown_item, self._last_shown_idx, datetime.datetime.now(), status="PAUSED")
                    else:
                        fallback_top = f"\033[90m┌{'─' * (cols - 2)}┐\033[0m"
                        fallback_mid = f"\033[90m│\033[0m\033[96;1m Loading... \033[0m{' ' * (cols - 16)}\033[90m│\033[0m"
                        fallback_bot = f"\033[90m└{'─' * (cols - 2)}┘\033[0m"
                        print(f"\033[H{fallback_top}\n{fallback_mid}\n{fallback_bot}", end="", flush=True)
                    time.sleep(0.1)
                    continue

                # --- Resume ---
                if pause_start is not None:
                    pause_duration = datetime.datetime.now() - pause_start
                    self.begin_time += pause_duration
                    self.frame_begin_time += pause_duration
                    pause_start = None

                if audio_was_paused:
                    # Resume audio. If we had stopped it (e.g. on Windows), restart at the current timestamp.
                    if not resume_audio(self.audio_process):
                        current_time = idx / self.framerate if self.framerate > 0 else 0
                        self.audio_process = play_audio(self.audio_path, self.audio_player, start_time=current_time)
                    audio_was_paused = False

                # --- Frame dropping to prevent audio-video drift ---
                now = datetime.datetime.now()
                elapsed_seconds = (now - self.begin_time).total_seconds()
                target_idx = int(elapsed_seconds * self.framerate * self.speed)
                if target_idx > idx:
                    with self.lock:
                        for stale_idx in range(idx, min(target_idx, self.total_frames)):
                            self.queue.pop(stale_idx, None)
                    idx = min(target_idx, self.total_frames)

                # --- Check end / loop ---
                if idx >= self.total_frames:
                    self.times_played += 1
                    if max_plays == 0:
                        break
                    if max_plays > 0 and self.times_played >= max_plays:
                        break
                    # Reset for next loop
                    idx = 0
                    all_cached = all(f is not None for f in self._all_ascii_frames)
                    self.begin_time = datetime.datetime.now()
                    self.frame_begin_time = datetime.datetime.now()
                    pause_start = None
                    # Restart audio for new loop
                    stop_audio(self.audio_process)
                    self._start_audio()
                    audio_was_paused = False
                    if not all_cached:
                        self._start_processing_threads(start_frame=0)
                    continue

                # --- Consume next frame ---
                item = None
                with self.lock:
                    if idx in self.queue:
                        item = self.queue.pop(idx)
                        if idx < len(self._all_ascii_frames) and self._all_ascii_frames[idx] is None:
                            self._all_ascii_frames[idx] = item
                    elif idx < len(self._all_ascii_frames):
                        item = self._all_ascii_frames[idx]

                if item is None:
                    # Restart processing threads if they died and frame is missing
                    with self.lock:
                        reader_alive = (self._reader and self._reader.is_alive())
                    if not reader_alive and idx < self.total_frames:
                        self._start_processing_threads(start_frame=idx)
                    time.sleep(0.001)
                    continue

                idx += 1
                self._last_shown_item = item
                self._last_shown_idx = idx

                # --- Timing ---
                now = datetime.datetime.now()
                elapsed = (now - self.frame_begin_time).total_seconds()
                remaining = delay - elapsed
                if remaining > 0:
                    time.sleep(remaining)
                    now = datetime.datetime.now()  # re-read after sleep
                self.frame_begin_time = now

                self._show_frame(item, idx, now)
        finally:
            self.stopped = True
            self._finish()


    def _show_frame(self, item, num, now=None, status="PLAYING"):
        """Print one frame to the terminal inside a Unicode Box Dashboard."""
        if now is None:
            now = datetime.datetime.now()
        elapsed = now - self.begin_time

        cols, lines = shutil.get_terminal_size((80, 24))

        # Check terminal resize each frame
        self._check_terminal_size(current_idx=max(0, num - 1))

        # Parse video dimensions and calculate margins
        video_lines = item.splitlines()
        vw = _visible_length(video_lines[0]) if video_lines else 0
        pad_w = max(0, (cols - 2 - vw) // 2)
        pad_right = max(0, cols - 2 - vw - pad_w)

        # Style colors
        border_color = "\033[90m"
        border_end = "\033[0m"

        # 1. Header
        filename = os.path.basename(self.args.vid) if self.args.vid else "Video"
        header_text = f" {filename} - {self.framerate:.1f} FPS - {status} "
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

        # 4. Footer Line 1: Progress
        pct = min(100, int(num / max(self.total_frames, 1) * 100))
        bar_w = max(10, min(cols - 30, 40))
        val = (pct / 100.0) * bar_w
        full_blocks = int(val)
        frac_part = val - full_blocks
        frac_idx = int(frac_part * 8)
        
        if full_blocks >= bar_w:
            bar_chars = "█" * bar_w
        else:
            frac_glyph = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"][frac_idx]
            has_frac = 1 if frac_glyph else 0
            empty_blocks = bar_w - full_blocks - has_frac
            bar_chars = "█" * full_blocks + frac_glyph + "░" * empty_blocks

        progress_text = f"Progress: [\033[96m{bar_chars}\033[0m] {pct}%"
        progress_visible_len = 12 + bar_w + len(str(pct))
        
        left_margin = 2
        right_space = cols - 2 - left_margin - progress_visible_len
        if right_space < 0:
            progress_line = f"{border_color}│{border_end}{progress_text}{border_color}│{border_end}"
        else:
            progress_line = f"{border_color}│{border_end}{' ' * left_margin}{progress_text}{' ' * right_space}{border_color}│{border_end}"

        # 5. Footer Line 2: Time, Speed, Loop
        elapsed_sec = int(elapsed.total_seconds()) if elapsed else 0
        elapsed_str = f"{elapsed_sec // 60:02d}:{elapsed_sec % 60:02d}"
        duration_sec = int(self.duration)
        duration_str = f"{duration_sec // 60:02d}:{duration_sec % 60:02d}"

        if self.loop_count == -1:
            loop_str = f"{self.times_played + 1}/infinite"
        elif self.loop_count == 0:
            loop_str = "1/1"
        else:
            loop_str = f"{self.times_played + 1}/{self.loop_count}"

        time_text = f"Time: {elapsed_str} / {duration_str}  |  Speed: {self.speed:.1f}x  |  Loop: {loop_str}"
        time_visible_len = len(time_text)
        right_space = cols - 2 - left_margin - time_visible_len
        if right_space < 0:
            time_line = f"{border_color}│{border_end}{time_text}{border_color}│{border_end}"
        else:
            time_line = f"{border_color}│{border_end}{' ' * left_margin}{time_text}{' ' * right_space}{border_color}│{border_end}"

        # 6. Footer Line 3: Keys Help
        keys_styled = "Keys: [\033[96mSpace/K\033[0m] Pause  [\033[96mQ\033[0m] Quit  [\033[96mJ/L/←/→\033[0m] Seek 5s"
        keys_visible_len = 49
        right_space = cols - 2 - left_margin - keys_visible_len
        if right_space < 0:
            keys_line = f"{border_color}│{border_end}{keys_styled}{border_color}│{border_end}"
        else:
            keys_line = f"{border_color}│{border_end}{' ' * left_margin}{keys_styled}{' ' * right_space}{border_color}│{border_end}"

        # 7. Bottom border
        bottom_line = f"{border_color}└{'─' * (cols - 2)}┘{border_end}"

        # Assemble and print
        dashboard = []
        dashboard.append(top_line)
        dashboard.extend(body_rows)
        dashboard.append(divider_line)
        dashboard.append(progress_line)
        dashboard.append(time_line)
        dashboard.append(keys_line)
        dashboard.append(bottom_line)

        try:
            print(f"\033[H" + "\n".join(dashboard), end="", flush=True)
        except BrokenPipeError:
            self.stopped = True

    def _check_terminal_size(self, current_idx=0):
        """Detect terminal resize and log if changed (recalc on next frame load)."""
        cur = shutil.get_terminal_size((80, 24))
        if cur != self._last_terminal_size:
            self._last_terminal_size = cur
            # Clear terminal completely to avoid residual layout artifacts on resize
            print("\033[2J\033[H", end="", flush=True)
            with self.lock:
                self.terminal_resized = True
                self._all_ascii_frames = [None] * self.total_frames
                self.frames_converted = current_idx
                self.seek_request_frame = current_idx

    def _cleanup_owned(self):
        """Remove the downloaded video file and its parent temp directory."""
        if self._owned_video_path:
            try:
                os.remove(self._owned_video_path)
                parent = os.path.dirname(self._owned_video_path)
                if parent:
                    os.rmdir(parent)
            except (FileNotFoundError, OSError):
                pass


    def _finish(self):
        """Stop audio, stop controls listener, write HTML export, print goodbye."""
        stop_audio(self.audio_process)
        self.controls.stop()

        # Release VideoCapture resources
        if self.video_cap:
            try:
                self.video_cap.release()
            except Exception:
                pass

        # Write HTML export if requested
        if self.export_html and self._all_ascii_frames:
            try:
                valid_frames = [f for f in self._all_ascii_frames if f is not None]
                if valid_frames:
                    write_html(valid_frames, self.framerate, self.export_html)
                    print(f"{Colours.GREEN}ASCII animation saved to {self.export_html}{Colours.END}")
                else:
                    print(f"{Colours.WARNING}No frames converted for HTML export{Colours.END}")
            except Exception as e:
                print(f"{Colours.FAIL}Error saving HTML export: {e}{Colours.END}")

        # Flush the frame queue to unblock reader/converters if blocked
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

        self._cleanup_owned()
        try:
            print(f"\n{Colours.FAIL}{Colours.BOLD}{Colours.UNDERLINE}Goodbye!{Colours.END}")
        except BrokenPipeError:
            pass

    def run(self):
        if not self.load_video():
            return False
        # Pre-allocate frames cache list
        self._all_ascii_frames = [None] * self.total_frames

        # Detect audio player
        self.audio_player = detect_player()

        # Start keyboard controls listener
        self.controls.start()

        # Start reader & converter threads
        self._start_processing_threads(start_frame=0)

        # --- Buffer phase ---
        target = max(int(self.total_frames * self.args.buffer), 1)
        if self.args.buffer > 0:
            print(f"{Colours.GREEN}Pre-buffering up to {target} frames…{Colours.END}")

        while not self.stopped:
            if self.args.buffer > 0 and self.frames_converted < target:
                with self.lock:
                    all_done = self.all_frames_read and self.frame_queue.empty()
                if all_done:
                    break
                pct = int(self.frames_converted / max(self.total_frames, 1) * 100)
                print(f"\r{Colours.GREEN}{Colours.BOLD}"
                      f"Buffering: {self.frames_converted}/{self.total_frames} ({pct}%)"
                      f"{Colours.END}",
                      end="")
                time.sleep(0.1)
                continue

            if not self.playback_started:
                if self.no_intro:
                    print("\033[2J\033[H", end="", flush=True)
                else:
                    intro()
                self.playback_started = True

                self._start_audio()
                self.begin_time = datetime.datetime.now()
                self.frame_begin_time = datetime.datetime.now()
                self._player = Thread(target=self._play_loop, daemon=True)
                self._player.start()

            time.sleep(0.1)

        # Join everything
        if self._reader:
            self._reader.join()
        for t in self._converters:
            t.join()
        if self._player and self._player.is_alive():
            self._player.join()
        return True
    def _start_audio(self):
        """Launch audio playback using the cross-platform audio module."""
        if self.no_audio:
            return
        if not self.audio_path or not os.path.isfile(self.audio_path):
            return
        if not self.audio_player:
            return
        self.audio_process = play_audio(self.audio_path, self.audio_player)


def main():
    args = parse_args()
    if args.version:
        print(f"video-to-ascii v{__version__}")
        sys.exit(0)

    # Handle --list-charsets
    if args.list_charsets:
        print("Available character sets:")
        for name, desc in list_charsets().items():
            print(f"  {name}  — {desc}")
        sys.exit(0)

    # vid is required unless --list-charsets was used
    if not args.vid:
        print(f"{Colours.FAIL}Error: a video URL or file path is required{Colours.END}")
        print("Usage: uv run python3 video_render.py <video-url-or-path> [options]")
        sys.exit(1)

    # Validate charset
    available = list_charsets()
    if args.chars not in available:
        print(f"{Colours.FAIL}Error: unknown charset '{args.chars}'. "
              f"Available: {', '.join(available)}{Colours.END}")
        sys.exit(1)

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    player = None
    try:
        cursor.hide()
        player = ASCIIVideoPlayer(args)
        if not player.run():
            sys.exit(1)
    except VideoNotYoutubeLink as e:
        print(f"{Colours.FAIL}Error: {e.message} — {e.video_link}{Colours.END}")
        sys.exit(1)
    except KeyboardInterrupt:
        if player:
            player.stopped = True
    finally:
        cleanup()

if __name__ == "__main__":
    main()
