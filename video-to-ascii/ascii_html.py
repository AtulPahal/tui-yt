"""
Export ANSI-coloured ASCII frames to a self-contained HTML page.
The page preserves colours and includes play/pause/seek controls.

Usage:
    from ascii_html import write_html

    write_html(frames, fps, path)
"""

from __future__ import print_function

import html as html_mod
import re

# Regex to match ANSI escape sequences used by sty
_ANSI_RE = re.compile(r'\x1b\[([\d;]*)m')


def xterm_256_to_rgb(idx):
    """Convert xterm 256-color index to RGB tuple."""
    idx = max(0, min(255, idx))
    if idx < 16:
        colors = [
            (0,0,0), (128,0,0), (0,128,0), (128,128,0), (0,0,128), (128,0,128), (0,128,128), (192,192,192),
            (128,128,128), (255,0,0), (0,255,0), (255,255,0), (0,0,255), (255,0,255), (0,255,255), (255,255,255)
        ]
        return colors[idx]
    elif idx < 232:
        idx -= 16
        r = (idx // 36) * 51
        g = ((idx // 6) % 6) * 51
        b = (idx % 6) * 51
        return r, g, b
    else:
        v = (idx - 232) * 10 + 8
        return v, v, v


def _ansi_to_html(text):
    """
    Convert a string with ANSI colour codes to HTML with inline styles.
    Handles combined foreground and background styling, bold, underline,
    bright ANSI colors, 8-bit xterm colors, and 24-bit true colors.
    """
    parts = []
    pos = 0
    span_open = False
    style_changed = False

    current_fg = None
    current_bg = None
    bold = False
    underline = False

    fg_colors = {
        "30": "0,0,0", "31": "128,0,0", "32": "0,128,0", "33": "128,128,0",
        "34": "0,0,128", "35": "128,0,128", "36": "0,128,128", "37": "192,192,192",
        "90": "128,128,128", "91": "255,85,85", "92": "85,255,85", "93": "255,255,85",
        "94": "85,85,255", "95": "255,85,255", "96": "85,255,255", "97": "255,255,255"
    }

    def compile_span():
        """Compile HTML span with currently active styles."""
        nonlocal span_open
        if span_open:
            parts.append("</span>")
            span_open = False

        styles = []
        if current_fg:
            styles.append(f"color:rgb({current_fg})")
        if current_bg:
            styles.append(f"background:rgb({current_bg})")
        if bold:
            styles.append("font-weight:bold")
        if underline:
            styles.append("text-decoration:underline")

        if styles:
            parts.append(f'<span style="{" ; ".join(styles)}">')
            span_open = True

    for m in _ANSI_RE.finditer(text):
        # Emit text before this escape
        if m.start() > pos:
            chunk = text[pos:m.start()]
            if style_changed:
                compile_span()
                style_changed = False
            parts.append(html_mod.escape(chunk))

        code = m.group(1)
        pos = m.end()

        # Parse code
        if code in ("0", ""):
            current_fg = None
            current_bg = None
            bold = False
            underline = False
            style_changed = True
        elif code == "39":
            current_fg = None
            style_changed = True
        elif code == "49":
            current_bg = None
            style_changed = True
        elif code == "1":
            bold = True
            style_changed = True
        elif code == "4":
            underline = True
            style_changed = True
        elif code in fg_colors:
            current_fg = fg_colors[code]
            style_changed = True
        elif code.startswith("38;2;"):
            try:
                _, _, r, g, b = code.split(";")
                current_fg = f"{r},{g},{b}"
                style_changed = True
            except ValueError:
                pass
        elif code.startswith("48;2;"):
            try:
                _, _, r, g, b = code.split(";")
                current_bg = f"{r},{g},{b}"
                style_changed = True
            except ValueError:
                pass
        elif code.startswith("38;5;"):
            try:
                _, _, idx = code.split(";")
                r, g, b = xterm_256_to_rgb(int(idx))
                current_fg = f"{r},{g},{b}"
                style_changed = True
            except ValueError:
                pass
        elif code.startswith("48;5;"):
            try:
                _, _, idx = code.split(";")
                r, g, b = xterm_256_to_rgb(int(idx))
                current_bg = f"{r},{g},{b}"
                style_changed = True
            except ValueError:
                pass

    # Remaining text
    if pos < len(text):
        chunk = text[pos:]
        if style_changed:
            compile_span()
            style_changed = False
        parts.append(html_mod.escape(chunk))

    if span_open:
        parts.append("</span>")

    return "".join(parts)


def _build_html(frames, fps):
    """Build a complete HTML page from a list of ANSI-coloured frame strings."""
    total = len(frames)
    if total == 0:
        return "<html><body><p>No frames.</p></body></html>"

    frame_divs = []
    for i, ansi_text in enumerate(frames):
        active = " active" if i == 0 else ""
        html_content = _ansi_to_html(ansi_text)
        frame_divs.append(
            f'<pre class="frame{active}" id="f{i}">{html_content}</pre>'
        )

    frames_joined = "\n".join(frame_divs)
    delay_ms = int(1000 / fps) if fps > 0 else 100

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ASCII Video — {total} frames @ {fps}fps</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#000; display:flex; justify-content:center;
       align-items:center; min-height:100vh;
       font-family:"Courier New","Consolas","Liberation Mono",monospace; }}
#player {{ background:#000; padding:20px; border-radius:8px; }}
pre {{ color:#fff; line-height:1.1; font-size:13px; white-space:pre; }}
.frame {{ display:none; }}
.frame.active {{ display:block; }}
#controls {{ text-align:center; margin-top:16px; color:#888;
             font-family:sans-serif; font-size:13px; }}
#controls button {{ background:#333; color:#fff; border:1px solid #555;
                    padding:5px 14px; margin:0 3px; cursor:pointer;
                    border-radius:4px; font-size:13px; }}
