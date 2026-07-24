# YouTube TUI (tui-yt)

A terminal-based interface for searching and streaming YouTube videos as ASCII art.

## Features
- **Live Streaming**: Plays videos as they stream, without needing to download the full video file first.
- **ASCII Art Playback**: Renders video frames as colored ASCII art in your terminal.
- **Thumbnail Previews**: Side-by-side view with ASCII thumbnail previews.
- **Quality Selection**: Cycle through resolutions (720p, 1080p, 240p, 360p, 480p, best) on-the-fly with the `[s]` key.
- **TUI Controls**: Full navigation and playback control.

## Installation
Requires [uv](https://github.com/astral-sh/uv) or a Python 3.10+ environment.

### With uv (recommended)
```bash
git clone git@github.com:AtulPahal/tui-yt.git
cd tui-yt
uv run python tui.py
```

### With pip
```bash
git clone git@github.com:AtulPahal/tui-yt.git
cd tui-yt
# Create and activate a virtual environment first
pip install -e .
python tui.py
```

## Controls

### TUI Navigation
| Key | Action |
|-----|--------|
| `Tab` | Switch focus |
| `Up/Down` or `j/k` | Navigate results |
| `Enter` | Play selected video |
| `v` | Toggle video/colour mode |
| `a` | Toggle audio on/off |
| `s` | Cycle quality (720p → 1080p → 240p → 360p → 480p → best) |
| `d` | Download video |
| `Esc` / `Ctrl+C` / `Ctrl+Q` / `q` | Exit |

### In-Player Controls
| Key | Action |
|-----|--------|
| `Space` | Pause / Resume |
| `Left` / `Right` or `j` / `l` | Seek backward / forward (5s) |
| `>` / `.` / `+` / `]` | Speed up (+0.25x) |
| `<` / `,` / `-` / `[` | Slow down (−0.25x) |
| `0` / `r` / `R` | Reset speed to 1.0x |
| `Q` | Quit playback |
