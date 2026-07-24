"""
Focused tests for ASCIIVideoPlayer.
"""
import io
import os
import tempfile
import time
import unittest
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


if __name__ == "__main__":
    t0 = time.monotonic()
    unittest.main(verbosity=2, exit=False)
    print(f"\nTotal: {time.monotonic() - t0:.2f}s")