#controls button:hover {{ background:#555; }}
#controls button:active {{ background:#777; }}
#controls .info {{ margin-left:10px; }}
</style>
</head>
<body>
<div id="player">
{frames_joined}
<div id="controls">
<button id="playBtn">⏸</button>
<button id="prevBtn">⏮</button>
<button id="nextBtn">⏭</button>
<span class="info" id="frameInfo">1 / {total}</span>
</div>
</div>
<script>
(function() {{
const frames = document.querySelectorAll(".frame");
const total = frames.length;
let current = 0;
let playing = true;
let timer = null;
const delay = {delay_ms};

function showFrame(idx) {{
  frames.forEach((f, i) => f.classList.toggle("active", i === idx));
  document.getElementById("frameInfo").textContent = (idx + 1) + " / " + total;
}}

function play() {{
  if (timer) clearInterval(timer);
  timer = setInterval(function() {{
    if (!playing) return;
    current = (current + 1) % total;
    showFrame(current);
  }}, delay);
}}

document.getElementById("playBtn").onclick = function() {{
  playing = !playing;
  this.textContent = playing ? "⏸" : "▶";
  if (playing) play();
}};

document.getElementById("prevBtn").onclick = function() {{
  current = (current - 1 + total) % total;
  showFrame(current);
}};

document.getElementById("nextBtn").onclick = function() {{
  current = (current + 1) % total;
  showFrame(current);
}};

document.addEventListener("keydown", function(e) {{
  if (e.key === " " || e.key === "k" || e.key === "K") {{ e.preventDefault(); document.getElementById("playBtn").click(); }}
  if (e.key === "ArrowLeft" || e.key === "j" || e.key === "J") {{ document.getElementById("prevBtn").click(); }}
  if (e.key === "ArrowRight" || e.key === "l" || e.key === "L") {{ document.getElementById("nextBtn").click(); }}
}});

showFrame(0);
play();
}})();
</script>
</body>
</html>"""


def write_html(frames, fps, path):
    """Write an HTML page of the ASCII animation to *path*.

    Args:
        frames: list of ANSI-coloured frame strings (one per frame)
        fps: frames per second for playback timing
        path: output file path
    """
    html = _build_html(frames, fps)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
