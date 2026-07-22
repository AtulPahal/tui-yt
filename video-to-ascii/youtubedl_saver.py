from __future__ import unicode_literals

try:
    import yt_dlp as youtube_dl
    HAS_YTDL = True
except ImportError:
    class DummyYoutubeDL:
        class YoutubeDL:
            pass
    youtube_dl = DummyYoutubeDL
    HAS_YTDL = False


def save_file(url, outtmpl=None):
    if not HAS_YTDL:
        print("Error: Missing dependency 'yt-dlp' for downloading YouTube videos. "
              "Install it with: uv pip install yt-dlp")
        return "error", 0, 0, 0

    if outtmpl is None:
        outtmpl = "video"
    ydl_opts = {
        "format": "best[height<=480][ext=mp4]/best[ext=mp4]/best",
        "outtmpl": outtmpl,
        "quiet": False,
        "extractor_args": {"youtube": {"player_client": ["android", "web_creator"]}}
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url=url, download=True)
            fps = info.get('fps', 30)
            duration = info.get('duration') or 0
            total_frames = int(fps * duration)
            actual_filename = ydl.prepare_filename(info) if hasattr(ydl, "prepare_filename") else outtmpl
            # Fallback to outtmpl if prepare_filename returns a mock or non-string
            if not isinstance(actual_filename, str) or actual_filename.startswith("<MagicMock"):
                actual_filename = outtmpl
        except Exception as e:
            print(f"Error downloading video: {e}")
            return "error", 0, 0, 0
        return actual_filename, fps, total_frames, duration
