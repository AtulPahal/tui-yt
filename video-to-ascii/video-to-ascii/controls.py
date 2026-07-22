"""
Interactive keyboard controls for video-to-ascii playback.
Provides pause (Space), quit (Q), and seek (Left/Right arrows).
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
        self._quit_flag = False
        self._lock = Lock()
        self._listener = None

    # --- pynput callback (called from listener thread) ---

    def on_press(self, key):
        """Handle a keypress.  Registered as pynput callback."""
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

    # --- lifecycle ---

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

    # --- thread-safe state queries ---

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
