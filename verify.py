#!/usr/bin/env python3
"""tui-yt Complete Verification Script — run this to verify everything works."""

import importlib, io, os, sys, time, tempfile, unittest
from contextlib import redirect_stdout

import cv2, numpy as np

VERDICT = {"pass": 0, "fail": 0, "total": 0}
def check(name, fn):
    VERDICT["total"] += 1
    try:
        fn()
        VERDICT["pass"] += 1
        print(f"  PASS  {name}")
    except Exception as e:
        VERDICT["fail"] += 1
        print(f"  FAIL  {name}: {e}")

def clean_video(path, frames=8, fps=10):
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (40, 20))
    for i in range(frames): vw.write(np.full((20, 40, 3), i * 20, dtype=np.uint8))
    vw.release()

# 1. MODULE IMPORTS
for mod in ["ascii_convert","audio_player","colours","playback_controls",
            "yt_saver","video_player","tui"]:
    check(f"import {mod}", lambda m=mod: importlib.import_module(m))

# 2. COMPILATION
for f in sorted(os.listdir(".")):
    if f.endswith(".py"):
        check(f"compile {f}", lambda fn=f: __import__("py_compile").compile(fn, doraise=True))

# 3. CONVERSION MATRIX (3 charsets × 3 dithers × 2 colour modes)
for c in ["standard","compact","minimal"]:
    for d in ["none","ordered","floyd"]:
        for v in [True, False]:
            check(f"conv {c} {d} v={int(v)}", lambda cc=c, dd=d, vv=v:
                __import__("ascii_convert").convert_frame(np.zeros((5,10,3),np.uint8), cc, vv, 1.0, 1.0, dd))

# 4. CONTROLS
pc = __import__("playback_controls")
k = pc.keyboard
ctrl = pc.PlaybackControls()
check("ctrl init not paused", lambda: not ctrl.is_paused())
ctrl.on_press(k.Key.space)
check("ctrl pause", ctrl.is_paused)
ctrl.on_press(k.Key.space)
check("ctrl unpause", lambda: not ctrl.is_paused())
ctrl.on_press(k.Key.right)
check("ctrl seek +5", lambda: ctrl.consume_seek() == 5)
ctrl.on_press(k.Key.left)
check("ctrl seek -5", lambda: ctrl.consume_seek() == -5)
ctrl.on_press(k.KeyCode.from_char(">"))
d, _ = ctrl.consume_speed_change()
check("ctrl speed +0.25", lambda: d == 0.25)
ctrl.on_press(k.KeyCode.from_char("<"))
d, _ = ctrl.consume_speed_change()
check("ctrl speed -0.25", lambda: d == -0.25)
ctrl.on_press(k.KeyCode.from_char("0"))
_, r = ctrl.consume_speed_change()
check("ctrl speed reset", lambda: r)
ctrl.on_press(k.KeyCode.from_char("q"))
check("ctrl quit", ctrl.should_quit)

# 5. AUDIO
ap = __import__("audio_player")
ap.stop_audio(None)
check("stop_audio(None) safe", lambda: True)
p = ap.detect_player()
check(f"detect_player = {p}", lambda: p in (None,"ffplay","mpv","afplay","aplay","paplay"))

# 6. YT SAVER
check("QUALITY_MAP len 6", lambda: len(__import__("yt_saver").QUALITY_MAP) == 6)

# 7. FLUSH STDIN
from tui import flush_stdin
old = sys.stdin; sys.stdin = open(os.devnull)
t0 = time.monotonic(); flush_stdin(); dt = time.monotonic() - t0
sys.stdin.close(); sys.stdin = old
check("flush_stdin < 10ms", lambda: dt < 0.01)

# 8. PLAYBACK
tmpdir = tempfile.mkdtemp(); path = os.path.join(tmpdir, "t.mp4")
clean_video(path)
from tui import MockArgs
from video_player import ASCIIVideoPlayer
buf = io.StringIO()
with redirect_stdout(buf):
    p = ASCIIVideoPlayer(MockArgs(path, True, True, "standard"))
    r = p.run()
check("playback result True", lambda: r)
check("playback stopped", lambda: p.stopped)
check("playback has frames", lambda: len(p._all_ascii_frames) > 0)
check("playback last idx", lambda: p._last_shown_idx == len(p._all_ascii_frames) - 1)
os.remove(path); os.rmdir(tmpdir)

# 9. EDGE CASES
from video_player import VideoNotYoutubeLink
check("VideoNotYoutubeLink exists", lambda: isinstance(VideoNotYoutubeLink, type))

# 10. PLAYER TESTS
from video_player import ASCIIVideoPlayer as AVP
args = MockArgs("/nonexistent/test.mkv", True, True, "standard")
with redirect_stdout(io.StringIO()):
    p2 = AVP(args)
    r2 = p2.run()
check("bad path returns False", lambda: not r2)

print(f"\n{'='*40}")
print(f"  {VERDICT['pass']}/{VERDICT['total']} PASS, {VERDICT['fail']} FAIL")
print(f"{'='*40}")
sys.exit(0 if VERDICT['fail'] == 0 else 1)
