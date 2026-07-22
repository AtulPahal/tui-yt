import sys
import os
import time
import shutil
import cursor
import yt_dlp
import asyncio
import re

# Ensure the sibling module can be imported
sys.path.insert(0, "/Users/atulpahal/github/video-to-ascii")
from video_render import ASCIIVideoPlayer

from prompt_toolkit.application import Application, run_in_terminal
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea, Frame
from prompt_toolkit.layout import Layout
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.formatted_text import ANSI
from ascii_convert import convert_frame

# --- Helper Logic: YouTube Search ---
def search_youtube(query: str, max_results: int = 15) -> list[dict]:
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # Run flat extraction for metadata only
            res = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            entries = res.get("entries") or []
            results = []
            for entry in entries:
                if not entry:
                    continue
                results.append({
                    "id": entry.get("id"),
                    "title": entry.get("title"),
                    "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                    "duration": entry.get("duration"),
                    "channel": entry.get("uploader") or entry.get("channel", "Unknown"),
                    "thumbnail": entry.get("thumbnail") or (f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg" if entry.get('id') else None),
                })
            return results
        except Exception as e:
            return []

YOUTUBE_URL_REGEX = re.compile(
    r'^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/.+$'
)

def fetch_youtube_video(url: str) -> list[dict]:
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            res = ydl.extract_info(url, download=False)
            if not res:
                return []
            
            if res.get("_type") == "playlist":
                entries = res.get("entries") or []
                results = []
                for entry in entries:
                    if not entry:
                        continue
                    results.append({
                        "id": entry.get("id"),
                        "title": entry.get("title"),
                        "url": f"https://www.youtube.com/watch?v={entry.get('id')}" if entry.get('id') else entry.get('url'),
                        "duration": entry.get("duration"),
                        "channel": entry.get("uploader") or entry.get("channel") or res.get("title") or "Unknown",
                        "thumbnail": entry.get("thumbnail") or (f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg" if entry.get('id') else None),
                    })
                return results
            
            return [{
                "id": res.get("id"),
                "title": res.get("title"),
                "url": f"https://www.youtube.com/watch?v={res.get('id')}",
                "duration": res.get("duration"),
                "channel": res.get("uploader") or res.get("channel", "Unknown"),
                "thumbnail": res.get("thumbnail") or f"https://i.ytimg.com/vi/{res.get('id')}/hqdefault.jpg",
            }]
        except Exception as e:
            return []

def download_youtube_video(url: str, progress_hook=None) -> str:
    outtmpl = os.path.join("downloads", "%(title)s [%(id)s].%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "format": "bestvideo+bestaudio/best",
        "quiet": True,
        "progress_hooks": [progress_hook] if progress_hook else [],
    }
    os.makedirs("downloads", exist_ok=True)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return outtmpl

# --- Helper Logic: Video Playback ---
class MockArgs:
    def __init__(self, url, video_mode, no_audio, chars_charset, format_height=480):
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
        self.no_intro = True  # Skip the countdown to play immediately
        self.loop = 0
        self.contrast = 1.0
        self.brightness = 1.0
        self.dither = "none"
        self.format_height = format_height

def flush_input():
    try:
        import termios
        if sys.stdin.isatty():
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    except ImportError:
        pass

def play_video(url: str, video_mode: bool, no_audio: bool, chars_charset: str, format_height: int = 480):
    args = MockArgs(url, video_mode, no_audio, chars_charset, format_height)
    
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
        flush_input()

# --- TUI Logic: Formatted Text Control for Search Results ---
class ResultsControl(FormattedTextControl):
    def __init__(self, tui):
        self.tui = tui
        super().__init__(self._get_formatted_text, focusable=True)

    def _get_formatted_text(self):
        if not self.tui.results:
            return [("class:no-results", " No results found. Enter a query in the search box to begin.")]
        self.tui._refresh_preview_dims()
        
        formatted = []
        is_results_focused = self.tui.app.layout.has_focus(self.tui.results_window) if hasattr(self.tui, "app") else False
        
        for idx, item in enumerate(self.tui.results):
            selected = (idx == self.tui.selected_idx)
            
            if selected:
                style = "class:selected-row" if is_results_focused else "class:selected-row-unfocused"
                prefix = " > "
            else:
                style = "class:row"
                prefix = "   "
            
            title = item.get("title") or "Unknown Title"
            channel = item.get("channel") or "Unknown Channel"
            duration = item.get("duration")
            
            # Truncate title to fit within the results pane (VSplit with thumbnail sidebar)
            prefix_len = len(prefix)
            dur_str_placeholder = "[--:--]"
            overhead = prefix_len + len(dur_str_placeholder) + 2 + len(f" (by {channel})") + 1
            terminal_w = shutil.get_terminal_size().columns
            pw = self.tui.preview_window.width
            pw_val = getattr(pw, 'preferred', None) or 46
            avail_width = terminal_w - pw_val - 4  # 2 for preview frame + 2 for results frame borders
            title_max = max(4, avail_width - overhead)
            if len(title) > title_max:
                title = title[:title_max] + ".."
            
            # Format duration as mm:ss
            if duration:
                try:
                    mins = int(duration) // 60
                    secs = int(duration) % 60
                    dur_str = f"[{mins:02d}:{secs:02d}]"
                except Exception:
                    dur_str = f"[{duration}s]"
            else:
                dur_str = "[--:--]"
            
            line = f"{prefix}{dur_str}  {title} (by {channel})\n"
            formatted.append((style, line))
        return formatted

# --- TUI Logic: Application Container ---
class YouTubeTUI:
    def __init__(self):
        self.results = []
        self.selected_idx = 0
        self.video_mode = True
        self.no_audio = False
        self.chars_charset = "standard"
        self.status_message = "Ready. Type a query above and press Enter to search."
        self.quality = 480
        self.quality_options = [144, 240, 360, 480, 720, 1080]
        self.is_playing = False
        self.current_thumbnail_ansi = ANSI("No video selected.")
        self.current_fetch_task = None
        
        # Build UI components
        self.search_field = TextArea(
            multiline=False,
            prompt="Search YouTube: ",
            accept_handler=self.on_search_accept
        )
        
        self.results_control = ResultsControl(self)
        self.results_window = Window(
            content=self.results_control,
            right_margins=[ScrollbarMargin(display_arrows=True)],
            style="class:results-window"
        )
        
        self.results_frame = Frame(
            self.results_window,
            title="Search Results"
        )
        
        self.preview_window = Window(
            content=FormattedTextControl(lambda: self.current_thumbnail_ansi),
            style="class:preview-window"
        )
        
        self.preview_frame = Frame(
            self.preview_window,
            title="Thumbnail Preview"
        )
        
        self.header = Window(
            content=FormattedTextControl(
                lambda: [("class:header", "══ YouTube TUI Video Player ══")]
            ),
            height=1,
            style="class:header-bg"
        )
        
        self.status_bar = Window(
            content=FormattedTextControl(self.get_status_text),
            height=1,
            style="class:status-bg"
        )
        
        self.footer = Window(
            content=FormattedTextControl(
                lambda: [("class:footer", " [Tab] Focus | [v] Video | [a] Audio | [r] Quality | [Enter] Play | [d] Download | [Esc/q] Exit")]
            ),
            height=1,
            style="class:footer-bg"
        )
        
        self.root_container = HSplit([
            self.header,
            Frame(self.search_field, title="Search Query"),
            VSplit([
                self.results_frame,
                self.preview_frame
            ]),
            self.status_bar,
            self.footer
        ])
        
        self.layout = Layout(self.root_container, focused_element=self.search_field)
        self.kb = KeyBindings()
        self.setup_keybindings()
        
        self.style = Style.from_dict({
            "header-bg": "bg:#d00000 #ffffff bold",
            "header": "#ffffff",
            "status-bg": "bg:#333333 #ffffff",
            "footer-bg": "bg:#d00000 #ffffff",
            "footer": "#ffffff",
            "selected-row": "bg:#d00000 #ffffff bold",
            "selected-row-unfocused": "bg:#555555 #cccccc",
            "row": "#cccccc",
            "no-results": "#888888 italic",
        })
        
        self.app = Application(
            layout=self.layout,
            key_bindings=self.kb,
            style=self.style,
            full_screen=True
        )
        self._refresh_preview_dims()

    def _refresh_preview_dims(self):
        """Recalculate preview window dimensions to match terminal size."""
        from prompt_toolkit.layout.dimension import Dimension
        term = shutil.get_terminal_size()
        w = max(25, min(55, term.columns // 4))
        h = max(6, min(20, term.lines // 4))
        self.preview_window.width = Dimension(preferred=w, min=w)
        self.preview_window.height = Dimension(preferred=h, min=h)

    def get_status_text(self):
        v_mode = "ON (Coloured Blocks)" if self.video_mode else "OFF (ASCII Chars)"
        a_mode = "PLAY" if not self.no_audio else "MUTED"
        return f" Video Mode: {v_mode} | Audio: {a_mode} | Quality: {self.quality}p | Status: {self.status_message}"

    def setup_keybindings(self):
        from prompt_toolkit.filters import has_focus
        
        is_results_focused = has_focus(self.results_window)

        @self.kb.add("c-c")
        def _exit_c_c(event):
            event.app.exit()

        @self.kb.add("q", filter=is_results_focused)
        def _exit(event):
            event.app.exit()

        @self.kb.add("escape", filter=is_results_focused)
        def _esc_exit(event):
            event.app.exit()

        @self.kb.add("tab")
        def _tab(event):
            if event.app.layout.has_focus(self.search_field):
                event.app.layout.focus(self.results_window)
            else:
                event.app.layout.focus(self.search_field)

        @self.kb.add("up", filter=is_results_focused)
        @self.kb.add("k", filter=is_results_focused)
        def _up(event):
            if self.results:
                self.selected_idx = (self.selected_idx - 1) % len(self.results)
                self.update_thumbnail_preview()
                event.app.invalidate()

        @self.kb.add("down", filter=is_results_focused)
        @self.kb.add("j", filter=is_results_focused)
        def _down(event):
            if self.results:
                self.selected_idx = (self.selected_idx + 1) % len(self.results)
                self.update_thumbnail_preview()
                event.app.invalidate()

        @self.kb.add("v", filter=is_results_focused)
        def _toggle_video(event):
            self.video_mode = not self.video_mode
            self.update_thumbnail_preview()
            event.app.invalidate()

        @self.kb.add("a", filter=is_results_focused)
        def _toggle_audio(event):
            self.no_audio = not self.no_audio
            event.app.invalidate()

        @self.kb.add("r", filter=is_results_focused)
        def _cycle_quality(event):
            idx = self.quality_options.index(self.quality)
            self.quality = self.quality_options[(idx + 1) % len(self.quality_options)]
            self.status_message = f"Video quality set to {self.quality}p"
            event.app.invalidate()

        @self.kb.add("enter", filter=is_results_focused)
        def _enter_results(event):
            if self.results:
                if self.is_playing:
                    return
                
                video_info = self.results[self.selected_idx]
                url = video_info["url"]
                
                async def run_play():
                    self.is_playing = True
                    self.status_message = f"Launching playback for: {video_info['title']}..."
                    event.app.invalidate()
                    try:
                        await run_in_terminal(
                            lambda: play_video(
                                url=url,
                                video_mode=self.video_mode,
                                no_audio=self.no_audio,
                                chars_charset=self.chars_charset,
                                format_height=self.quality
                            )
                        )
                    finally:
                        self.is_playing = False
                        self.status_message = "Returned from video playback."
                        event.app.invalidate()
                
                event.app.create_background_task(run_play())

        @self.kb.add("d", filter=is_results_focused)
        def _download_results(event):
            if self.results:
                video_info = self.results[self.selected_idx]
                url = video_info["url"]
                
                async def run_download():
                    self.status_message = f"Starting download for: {video_info['title']}..."
                    event.app.invalidate()
                    
                    def progress_hook(d):
                        if d['status'] == 'downloading':
                            percent = d.get('_percent_str', '0.0%').strip()
                            self.status_message = f"Downloading '{video_info['title']}': {percent}..."
                            if event.app.loop:
                                event.app.loop.call_soon_threadsafe(event.app.invalidate)
                        elif d['status'] == 'finished':
                            self.status_message = f"Finished downloading: {video_info['title']}"
                            if event.app.loop:
                                event.app.loop.call_soon_threadsafe(event.app.invalidate)

                    try:
                        await asyncio.to_thread(
                            lambda: download_youtube_video(url, progress_hook)
                        )
                    except Exception as e:
                        self.status_message = f"Download error: {e}"
                        event.app.invalidate()
                
                event.app.create_background_task(run_download())

    def update_thumbnail_preview(self):
        if not self.results:
            self.current_thumbnail_ansi = ANSI("No results found.")
            return

        video_info = self.results[self.selected_idx]
        url = video_info.get("thumbnail") or f"https://i.ytimg.com/vi/{video_info['id']}/hqdefault.jpg"
        
        if self.current_fetch_task and not self.current_fetch_task.done():
            self.current_fetch_task.cancel()

        async def run_fetch():
            self.current_thumbnail_ansi = ANSI("Loading preview...")
            self.app.invalidate()
            
            try:
                await asyncio.sleep(0.15)
                
                def fetch_and_convert():
                    import urllib.request
                    from PIL import Image
                    import io
                    
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=3) as response:
                        img_bytes = response.read()
                    
                    img = Image.open(io.BytesIO(img_bytes))
                    preferred_w = getattr(self.preview_window.width, 'preferred', 44) or 44
                    preferred_h = getattr(self.preview_window.height, 'preferred', 14) or 14
                    img = img.resize((preferred_w, preferred_h), Image.Resampling.LANCZOS)
                    lines = convert_frame(img, charset=self.chars_charset, video_mode=self.video_mode)
                    return lines
                
                lines = await asyncio.to_thread(fetch_and_convert)
                self.current_thumbnail_ansi = ANSI("\n".join(lines))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.current_thumbnail_ansi = ANSI(f"Preview error:\n{e}")
            
            self.app.invalidate()

        self.current_fetch_task = self.app.create_background_task(run_fetch())

    def on_search_accept(self, buffer):
        query = buffer.text.strip()
        if not query:
            return
        
        async def run_search():
            is_url = bool(YOUTUBE_URL_REGEX.match(query))
            if is_url:
                self.status_message = f"Fetching video details from URL..."
            else:
                self.status_message = f"Searching for '{query}'..."
            
            self.results = []
            self.app.invalidate()
            
            try:
                if is_url:
                    results = await asyncio.to_thread(fetch_youtube_video, query)
                else:
                    results = await asyncio.to_thread(search_youtube, query)
                
                self.results = results
                self.selected_idx = 0
                self.update_thumbnail_preview()
                if results:
                    if is_url:
                        if len(results) > 1:
                            self.status_message = f"Successfully fetched {len(results)} videos from playlist/channel."
                        else:
                            self.status_message = f"Successfully fetched video details."
                    else:
                        self.status_message = f"Found {len(results)} results for '{query}'."
                    self.app.layout.focus(self.results_window)
                else:
                    if is_url:
                        self.status_message = f"Could not fetch details for URL/playlist '{query}'."
                    else:
                        self.status_message = f"No results found for '{query}'."
            except Exception as e:
                self.status_message = f"Error: {e}"
            
            self.app.invalidate()
        
        self.app.create_background_task(run_search())

if __name__ == "__main__":
    tui = YouTubeTUI()
    tui.app.run()
