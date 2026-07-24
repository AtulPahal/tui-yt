"""
Cross-platform audio playback for video-to-ascii.
Supports macOS (afplay), Linux (ffplay / aplay / paplay), and Windows (ffplay).

Usage:
    from audio import detect_player, play_audio, stop_audio

    player = detect_player()
    if player:
        proc = play_audio("video.mp4", player=player)
        # ... later ...
        stop_audio(proc)
"""

from __future__ import print_function

import os
import subprocess
import sys


def detect_player():
    """
    Detect the best available audio player for the current platform.

    Returns a player name string (suitable for ``play_audio``) or *None*.
    """
    # Prioritize ffplay or mpv on all platforms for seeking and streaming support
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
        # afplay is built into macOS — no dependency needed
        return "afplay"

    # Check *nix players
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


def play_audio(path, player, start_time=0):
    """
    Play an audio file at the given start offset (in seconds) and return the
    ``subprocess.Popen`` handle.

    Returns *None* if playback could not be started.
    """
    is_url = isinstance(path, str) and (path.startswith("http://") or path.startswith("https://"))
    if not path or (not is_url and not os.path.isfile(path)):
        return None

    try:
        # afplay/aplay/paplay cannot stream HTTP URLs directly — use ffplay or mpv for HTTP streams
        # afplay/aplay/paplay cannot stream HTTP URLs directly — use mpv or ffplay for HTTP streams
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        if is_url:
            import shutil
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

