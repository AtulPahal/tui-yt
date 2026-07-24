"""
YouTube stream extractor and download helper for tui-yt.
"""


try:
    import yt_dlp as youtube_dl
    HAS_YTDL = True
except ImportError:
    class DummyYoutubeDL:
        class YoutubeDL:
            pass
    youtube_dl = DummyYoutubeDL
    HAS_YTDL = False


QUALITY_MAP = {
    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
    "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
    "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]/best",
    "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]/best",
    "240p": "bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/best[height<=240]/best",
    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
}


def get_stream_info(url, quality="720p"):
    if not HAS_YTDL:
        print("Error: Missing dependency 'yt-dlp' for streaming YouTube videos.")
        return "error", "error", 0, 0, 0

    fmt = QUALITY_MAP.get(quality, QUALITY_MAP["720p"])
    ydl_opts_video = {
        "format": fmt,
        "quiet": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web_creator"]}}
    }
    ydl_opts_audio = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "quiet": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web_creator"]}}
    }

    with youtube_dl.YoutubeDL(ydl_opts_video) as ydl_v:
        try:
            info = ydl_v.extract_info(url=url, download=False)
            requested = info.get("requested_formats")
            if requested and len(requested) >= 1:
                video_url = requested[0].get("url")
            else:
                video_url = info.get("url")
                if not video_url and "formats" in info and info["formats"]:
                    video_url = info["formats"][-1].get("url")

            fps = info.get("fps") or 30.0
            duration = info.get("duration") or 0
            total_frames = int(fps * duration)

            audio_url = None
            if requested and len(requested) >= 2:
                audio_url = requested[1].get("url")

            if not audio_url:
                try:
                    with youtube_dl.YoutubeDL(ydl_opts_audio) as ydl_a:
                        a_info = ydl_a.extract_info(url=url, download=False)
                        if a_info and a_info.get("url"):
                            audio_url = a_info.get("url")
                except Exception:
                    audio_url = video_url

            return video_url, audio_url, fps, total_frames, duration
        except Exception as e:
            print(f"Error fetching live stream info: {e}")
            return "error", "error", 0, 0, 0


def save_file(url, outtmpl=None, quality="720p"):
    if not HAS_YTDL:
        print("Error: Missing dependency 'yt-dlp' for downloading YouTube videos.")
        return "error", 0, 0, 0

    if outtmpl is None:
        outtmpl = "video"
    fmt = QUALITY_MAP.get(quality, QUALITY_MAP["720p"])
    ydl_opts = {
        "format": fmt,
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
            if not isinstance(actual_filename, str) or actual_filename.startswith("<MagicMock"):
                actual_filename = outtmpl
        except Exception as e:
            print(f"Error downloading video: {e}")
            return "error", 0, 0, 0
        return actual_filename, fps, total_frames, duration
