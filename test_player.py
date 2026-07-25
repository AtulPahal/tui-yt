"""
Focused tests for ASCIIVideoPlayer.
"""
import io
import os
import tempfile
import time
import unittest
import unittest.mock
from contextlib import redirect_stdout

import cv2
import numpy as np
from tui import MockArgs


def _make_video(path, frames=8, fps=10):
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (40, 20))
    for i in range(frames):
        vw.write(np.full((20, 40, 3), i * 20, dtype=np.uint8))
    vw.release()
    return fps


class TestPlayer(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "vid.mp4")
        self.fps = _make_video(self.path)
        self.buf = io.StringIO()

    def tearDown(self):
        try:
            os.remove(self.path)
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def _play(self, **kw):
        from video_player import ASCIIVideoPlayer
        no_audio = kw.get("no_audio", True)
        args = MockArgs(self.path, True, no_audio, "standard", kw.get("quality", "720p"))
        if "width" in kw:
            args.width = kw["width"]
        if "height" in kw:
            args.height = kw["height"]
        p = ASCIIVideoPlayer(args)
        with redirect_stdout(self.buf):
            t0 = time.monotonic()
            r = p.run()
            dt = time.monotonic() - t0
        return p, r, dt

    def test_basic_playback(self):
        p, r, _ = self._play()
        self.assertTrue(r)
        self.assertTrue(p.stopped)
        self.assertGreater(len(p._all_ascii_frames), 0)

    def test_no_audio_flag(self):
        p, r, _ = self._play(no_audio=True)
        self.assertTrue(r)
        self.assertIsNone(p.audio_process)

    def test_framerate_zero(self):
        p, r, _ = self._play()
        self.assertTrue(r)

    def test_all_frames(self):
        p, r, _ = self._play()
        self.assertTrue(r)
        self.assertGreater(p.frames_converted, 0)

    def test_multiple_runs(self):
        for _ in range(2):
            _make_video(self.path)
            p, r, _ = self._play()
            self.assertTrue(r)
            self.assertTrue(p.stopped)

    def test_bad_path(self):
        from video_player import ASCIIVideoPlayer
        args = MockArgs("/nonexistent/test.mkv", True, True, "standard")
        with redirect_stdout(io.StringIO()):
            p = ASCIIVideoPlayer(args)
            r = p.run()
        self.assertFalse(r)

    def test_video_cap_none(self):
        from video_player import ASCIIVideoPlayer
        args = MockArgs(self.path, True, True, "standard")
        p = ASCIIVideoPlayer(args)
        orig = p.load_video
        def fake_load():
            p.framerate = 10.0
            p.total_frames = 8
            p.duration = 0.8
            p.video_cap = None
            p.audio_path = None
            return True
        p.load_video = fake_load
        with redirect_stdout(io.StringIO()):
            r = p.run()
        p.load_video = orig
        self.assertFalse(r)

    def test_non_video_url(self):
        from video_player import ASCIIVideoPlayer
        args = MockArgs("https://invalid.example/video", True, True, "standard")
        with redirect_stdout(io.StringIO()):
            p = ASCIIVideoPlayer(args)
            r = p.run()
        self.assertFalse(r)


