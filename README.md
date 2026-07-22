# YouTube TUI (tui-yt)

A terminal-based interface for searching and streaming YouTube videos as ASCII art.

## Features
- **Live Streaming**: Plays videos as they stream, without needing to download the full video file first.
- **ASCII Art Playback**: Renders video frames as colored ASCII art in your terminal.
- **Thumbnail Previews**: Side-by-side view with ASCII thumbnail previews.
- **Quality Selection**: Cycle through resolutions (144p to 1080p) on-the-fly with the `[r]` key.
- **TUI Controls**: Full navigation and playback control.

## Installation
Requires [uv](https://github.com/astral-sh/uv).

1. Clone the repo: 
   ```bash
   git clone git@github.com:AtulPahal/tui-yt.git
   cd tui-yt
   ```
2. Run the application: 
   ```bash
   uv run python tui.py
   ```

## Controls
| Key | Action |
|-----|--------|
| `Tab` | Switch focus |
| `Up/Down` | Navigate results |
| `Enter` | Play selected video |
| `v` | Toggle video mode |
| `a` | Toggle audio |
| `r` | Cycle quality |
| `d` | Download video |
| `Esc/q`| Exit |
