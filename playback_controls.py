"""
Interactive keyboard controls for tui-yt video playback.
Provides pause (Space), quit (Q), seek (Left/Right arrows), and speed control (>/<).
Uses pynput for cross-platform keyboard listening.
"""

from __future__ import print_function
from threading import Lock

try:
    from pynput import keyboard
except ImportError:
    import sys
    print("Missing dependency: pynput. Install with: uv pip install pynput")
    sys.exit(1)


class PlaybackControls:
    """
    Manages interactive playback state.

    Thread-safe: called from pynput's listener thread and the
    playback loop thread simultaneously.
    """

    SEEK_STEP_SECONDS = 5  # seconds to seek per arrow press

    def __init__(self):
        self._paused = False
        self._seek_offset = 0       # frames to skip (positive = forward)
        self._speed_delta = 0.0     # accumulated speed adjustment
        self._speed_reset = False   # flag to reset speed to 1.0
        self._quit_flag = False
        self._lock = Lock()
        self._listener = None

    def on_press(self, key):
        """Handle a keypress. Registered as pynput callback."""
        with self._lock:
            try:
                k = key.char
            except AttributeError:
                k = key

            if k == " " or k in ("k", "K"):
                self._paused = not self._paused
            elif k in ("q", "Q"):
                self._quit_flag = True
            elif k == keyboard.Key.right or k in ("l", "L"):
                self._seek_offset += self.SEEK_STEP_SECONDS
            elif k == keyboard.Key.left or k in ("j", "J"):
                self._seek_offset -= self.SEEK_STEP_SECONDS
            elif k in (">", ".", "]", "+"):
                self._speed_delta += 0.25
            elif k in ("<", ",", "[", "-"):
                self._speed_delta -= 0.25
            elif k in ("0", "r", "R"):
                self._speed_reset = True

    def start(self):
        """Begin listening for keyboard input."""
        try:
            self._listener = keyboard.Listener(on_press=self.on_press)
            self._listener.start()
        except Exception as e:
            print(f"\033[93mWarning: Could not start keyboard listener. "
                  f"Keyboard controls will be disabled. (Error: {e})\033[0m")
            self._listener = None

    def stop(self):
        """Stop the keyboard listener."""
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass

    def is_paused(self):
        with self._lock:
            return self._paused

    def should_quit(self):
        with self._lock:
            return self._quit_flag

    def consume_seek(self):
        """Return the accumulated seek offset (in seconds) and reset to 0."""
        with self._lock:
            offset = self._seek_offset
            self._seek_offset = 0
        return offset

    def consume_speed_change(self):
        """Return (delta, reset_flag) and reset accumulated values."""
        with self._lock:
            delta = self._speed_delta
            reset = self._speed_reset
            self._speed_delta = 0.0
            self._speed_reset = False
        return delta, reset