class TestAuditFixes(unittest.TestCase):
    """Regression tests for bugs found in the deep audit."""

    def test_nan_fps_and_frame_count(self):
        # Corrupt containers can report NaN FPS/frame count; must not crash.
        from video_player import ASCIIVideoPlayer
        args = MockArgs("x.mp4", True, True, "standard")
        p = ASCIIVideoPlayer(args)
        with unittest.mock.patch("video_player.os.path.isfile", return_value=True), \
             unittest.mock.patch("video_player.cv2.VideoCapture") as cap_cls:
            cap = cap_cls.return_value
            cap.isOpened.return_value = True
            cap.get.side_effect = lambda prop: float("nan")
            with redirect_stdout(io.StringIO()):
                self.assertTrue(p.load_video())
        self.assertTrue(p.framerate > 0 and p.framerate == p.framerate)
        self.assertEqual(p.total_frames, 0)
        self.assertEqual(p.duration, 0)

    def test_inf_fps_coerced(self):
        from video_player import ASCIIVideoPlayer
        args = MockArgs("x.mp4", True, True, "standard")
        p = ASCIIVideoPlayer(args)
        with unittest.mock.patch("video_player.os.path.isfile", return_value=True), \
             unittest.mock.patch("video_player.cv2.VideoCapture") as cap_cls:
            cap = cap_cls.return_value
            cap.isOpened.return_value = True
            cap.get.side_effect = lambda prop: float("inf")
            with redirect_stdout(io.StringIO()):
                self.assertTrue(p.load_video())
        self.assertEqual(p.framerate, float(args.framerate))
        self.assertEqual(p.total_frames, 0)

    def test_negative_frame_count_clamped(self):
        from video_player import ASCIIVideoPlayer
        import cv2
        args = MockArgs("x.mp4", True, True, "standard")
        p = ASCIIVideoPlayer(args)
        with unittest.mock.patch("video_player.os.path.isfile", return_value=True), \
             unittest.mock.patch("video_player.cv2.VideoCapture") as cap_cls:
            cap = cap_cls.return_value
            cap.isOpened.return_value = True
            cap.get.side_effect = lambda prop: (
                30.0 if prop == cv2.CAP_PROP_FPS else -50.0)
            with redirect_stdout(io.StringIO()):
                self.assertTrue(p.load_video())
        self.assertEqual(p.total_frames, 0)
        self.assertEqual(p.duration, 0)

    def test_render_size_zero_frame(self):
        from video_player import ASCIIVideoPlayer
        args = MockArgs("x.mp4", True, True, "standard")
        p = ASCIIVideoPlayer(args)
        w, h = p._render_size(0, 0)  # must not raise ZeroDivisionError
        self.assertGreaterEqual(w, 1)
        self.assertGreaterEqual(h, 1)

    def test_on_press_char_explosion_survived(self):
        # A key whose .char raises must not kill the pynput listener thread.
        from playback_controls import PlaybackControls
        ctrl = PlaybackControls()

        class WeirdKey:
            @property
            def char(self):
                raise RuntimeError("dead key")

        ctrl.on_press(WeirdKey())  # must not raise
        ctrl.on_press(playback_key_space())
        self.assertTrue(ctrl.is_paused())

    def test_stop_audio_sigstopped_process(self):
        # stop_audio on a SIGSTOPped process must not stall ~3s.
        import signal
        import subprocess
        from audio_player import stop_audio
        proc = subprocess.Popen(["sleep", "60"])
        try:
            proc.send_signal(signal.SIGSTOP)
            t0 = time.monotonic()
            stop_audio(proc)
            dt = time.monotonic() - t0
            self.assertLess(dt, 3.0)
            self.assertIsNotNone(proc.poll())
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_failed_stream_capture_released(self):
        # A failed cv2.VideoCapture(video_url) must be released before fallback.
        from video_player import ASCIIVideoPlayer
        args = MockArgs(
            "https://www.youtube.com/watch?v=2PuFyjAs7JA", True, True, "standard")
        p = ASCIIVideoPlayer(args)
        with unittest.mock.patch("video_player.ydls.get_stream_info",
                                 return_value=("http://x/v", "http://x/a", 30.0, 90, 3.0)), \
             unittest.mock.patch("video_player.ydls.save_file",
                                 return_value=("error", 0, 0, 0)), \
             unittest.mock.patch("video_player.cv2.VideoCapture") as cap_cls:
            cap_cls.return_value.isOpened.return_value = False
            with redirect_stdout(io.StringIO()):
                self.assertFalse(p.load_video())
            cap_cls.return_value.release.assert_called()

    def test_ffplay_atempo_chain_for_slow_speeds(self):
        # ffmpeg's atempo accepts [0.5, 100]; speed 0.25 must chain filters.
        from unittest import mock as _mock
        import audio_player
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "a.mp3")
        open(path, "w").close()
        try:
            with _mock.patch("subprocess.Popen") as pop:
                audio_player.play_audio(path, "ffplay", speed=0.25)
                cmd = pop.call_args[0][0]
                self.assertEqual(cmd[cmd.index("-af") + 1],
                                 "atempo=0.5,atempo=0.50")
            with _mock.patch("subprocess.Popen") as pop:
                audio_player.play_audio(path, "ffplay", speed=0.75)
                cmd = pop.call_args[0][0]
                self.assertEqual(cmd[cmd.index("-af") + 1], "atempo=0.75")
        finally:
            os.remove(path)
            os.rmdir(tmpdir)

    def test_stale_search_does_not_clobber_newer(self):
        # A slow stale search must not overwrite a newer search's results.
        import threading
        from tui import YouTubeTUI
        t = YouTubeTUI()

        def fake_search(q, max_results=15):
            if q == "slow-query":
                time.sleep(0.4)
                return [{"id": "slow", "title": "S", "url": "u",
                         "duration": 1, "channel": "c"}]
            return [{"id": "fast", "title": "F", "url": "u",
                     "duration": 1, "channel": "c"}]

        class Buf:
            def __init__(self, text):
                self.text = text

        with unittest.mock.patch("tui.search_youtube", side_effect=fake_search):
            t.on_search_accept(Buf("slow-query"))
            t.on_search_accept(Buf("fast-query"))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if t.results and t.results[0]["id"] == "fast":
                    break
                time.sleep(0.05)
            time.sleep(0.6)  # allow stale thread to finish
            self.assertEqual([r["id"] for r in t.results], ["fast"])


def playback_key_space():
    from pynput import keyboard
    return keyboard.Key.space


if __name__ == "__main__":
    t0 = time.monotonic()
    unittest.main(verbosity=2, exit=False)
    print(f"\nTotal: {time.monotonic() - t0:.2f}s")
