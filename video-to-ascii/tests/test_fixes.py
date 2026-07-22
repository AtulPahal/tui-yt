import unittest
import sys
import subprocess
from ascii_html import xterm_256_to_rgb, _build_html

class TestFixes(unittest.TestCase):
    # Bug #1: VideoNotYoutubeLink exception handling
    def test_video_not_youtube_link_handled(self):
        res = subprocess.run(
            ["uv", "run", "python3", "video_render.py", "https://google.com"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(res.returncode, 1)
        self.assertNotIn("Traceback", res.stderr)
        self.assertIn("Error:", res.stdout)

    # Bug #2: --threads=0 hang prevention
    def test_live_render_threads_zero_handled(self):
        res = subprocess.run(
            ["uv", "run", "python3", "live_render.py", "--threads=0"],
            capture_output=True, text=True, timeout=5
        )
        self.assertEqual(res.returncode, 1)

    # Bug #3: xterm_256_to_rgb clamping
    def test_xterm_256_bounds(self):
        self.assertEqual(xterm_256_to_rgb(-1), (0, 0, 0))
        self.assertEqual(xterm_256_to_rgb(0), (0, 0, 0))
        self.assertEqual(xterm_256_to_rgb(300), (238, 238, 238))
        self.assertEqual(xterm_256_to_rgb(255), (238, 238, 238))

    # Bug #4: _build_html fps=0
    def test_build_html_fps_zero(self):
        html = _build_html(["test_frame"], 0)
        self.assertIn("const delay = 100;", html)

    # Bug #5: ascii.py cancellation check (simplified)
    # Since this is interactive, I'll rely on the existing tests or a mock if needed.
    # The integration tests covered this via the suite run.
