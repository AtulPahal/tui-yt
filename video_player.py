"""
Video renderer and player engine for tui-yt.
"""
import os
import queue
import re
import shutil
import tempfile
import time
from threading import Lock, Thread

import cursor
import cv2

from audio_player import detect_player, play_audio, stop_audio, pause_audio, resume_audio
from colours import Colours
from playback_controls import PlaybackControls
import yt_saver as ydls
from ascii_convert import convert_frame


class VideoNotYoutubeLink(Exception):
    def __init__(self, video_link: str, message: str = "The video entered was not a youtube video"):
        self.video_link = video_link
        self.message = message
        super().__init__(self.message)


__version__ = "1.1.0"
_ANSI_STRIP_RE = re.compile(r'\x1b\[[0-9;]*m')


def _visible_length(s):
    return len(_ANSI_STRIP_RE.sub('', s))

class ASCIIVideoPlayer:
    def __init__(self, args):
        self.args = args
        self.watching_video = args.video_mode
        self.charset = args.chars
        self.no_audio = args.no_audio
        self.speed = args.speed if args.speed > 0 else 1.0
        self.quality = getattr(args, "quality", "720p")
        self.download_first = getattr(args, "download_first", False)
        self.no_intro = args.no_intro
        self.override_w = args.width
        self.override_h = args.height

        self.framerate = args.framerate
        self.total_frames = 0
        self.duration = 0
        self.video_cap = None
        self.audio_path = None
        self._owned_video_dir = None
        self._owned_video_path = None

        self.export_html = args.export_html
        self._all_ascii_frames = []
        self.seek_request_frame = None
        self.terminal_resized = False
        self.stopped = False
        self.frames_written = 0
        self.frames_converted = 0
        self.all_frames_read = False
        self.lock = Lock()
        self.frame_queue = queue.Queue(maxsize=120)

        self.begin_time = None
        self.audio_process = None
        self.audio_player = None
        self.controls = PlaybackControls()
        self._last_shown_item = None
        self._last_shown_idx = 0
        self._aspect_ratio_cache = {}

        self._reader = None
        self._converters = []
        self._term_cols, self._term_lines = 80, 24
        self._term_refresh = 0

    def _start_processing_threads(self, start_frame=0):
        with self.lock:
            if self._reader and self._reader.is_alive():
                return
            self.all_frames_read = False
            self.frames_written = start_frame
            self.stopped = False
            if self.video_cap:
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            while not self.frame_queue.empty():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    break
            self._reader = Thread(target=self._read_frames, daemon=True)
            self._reader.start()
            self._converters = []
            t = Thread(target=self._convert_frames, daemon=True)
            t.start()
            self._converters.append(t)

    def load_video(self):
        vid = self.args.vid

        if os.path.isfile(vid):
            cap = cv2.VideoCapture(vid)
            if not cap.isOpened():
                cap.release()
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
            return True

        if not re.match(
            r'^(http(s)?://)?(www\.)?((youtube\.com/watch\?v=)|(youtu\.be/))([a-zA-Z0-9_-]{11})',
            vid
        ):
            if vid.startswith("http") or "youtube" in vid or "youtu.be" in vid:
                raise VideoNotYoutubeLink(vid)
            print(f"{Colours.FAIL}Error: not a valid file path or YouTube URL{Colours.END}")
            return False

        if not self.download_first:
            video_url, audio_url, fps, total_frames, duration = ydls.get_stream_info(vid, quality=self.quality)
            if video_url != "error" and video_url:
                self.framerate = fps if fps > 0 else 30.0
                self.total_frames = total_frames
                self.duration = duration
                self.audio_path = audio_url
                self.video_cap = cv2.VideoCapture(video_url)
                if self.video_cap.isOpened():
                    return True

        temp_dir = tempfile.mkdtemp(prefix="ytdl_")
        temp_download = os.path.join(temp_dir, "video.mp4")
        video_location, self.framerate, self.total_frames, self.duration = ydls.save_file(
            vid, outtmpl=temp_download, quality=self.quality
        )
        if video_location == "error":
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass
            return False
        if self.framerate <= 0:
            self.framerate = 30.0
        self.audio_path = video_location
        self._owned_video_path = video_location
        self._owned_video_dir = temp_dir
        self.video_cap = cv2.VideoCapture(video_location)
        return True

    def _render_size(self, frame_w, frame_h):
        if self.override_w > 0 and self.override_h > 0:
            return self.override_w, self.override_h

        cols, lines = shutil.get_terminal_size((80, 24))
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

    def _read_frames(self):
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
                        while not self.frame_queue.empty():
                            try:
                                self.frame_queue.get_nowait()
                            except queue.Empty:
                                break
                    if self.video_cap is None or self.stopped:
                        self.all_frames_read = True
                        break
                if self.stopped:
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

    def _convert_frames(self):
        while not self.stopped:
            try:
                idx, frame = self.frame_queue.get(timeout=0.1)
            except queue.Empty:
                with self.lock:
                    if self.all_frames_read and self.frame_queue.empty():
                        break
                continue

            # Skip if another converter already handled this frame
            with self.lock:
                if idx < len(self._all_ascii_frames) and self._all_ascii_frames[idx] is not None:
                    continue

            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                lines = convert_frame(rgb_frame, charset=self.charset,
                                      video_mode=self.watching_video,
                                      contrast=self.args.contrast,
                                      brightness=self.args.brightness,
                                      dither=self.args.dither)
                with self.lock:
                    if idx >= len(self._all_ascii_frames):
                        self._all_ascii_frames.extend([None] * (idx + 1 - len(self._all_ascii_frames)))
                    self._all_ascii_frames[idx] = lines
                    while self.frames_converted < len(self._all_ascii_frames) and self._all_ascii_frames[self.frames_converted] is not None:
                        self.frames_converted += 1
            except Exception:
                empty = [""]
                with self.lock:
                    if idx >= len(self._all_ascii_frames):
                        self._all_ascii_frames.extend([None] * (idx + 1 - len(self._all_ascii_frames)))
                    self._all_ascii_frames[idx] = empty

    def _play_loop(self):
        idx = 0
        audio_was_paused = False
        pause_start = None
        try:
            while not self.stopped:
                if self.controls.should_quit():
                    self.stopped = True
                    break

                seek = self.controls.consume_seek()
                if seek != 0:
                    seek_frames = int(seek * self.framerate) if self.framerate > 0 else int(seek * 30)
                    max_frame = max(0, self.total_frames - 1)
                    idx = max(0, min(idx + seek_frames, max_frame))

                    item_ready = False
                    reader_alive = False
                    with self.lock:
                        if idx < len(self._all_ascii_frames):
                            item_ready = self._all_ascii_frames[idx] is not None
                        reader_alive = self._reader and self._reader.is_alive()
                        if not item_ready and reader_alive:
                            self.seek_request_frame = idx
                            if not self._reader or not self._reader.is_alive():
                                reader_alive = False

                    if not item_ready:
                        if not reader_alive:
                            self._start_processing_threads(start_frame=idx)
                    else:
                        need_restart = False
                        if not reader_alive:
                            with self.lock:
                                need_restart = self.all_frames_read
                        if need_restart:
                            self._start_processing_threads(start_frame=idx)

                    current_time = idx / self.framerate if self.framerate > 0 else 0
                    if not self.no_audio:
                        stop_audio(self.audio_process)
                        self.audio_process = play_audio(self.audio_path, self.audio_player,
                                                        start_time=current_time, speed=self.speed)
                        if audio_was_paused:
                            pause_audio(self.audio_process)

                    self.begin_time = time.monotonic() - current_time
                    if pause_start is not None:
                        pause_start = time.monotonic()
                    self._last_shown_idx = idx

                speed_info = self.controls.consume_speed_change()
                if isinstance(speed_info, (tuple, list)) and len(speed_info) == 2:
                    speed_delta, speed_reset = speed_info
                    old_speed = self.speed
                    if speed_reset:
                        self.speed = 1.0
                    elif speed_delta != 0.0:
                        self.speed = max(0.25, min(4.0, self.speed + speed_delta))
                    if speed_delta != 0.0 or speed_reset:
                        if not self.no_audio and self.audio_process and not audio_was_paused:
                            stop_audio(self.audio_process)
                            current_time = idx / self.framerate if self.framerate > 0 else 0
                            self.audio_process = play_audio(self.audio_path, self.audio_player,
                                                            start_time=current_time, speed=self.speed)
                        if self.begin_time is not None:
                            current_pos_secs = idx / (self.framerate * old_speed) if self.framerate > 0 else 0
                            new_current_pos_secs = idx / (self.framerate * self.speed) if self.framerate > 0 else 0
                            self.begin_time += current_pos_secs - new_current_pos_secs

                if self.controls.is_paused():
                    if pause_start is None:
                        pause_start = time.monotonic()
                    if not audio_was_paused:
                        if not pause_audio(self.audio_process):
                            stop_audio(self.audio_process)
                        audio_was_paused = True
                    if self._last_shown_item is not None:
                        self._show_frame(self._last_shown_item, self._last_shown_idx, status="PAUSED")
                    time.sleep(0.05)
                    continue

                if audio_was_paused:
                    if not resume_audio(self.audio_process):
                        resume_time = idx / self.framerate if self.framerate > 0 else 0
                        self.audio_process = play_audio(self.audio_path, self.audio_player,
                                                        start_time=resume_time, speed=self.speed)
                    audio_was_paused = False
                    if pause_start is not None:
                        self.begin_time += time.monotonic() - pause_start
                        pause_start = None

                # Single lock for frame fetch + end-of-video check
                item = None
                all_read = False
                with self.lock:
                    if idx < len(self._all_ascii_frames):
                        item = self._all_ascii_frames[idx]
                    if item is None:
                        all_read = self.all_frames_read

                if item is None:
                    if all_read and idx >= (self.total_frames if self.total_frames > 0 else self.frames_converted):
                        break
                    time.sleep(0.005)
                    continue

                now = time.monotonic()
                if self.begin_time is None:
                    self.begin_time = now
                    if not self.no_audio and not self.audio_process:
                        self._start_audio()

                fps = self.framerate if self.framerate > 0 else 30
                target = self.begin_time + idx / (fps * self.speed)
                sleep_dur = target - now
                if sleep_dur > 0:
                    time.sleep(sleep_dur)
                self._show_frame(item, idx)
                self._last_shown_item = item
                self._last_shown_idx = idx
                idx += 1

                # Check reader thread health
                if self._reader and not self._reader.is_alive() and not self.all_frames_read:
                    self.stopped = True
                    break

                # Prune converted frame cache
                if len(self._all_ascii_frames) > 900:
                    with self.lock:
                        prune_to = max(0, min(idx, len(self._all_ascii_frames) - 600))
                        if prune_to > 0:
                            self._all_ascii_frames[:prune_to] = [None] * prune_to
                            self.frames_converted = prune_to
        finally:
            self._finish()

    def _show_frame(self, lines, idx, status=None):
        if self._term_refresh <= 0:
            self._term_cols, self._term_lines = shutil.get_terminal_size((80, 24))
            self._term_refresh = 30
        else:
            self._term_refresh -= 1
        cols, lns = self._term_cols, self._term_lines
        fh = len(lines)
        fw = _visible_length(lines[0]) if fh > 0 else 0

        pad_top = max((lns - fh - 2) // 2, 0)
        pad_left = max((cols - fw - 2) // 2, 0)
        margin = " " * pad_left

        out = ["\033[H"]
        out.append("\n" * pad_top)

        # Build cached borders — only recompute on width change
        if getattr(self, '_border_cache_cols', None) != cols:
            self._border_cache_cols = cols
            self._top_border_cache = f"\033[90m┌{'─' * (cols - 2)}┐\033[0m"
            self._bot_border_cache = f"\033[90m└{'─' * (cols - 2)}┘\033[0m"
        out.append(self._top_border_cache + "\n")

        for line in lines:
            out.append(f"\033[90m│\033[0m{margin}{line}\033[90m│\033[0m\n")

        out.append(self._bot_border_cache + "\n")

        mode_label = "VIDEO" if self.watching_video else "COLOUR"
        status_label = f" [{status}]" if status else ""
        sp_label = f" [{self.speed:.2f}x]" if self.speed != 1.0 else ""
        info_str = f" tui-yt | Mode: {mode_label}{sp_label}{status_label} | Frame {idx+1}/{self.total_frames} | Space: pause, Q: quit, Arrows: seek "
        info_str = info_str[:cols-4]
        out.append(f"\033[90m {info_str}\033[0m\033[J")
        print("".join(out), end="", flush=True)

    def _start_audio(self):
        if self.no_audio or not self.audio_path:
            return
        if not self.audio_player:
            return
        self.audio_process = play_audio(self.audio_path, self.audio_player, speed=self.speed)

    def _finish(self):
        self.stopped = True
        stop_audio(self.audio_process)
        self.controls.stop()
        if self.video_cap:
            self.video_cap.release()
            self.video_cap = None
        if self._owned_video_path and os.path.isfile(self._owned_video_path):
            try:
                os.remove(self._owned_video_path)
            except Exception:
                pass
        if self._owned_video_dir and os.path.isdir(self._owned_video_dir):
            try:
                os.rmdir(self._owned_video_dir)
            except Exception:
                pass
        cursor.show()

    def run(self):
        if not self.load_video():
            return False

        self.audio_player = detect_player()
        if not self.audio_player and not self.no_audio:
            print("\033[93mWarning: No audio player found (tried ffplay, mpv, afplay)."
                  " Install ffmpeg (provides ffplay) or mpv for audio.\033[0m")
        self.controls.start()
        self._start_processing_threads(start_frame=0)

        if self.video_cap:
            w = int(self.video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w > 0 and h > 0:
                self._render_size(w, h)

        self._play_loop()
        return True
