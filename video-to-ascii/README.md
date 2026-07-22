# Video To ASCII

A Python generator that converts YouTube videos or local video files to
coloured ASCII art in your terminal.

## Features

- **YouTube & local files** — paste a URL or point at a local MP4/AVI/etc.
- **HTML export** — `--export-html output.html` saves the ASCII animation as a
  self-contained web page you can share with anyone.
- **Discover charsets** — `--list-charsets` prints available character sets and
  exits.
- **Loop playback** — `--loop` for infinite replay, `--loop N` to repeat N times
- **Zero-disk-I/O pipeline** — uses a thread-safe, bounded, in-memory frame queue
  for fast concurrent processing without writing files to disk.
- **Skip intro** — `--no-intro` bypasses the 3-2-1 countdown
- **Full-screen** — automatically adapts to your terminal size.
- **Cross-platform audio** — macOS (`afplay`), Linux (`ffplay`/`aplay`/`paplay`),
  Windows (`ffplay`).
- **Interactive controls** — **Space** to pause, **Q** to quit,
  **Left/Right arrows** to seek during playback.
- **Real-time progress bar** — shows `[====>.......]` with frame counter
  and elapsed/duration time.
- **Speed control** — `--speed 0.5` for slow-motion, `--speed 2` to double
  the playback rate.
- **Multiple character sets** — `standard`, `compact`, `minimal`.
- **Video mode** — background-coloured blocks for more vibrant output.
- **Smooth playback** — ANSI escape codes prevent flickering.
- **Live screen capture** — render your desktop (or a region) as ASCII in
  real time.

## Installation

```bash
git clone <repo>
cd video-to-ascii
uv venv && uv pip install -r requirements.txt
```

Or with plain pip:

```bash
pip3 install -r requirements.txt
```

## Usage

### Play a YouTube video

```bash
uv run python3 video_render.py "https://youtube.com/watch?v=..."
```

### Play a local video file

```bash
uv run python3 video_render.py /path/to/video.mp4
```

### Loop playback

```bash
# Infinite loop
uv run python3 video_render.py video.mp4 --loop

# Play 3 times
uv run python3 video_render.py video.mp4 --loop 3
```

### Skip countdown

```bash
uv run python3 video_render.py video.mp4 --no-intro
```

### Check version

```bash
uv run python3 video_render.py --version
```

### Interactive CLI

```bash
uv run python3 ascii.py
```

### Options

| Flag | Description |
|---|---|
| `--video-mode` | Use background-coloured blocks (more vibrant) |
| `--chars` | Character set: `standard`, `compact`, `minimal` |
| `--speed` | Playback speed multiplier (e.g. `0.5`, `2.0`) |
| `--no-audio` | Disable audio playback |
| `--buffer` | Pre-buffer fraction (0–1) before starting |
| `--width`, `--height` | Override output size in character cells |
| `--framerate` | Target framerate |
| `--list-charsets` | List available character sets and exit |
| `--export-html FILE` | Save the ASCII animation as a shareable HTML file |
| `--loop` | Loop playback: `--loop` = infinite, `--loop N` = N times |
| `--no-intro` | Skip the 3-2-1 countdown before playback |
| `--version` | Show version number and exit |

### Live screen capture

```bash
uv run python3 live_render.py
```
(Toggle video mode with Right Shift.)

### Interactive controls during playback

| Key | Action |
|---|---|
| **Space / K** | Pause / resume |
| **Q** | Quit |
| **← / J** | Seek backward ~5 seconds |
| **→ / L** | Seek forward ~5 seconds |

## How it works

1. **Video Ingestion:** Video is downloaded (YouTube) or opened (local file) via OpenCV.
2. **Pipelined In-Memory Queue:** The reader thread reads and resizes frames, pushing them into a bounded, thread-safe memory queue (no slow disk I/O or temporary files).
3. **Parallel ASCII Conversion:** Multiple background converter threads pull frames from the queue, converting every pixel to ANSI-coloured ASCII characters concurrently.
4. **ANSI True-Colour Escape Codes:** Characters are coloured matching the original pixel colour (or background-coloured in block video mode).
5. **Smooth Playback:** The playback thread consumes converted frames and prints them at the native framerate using `\033[H` to overwrite the terminal in-place with zero flickering.
6. **Synchronized Audio:** Audio plays via a cross-platform background subprocess synced to the video duration.

## Requirements

- Python 3.9+
- `uv` or `pip` for dependencies
- macOS, Linux, or Windows terminal with true-colour ANSI support

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
