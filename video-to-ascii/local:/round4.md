# Round 4 — Implementation Contract

## Shared context
- Repo root: ~/github/video-to-ascii/
- Run via: `uv run python3 video_render.py`
- Colours class in colours.py has: HEADER, BLUE, CYAN, GREEN, WARNING, FAIL, END, BOLD, UNDERLINE
- ANSI clear-screen + home: `"\033[2J\033[H"`
- ANSI home (go to top-left): `"\033[H"`
