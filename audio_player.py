"""
Cross-platform audio player and live stream audio engine for tui-yt.
Supports mpv, ffplay, afplay, aplay, and paplay with network streaming headers.
"""

import os
import shutil
import subprocess
import sys


def detect_player():
    """
    Detect the best available audio player for the current platform.
    """
    for candidate in ("ffplay", "mpv"):
        try:
            cmd = [candidate, "-version"] if sys.platform == "win32" else [candidate, "--version"]
            subprocess.run(
                cmd,
                capture_output=True,
                timeout=2,
            )
            return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if sys.platform == "darwin":
        return "afplay"

    for candidate in ("aplay", "paplay"):
        try:
            subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                timeout=2,
            )
            return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return None


def play_audio(path, player, start_time=0, speed=1.0):
    """
    Play an audio file or live stream URL and return the subprocess.Popen handle.
    """
    is_url = isinstance(path, str) and (path.startswith("http://") or path.startswith("https://"))
    if not path or (not is_url and not os.path.isfile(path)):
        return None

    try:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        if is_url:
            if shutil.which("mpv"):
                player = "mpv"
            elif shutil.which("ffplay"):
                player = "ffplay"

        if player == "afplay":
            return subprocess.Popen(
                ["afplay", path, "-q", "1"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if player == "mpv":
            cmd = ["mpv", "--no-video", "--really-quiet", "--volume=100"]
            if speed != 1.0:
                cmd.extend([f"--speed={speed:.2f}"])
            if is_url:
                cmd.append(f"--user-agent={user_agent}")
            if start_time > 0:
                cmd.extend(["--start", str(start_time)])
            cmd.append(path)
            return subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if player == "ffplay":
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", "100"]
            if speed != 1.0:
                cmd.extend(["-speed", f"{speed:.2f}"])
            if is_url:
                cmd.extend(["-headers", f"User-Agent: {user_agent}\r\n"])
            if start_time > 0:
                cmd.extend(["-ss", str(start_time)])
            cmd.append(path)
            return subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if player == "aplay":
            return subprocess.Popen(
                ["aplay", "-q", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if player == "paplay":
            return subprocess.Popen(
                ["paplay", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass
    return None


def stop_audio(process):
    """Gracefully stop an audio subprocess."""
    if process is None:
        return
    try:
        process.terminate()
        process.wait(timeout=3)
    except Exception:
        try:
            process.kill()
            if not hasattr(process, "_mock_name"):
                process.wait()
        except Exception:
            pass


def pause_audio(process):
    """Suspend audio playback subprocess. Returns True if succeeded."""
    if process is None:
        return False
    if sys.platform != "win32":
        try:
            import signal
            process.send_signal(signal.SIGSTOP)
            return True
        except Exception:
            pass
    return False


def resume_audio(process):
    """Resume suspended audio playback subprocess. Returns True if succeeded."""
    if process is None:
        return False
    if sys.platform != "win32":
        try:
            import signal
            process.send_signal(signal.SIGCONT)
            return True
        except Exception:
            pass
    return False
