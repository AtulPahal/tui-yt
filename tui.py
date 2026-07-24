#!/usr/bin/env python3
import sys
import os
import io
import time
import re
import asyncio
import threading
import urllib.request
from PIL import Image, ImageEnhance

# Native video_player module

# Handle third-party imports gracefully
try:
    import yt_dlp
except ImportError:
    print("Error: 'yt-dlp' is not installed. Run 'uv pip install yt-dlp'.")
    sys.exit(1)

try:
    from prompt_toolkit import Application
    from prompt_toolkit.application import run_in_terminal
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, VSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.widgets import TextArea, Frame
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.filters import has_focus
    from prompt_toolkit.styles import Style
except ImportError:
    print("Error: 'prompt-toolkit' is not installed. Run 'uv pip install prompt-toolkit'.")
    sys.exit(1)

try:
    from video_player import ASCIIVideoPlayer
    import cursor
except ImportError as e:
    print(f"Error importing internal video_player module: {e}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Module-level YouTube Download Helper (expected by regression test)
# ---------------------------------------------------------------------------
def download_youtube_video(url: str, progress_hook=None) -> str:
    os.makedirs("downloads", exist_ok=True)
    ydl_opts = {
        "outtmpl": "downloads/%(title)s.%(ext)s",
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "quiet": True,
    }
    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename


# ---------------------------------------------------------------------------
# Thumbnail Terminal Renderer (True-Color Half-Blocks)
# ---------------------------------------------------------------------------
def fetch_thumbnail_image(url: str) -> Image.Image:
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as response:
            img_data = response.read()
        return Image.open(io.BytesIO(img_data)).convert("RGB")
    except Exception:
        return None

def render_image_to_ansi(img: Image.Image, max_w: int, max_h: int) -> str:
    if img is None:
        return "No thumbnail preview available."
    try:
        w_orig, h_orig = img.size
        aspect = w_orig / h_orig
        
        # Calculate size keeping correct aspect ratio:
        # Physical aspect ratio = w / (h * 2) = aspect -> h = w / (2 * aspect)
        w = max_w
        h = int(w / (2 * aspect))
        
        if h > max_h:
            h = max_h
            w = int(h * 2 * aspect)
            
        w = max(1, w)
        h = max(1, h)
        
        # Downsample using LANCZOS to avoid aliasing and keep smooth details
        img_resized = img.resize((w, h * 2), Image.Resampling.LANCZOS)
        
        # Apply slight contrast and sharpness enhancements to make details stand out in terminal
        img_resized = ImageEnhance.Sharpness(img_resized).enhance(2.0)
        img_resized = ImageEnhance.Contrast(img_resized).enhance(1.1)
        
        lines = []
        for y in range(0, h * 2, 2):
            line = []
            for x in range(w):
                r1, g1, b1 = img_resized.getpixel((x, y))
                r2, g2, b2 = img_resized.getpixel((x, y + 1)) if y + 1 < h * 2 else (0, 0, 0)
                # Foreground (lower pixel) + Background (upper pixel) + unicode half block (▄)
                line.append(f"\033[38;2;{r2};{g2};{b2}m\033[48;2;{r1};{g1};{b1}m\u2584")
            lines.append("".join(line) + "\033[0m")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to render thumbnail: {e}"

def fetch_and_render_thumbnail(url: str, max_w: int = 40, max_h: int = 12) -> str:
    img = fetch_thumbnail_image(url)
    return render_image_to_ansi(img, max_w, max_h)


# ---------------------------------------------------------------------------
# YouTube Search Helper
# ---------------------------------------------------------------------------
def search_youtube(query: str, max_results: int = 15) -> list[dict]:
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # Emulate search query flat extraction
            res = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            entries = res.get("entries", [])
            search_results = []
            for entry in entries:
                if not entry:
                    continue
                
                # Retrieve thumbnail safely
                thumb_url = None
                if entry.get("thumbnails"):
                    # Use the first thumbnail option
                    thumb_url = entry.get("thumbnails")[0].get("url")
                
                search_results.append({
                    "id": entry.get("id"),
                    "title": entry.get("title") or "No Title",
                    "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                    "duration": entry.get("duration"),
                    "channel": entry.get("uploader") or entry.get("channel", "Unknown"),
                    "thumbnail": thumb_url,
                })
            return search_results
        except Exception as e:
            return []


# ---------------------------------------------------------------------------
# Programmatic Video Playback Function
# ---------------------------------------------------------------------------
class MockArgs:
    def __init__(self, url, video_mode, no_audio, chars_charset, quality="720p"):
        self.vid = url
        self.framerate = 30
        self.buffer = 0.0
        self.video_mode = video_mode
        self.chars = chars_charset
        self.export_html = None
        self.no_audio = no_audio
        self.width = 0
        self.height = 0
        self.speed = 1.0
        self.quality = quality
        self.no_intro = True  # Skip the countdown to play immediately
        self.loop = 0
        self.contrast = 1.0
        self.brightness = 1.0
        self.dither = "none"

def flush_stdin():
    try:
        if sys.platform != "win32":
            import select
            while select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.read(1)
        else:
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getch()
    except Exception:
        pass

def play_video(url: str, video_mode: bool, no_audio: bool, chars_charset: str, quality: str = "720p"):
    args = MockArgs(url, video_mode, no_audio, chars_charset, quality=quality)
    # Hide cursor and run player
    cursor.hide()
    player = ASCIIVideoPlayer(args)
    try:
        player.run()
    except Exception as e:
        print(f"\nError during video playback: {e}")
        time.sleep(2)
    finally:
        # Clean up and restore cursor/screen state
        cursor.show()
        print("\033[2J\033[H", end="", flush=True)  # Clear screen and reset cursor home
        flush_stdin()
# Custom ANSI wrapper that exposes .value (expected by test)
class ThumbnailANSI(ANSI):
    def __init__(self, value):
        super().__init__(value)
        self.value = value


# ---------------------------------------------------------------------------
# YouTube TUI Main Application Class
# ---------------------------------------------------------------------------
class YouTubeTUI:
    def __init__(self):
        self.results = []
        self.selected_idx = 0
        self.video_mode = True
        self.no_audio = False
        self.quality = "720p"
        self.chars_charset = "standard"
        self.status_message = ""
        self.current_thumbnail_ansi = ThumbnailANSI("No video selected.")
        self.thumbnail_cache = {}
        self.is_playing = False
        self.last_playback_end_time = 0.0

        # Custom Styling
        self.style = Style.from_dict({
            "selected": "bg:#00f0ff #000000 bold",
            "status": "fg:#ffaa00 italic",
            "status-label": "bg:#333333 fg:#ffffff bold",
            "header": "fg:#00f0ff bold",
            "footer": "bg:#333333 fg:#00f0ff",
            "instruction": "fg:#666666",
        })

        # Set up Widgets
        self.search_field = TextArea(
            multiline=False,
            prompt="Search YouTube: ",
            focusable=True,
        )
        self.search_field.accept_handler = self.on_search_accept

        self.results_window = Window(
            content=FormattedTextControl(self.get_results_text, focusable=True),
        )

        self.preview_window = Window(
            content=FormattedTextControl(self.get_details_content),
        )
        self.preview_frame = Frame(self.preview_window, title="Preview")

        self.status_bar = Window(
            content=FormattedTextControl(self.get_status_text),
            height=1,
        )

        self.header_window = Window(
            content=FormattedTextControl([
                ("class:header", " === YouTube TUI Video Player ===\n"),
                ("class:instruction", " Use Tab to switch focus. Arrow keys/j/k to navigate results. Enter to play. [d] Download\n")
            ]),
            height=2,
        )

        self.footer_window = Window(
            content=FormattedTextControl([
                ("class:footer", " [v] Mode | [a] Audio | [s] Quality | [d] Download | In-Player: [Space] Pause | [L/R] Seek | [>/<] Speed ")
            ]),
            height=1,
        )

        # Set up Keybindings
        self.kb = KeyBindings()
        self.setup_keybindings()

        # Compile layout structure
        self.root_layout = HSplit([
            self.header_window,
            self.search_field,
            VSplit([
                self.results_window,
                Window(width=1, char="|"),
                self.preview_frame,
            ]),
            self.status_bar,
            self.footer_window,
        ])

        # Build prompt_toolkit Application
        self.app = Application(
            layout=Layout(self.root_layout),
            key_bindings=self.kb,
            style=self.style,
            full_screen=True,
        )

    def setup_keybindings(self):
        # Exit App
        @self.kb.add("escape")
        @self.kb.add("c-c")
        @self.kb.add("c-q")
        def _(event):
            event.app.exit()

        @self.kb.add("q", filter=has_focus(self.results_window))
        def _(event):
            # Guard against trailing 'q' keypresses right after video playback finishes
            if time.time() - self.last_playback_end_time < 1.0:
                return
            event.app.exit()

        # Navigation
        @self.kb.add("down", filter=has_focus(self.results_window))
        @self.kb.add("j", filter=has_focus(self.results_window))
        def _(event):
            if self.results and self.selected_idx < len(self.results) - 1:
                self.selected_idx += 1
                self.update_thumbnail_preview()

        @self.kb.add("up", filter=has_focus(self.results_window))
        @self.kb.add("k", filter=has_focus(self.results_window))
        def _(event):
            if self.results and self.selected_idx > 0:
                self.selected_idx -= 1
                self.update_thumbnail_preview()

        # Play Video
        @self.kb.add("enter", filter=has_focus(self.results_window))
        def _(event):
            if self.is_playing:
                return
            if not self.results or self.selected_idx >= len(self.results):
                return
            url = self.results[self.selected_idx].get("url")
            
            def do_play():
                try:
                    play_video(url, self.video_mode, self.no_audio, self.chars_charset, self.quality)
                finally:
                    self.is_playing = False
                    self.last_playback_end_time = time.time()
                    flush_stdin()
                
            run_in_terminal(do_play)
            self.last_playback_end_time = time.time()
            flush_stdin()

        # Toggle quality
        @self.kb.add("s", filter=has_focus(self.results_window))
        def _(event):
            qualities = ["720p", "1080p", "240p", "360p", "480p", "best"]
            idx = (qualities.index(self.quality) + 1) % len(qualities) if self.quality in qualities else 0
            self.quality = qualities[idx]

        # Toggle video mode
        @self.kb.add("v", filter=has_focus(self.results_window))
        def _(event):
            self.video_mode = not self.video_mode

        # Toggle audio mode
        @self.kb.add("a", filter=has_focus(self.results_window))
        def _(event):
            self.no_audio = not self.no_audio

        # Download Video
        @self.kb.add("d", filter=has_focus(self.results_window))
        def _(event):
            event.app.create_background_task(self.download_selected())

        # Tab Navigation
        @self.kb.add("tab")
        def _(event):
            if event.app.layout.has_focus(self.search_field):
                event.app.layout.focus(self.results_window)
            else:
                event.app.layout.focus(self.search_field)

    async def download_selected(self):
        if not self.results or self.selected_idx >= len(self.results):
            return
        url = self.results[self.selected_idx].get("url")
        self.status_message = "Downloading video..."
        self.app.invalidate()
        
        def run_dl():
            try:
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        self.status_message = f"Downloading... {d.get('_percent_str', '')}"
                        self.app.invalidate()
                    elif d['status'] == 'finished':
                        self.status_message = "Download finished!"
                        self.app.invalidate()
                        
                filename = download_youtube_video(url, progress_hook=progress_hook)
                self.status_message = f"Saved to {filename}"
                self.app.invalidate()
            except Exception as e:
                self.status_message = f"Download error: {e}"
                self.app.invalidate()
                
        await asyncio.to_thread(run_dl)

    def on_search_accept(self, buffer):
        query_str = buffer.text.strip()
        if not query_str:
            return
            
        self.results = []
        self.selected_idx = 0
        self.current_thumbnail_ansi = ThumbnailANSI("Loading preview...")
        self.status_message = "Searching YouTube..."
        self.app.layout.focus(self.results_window)
        self.app.invalidate()
        
        is_url = query_str.startswith("http://") or query_str.startswith("https://")
        
        def bg_search():
            try:
                if is_url:
                    self.status_message = "Fetching video details from URL..."
                    self.app.invalidate()
                    
                    ydl_opts = {
                        "quiet": True,
                        "extract_flat": True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(query_str, download=False)
                        
                        if not info:
                            self.results = []
                        elif "_type" in info and info["_type"] == "playlist":
                            entries = info.get("entries")
                            if entries is None:
                                self.results = []
                            else:
                                search_results = []
                                for entry in entries:
                                    if not entry:
                                        continue
                                    thumb_url = None
                                    if entry.get("thumbnails"):
                                        thumb_url = entry.get("thumbnails")[0].get("url")
                                    search_results.append({
                                        "id": entry.get("id"),
                                        "title": entry.get("title") or "No Title",
                                        "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                                        "duration": entry.get("duration"),
                                        "channel": entry.get("uploader") or entry.get("channel", "Unknown"),
                                        "thumbnail": thumb_url,
                                    })
                                self.results = search_results
                        else:
                            # Single video
                            thumb_url = None
                            if info.get("thumbnails"):
                                thumb_url = info.get("thumbnails")[0].get("url")
                            self.results = [{
                                "id": info.get("id"),
                                "title": info.get("title") or "No Title",
                                "url": f"https://www.youtube.com/watch?v={info.get('id')}",
                                "duration": info.get("duration"),
                                "channel": info.get("uploader") or info.get("channel", "Unknown"),
                                "thumbnail": thumb_url,
                            }]
                    self.status_message = ""
                else:
                    self.status_message = f"Searching YouTube for '{query_str}'..."
                    self.app.invalidate()
                    self.results = search_youtube(query_str)
                    self.status_message = ""
                    
                self.selected_idx = 0
                if self.results:
                    self.update_thumbnail_preview()
                else:
                    self.current_thumbnail_ansi = ThumbnailANSI("No video selected.")
            except Exception as e:
                self.results = []
                self.current_thumbnail_ansi = ThumbnailANSI("No video selected.")
                if is_url:
                    self.status_message = f"Could not fetch details for URL/playlist: {e}"
                else:
                    self.status_message = f"Could not fetch details: {e}"
            self.app.invalidate()
            
        threading.Thread(target=bg_search, daemon=True).start()

    def update_thumbnail_preview(self):
        if not self.results or self.selected_idx >= len(self.results):
            self.current_thumbnail_ansi = ThumbnailANSI("No video selected.")
            return
            
        item = self.results[self.selected_idx]
        video_id = item.get("id")
        if not video_id:
            return
            
        # Dynamically calculate sizes based on terminal window dimensions
        import shutil
        cols, lines = shutil.get_terminal_size()
        max_w = max(20, cols // 2 - 4)
        max_h = max(5, lines - 8)
        
        # Check cache
        if video_id in self.thumbnail_cache:
            img = self.thumbnail_cache[video_id]
            ansi = render_image_to_ansi(img, max_w, max_h)
            self.current_thumbnail_ansi = ThumbnailANSI(ansi)
            return
            
        self.current_thumbnail_ansi = ThumbnailANSI("Loading preview...")
        
        def bg_load():
            thumb_url = item.get("thumbnail")
            img = fetch_thumbnail_image(thumb_url)
            self.thumbnail_cache[video_id] = img
            
            # Update only if selection hasn't changed
            if self.results and self.selected_idx < len(self.results) and self.results[self.selected_idx].get("id") == video_id:
                ansi = render_image_to_ansi(img, max_w, max_h)
                self.current_thumbnail_ansi = ThumbnailANSI(ansi)
                self.app.invalidate()
                
        threading.Thread(target=bg_load, daemon=True).start()

    def get_results_text(self):
        if self.status_message and not self.results:
            return [("class:status", f"\n   {self.status_message}\n")]
        if not self.results:
            return [("", "\n   No results. Type a search query above and press Enter.\n")]
            
        formatted = []
        for i, item in enumerate(self.results):
            dur = item.get("duration")
            if dur:
                minutes = int(dur // 60)
                seconds = int(dur % 60)
                dur_str = f"[{minutes:02d}:{seconds:02d}]"
            else:
                dur_str = "[--:--]"
                
            title = item.get("title", "")
            if len(title) > 40:
                title = title[:37] + "..."
                
            line = f" {'>' if i == self.selected_idx else ' '} {i+1:2d}. {title:<40} {dur_str:<8} - {item.get('channel')}\n"
            
            if i == self.selected_idx:
                formatted.append(("class:selected", line))
            else:
                formatted.append(("", line))
        return formatted

    def get_details_content(self):
        if not self.results or self.selected_idx >= len(self.results):
            return ANSI("Select a video to see details.")
            
        item = self.results[self.selected_idx]
        title = item.get("title", "")
        channel = item.get("channel", "")
        dur = item.get("duration")
        if dur:
            minutes = int(dur // 60)
            seconds = int(dur % 60)
            dur_str = f"{minutes:02d}:{seconds:02d}"
        else:
            dur_str = "Unknown"
            
        details = [
            f"\033[1;36m{title}\033[0m",
            f"\033[1;33mChannel:\033[0m {channel}",
            f"\033[1;33mDuration:\033[0m {dur_str}",
            "",
            self.current_thumbnail_ansi.value
        ]
        return ANSI("\n".join(details))

    def get_status_text(self):
        mode_str = "Blocks" if self.video_mode else "Characters"
        audio_str = "Muted" if self.no_audio else "Play"
        msg = f" | Message: {self.status_message}" if self.status_message else ""
        return [
            ("class:status-label", " [Settings] "),
            ("", f" Video Mode: {mode_str} | Audio: {audio_str} | Quality: {self.quality}{msg}")
        ]


def main():
    tui = YouTubeTUI()
    tui.app.run()


if __name__ == "__main__":
    main()
