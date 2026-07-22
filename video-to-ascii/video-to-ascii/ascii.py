"""
Interactive CLI launcher for video-to-ascii.
Prompts the user for mode, URL, buffer, and display settings,
then runs the appropriate renderer.
"""

from __future__ import print_function, unicode_literals

import os
import re
import subprocess
import sys

from colours import Colours
try:
    import questionary
    from questionary import Validator, ValidationError
except ImportError:
    print(f"{Colours.FAIL}Missing dependency: questionary. Install with: uv pip install questionary{Colours.END}")
    sys.exit(1)

from ascii_convert import list_charsets

style = questionary.Style([
    ('qmark', 'fg:#00f0ff bold'),       # Neon cyan question mark
    ('question', 'bold'),               # Bold white question text
    ('answer', 'fg:#00ff66 bold'),      # Neon green submitted answer
    ('pointer', 'fg:#00f0ff bold'),     # Cyan pointer
    ('highlighted', 'fg:#00f0ff bold'), # Cyan highlighted selection
    ('instruction', 'fg:#666666'),      # Dim grey instructions
])

def print_banner():
    banner_rows = [
        r" __     ___     _               _____          _                    _ _ ",
        r" \ \   / (_) __| | ___  ___    |_   _|__      / \   ___  ___  _   _(_|_)",
        r"  \ \ / /| |/ _` |/ _ \/ _ \_____| |/ _ \____/ _ \ / __|/ __|| | | | | |",
        r"   \ V / | | (_| |  __/ (_) |____| | (_) |__/ ___ \\__ \ (__ | |_| | | |",
        r"    \_/  |_|\__,_|\___|\___/     |_|\___/  /_/   \_\___/\___| \__,_|_|_|"
    ]
    colors = [
        "\033[96;1m",  # Bright Cyan
        "\033[96m",    # Cyan
        "\033[94;1m",  # Light Blue
        "\033[94m",    # Blue
        "\033[34m",    # Deep Blue
    ]
    for row, color in zip(banner_rows, colors):
        print(f"{color}{row}\033[0m")
    print()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class URLValidator(Validator):
    def validate(self, document):
        text = document.text.strip()
        is_valid = re.match(
            r'^(http(s)?://)?(www\.)?((youtube\.com/watch\?v=)|(youtu\.be/))([a-zA-Z0-9_-]{11})',
            text
        )
        if not is_valid:
            raise ValidationError(
                message="Please enter a valid YouTube URL "
                        "(e.g. https://youtube.com/watch?v=VIDEO_ID)",
                cursor_position=len(document.text),
            )


class FileValidator(Validator):
    def validate(self, document):
        path = document.text.strip()
        if not os.path.isfile(path):
            raise ValidationError(
                message=f"File not found: {path}",
                cursor_position=len(document.text),
            )


class BufferValidator(Validator):
    def validate(self, document):
        try:
            val = float(document.text.strip())
            if not 0 <= val <= 1:
                raise ValidationError(
                    message="Buffer amount must be between 0 and 1",
                    cursor_position=len(document.text),
                )
        except ValueError:
            raise ValidationError(
                message="Buffer amount must be a number between 0 and 1",
                cursor_position=len(document.text),
            )


class PositiveFloatValidator(Validator):
    def validate(self, document):
        try:
            val = float(document.text.strip())
            if val < 0:
                raise ValidationError(
                    message="Value must be a positive number",
                    cursor_position=len(document.text),
                )
        except ValueError:
            raise ValidationError(
                message="Value must be a valid float",
                cursor_position=len(document.text),
            )


# ---------------------------------------------------------------------------
# Build command
# ---------------------------------------------------------------------------

def build_command():
    answers = questionary.select(
        "What do you want to do?",
        choices=[
            "Video — render a YouTube video or local file",
            "Screen — capture and render your screen live (laggy, lower quality)",
        ],
        style=style,
    ).ask()

    if answers is None:
        sys.exit(0)

    if answers.startswith("Video"):
        return _build_video_command()
    else:
        return ["uv", "run", sys.executable, "live_render.py"]


def _build_video_command():
    # Source
    source = questionary.select(
        "Where is the video?",
        choices=["YouTube URL", "Local file"],
        style=style,
    ).ask()
    if source is None:
        sys.exit(0)

    vid_arg = ""
    if source == "YouTube URL":
        url = questionary.text(
            "What's the YouTube URL?",
            validate=URLValidator,
            style=style,
        ).ask()
        if url is None:
            sys.exit(0)
        vid_arg = url.strip()
    else:
        path = questionary.text(
            "Path to the video file:",
            validate=FileValidator,
            style=style,
        ).ask()
        if path is None:
            sys.exit(0)
        vid_arg = path.strip()

    # Buffer
    buffer_val = questionary.text(
        "How much to pre-buffer (0-1, 0 = minimal):",
        validate=BufferValidator,
        default="0",
        style=style,
    ).ask()
    if buffer_val is None:
        sys.exit(0)

    # Video mode
    video_mode = questionary.confirm(
        "Use video mode? (background-coloured blocks, more vibrant)",
        default=False,
        style=style,
    ).ask()
    if video_mode is None:
        sys.exit(0)

    # Character set (only in non-video mode)
    if not video_mode:
        charsets = list_charsets()
        charset = questionary.select(
            "Character set:",
            choices=[f"{k} — {v}" for k, v in charsets.items()],
            default="standard",
            style=style,
        ).ask()
        if charset is None:
            sys.exit(0)
        charset_name = charset.split(" —")[0]
    else:
        charset_name = "standard"  # unused in video mode

    # Advanced quality settings
    customize_advanced = questionary.confirm(
        "Customize advanced quality settings? (dithering, contrast, etc.)",
        default=False,
        style=style,
    ).ask()
    if customize_advanced is None:
        sys.exit(0)

    dither = "none"
    contrast = "1.0"
    brightness = "1.0"

    if customize_advanced:
        dither = questionary.select(
            "Dithering method:",
            choices=["none", "ordered", "floyd"],
            default="none",
            style=style,
        ).ask()
        if dither is None:
            sys.exit(0)

        contrast = questionary.text(
            "Contrast enhancement factor:",
            validate=PositiveFloatValidator,
            default="1.0",
            style=style,
        ).ask()
        if contrast is None:
            sys.exit(0)

        brightness = questionary.text(
            "Brightness enhancement factor:",
            validate=PositiveFloatValidator,
            default="1.0",
            style=style,
        ).ask()
        if brightness is None:
            sys.exit(0)

    cmd_parts = ["uv", "run", sys.executable, "video_render.py", vid_arg]
    cmd_parts.append(f"--buffer={float(buffer_val.strip())}")
    if video_mode:
        cmd_parts.append("--video-mode")
    if charset_name != "standard":
        cmd_parts.append(f"--chars={charset_name}")

    if dither and dither != "none":
        cmd_parts.append(f"--dither={dither}")

    if contrast:
        try:
            contrast_val = float(contrast.strip())
            if contrast_val != 1.0:
                cmd_parts.append(f"--contrast={contrast_val}")
        except (ValueError, AttributeError):
            pass

    if brightness:
        try:
            brightness_val = float(brightness.strip())
            if brightness_val != 1.0:
                cmd_parts.append(f"--brightness={brightness_val}")
        except (ValueError, AttributeError):
            pass

    return cmd_parts


# ---------------------------------------------------------------------------
# Warning prompt
# ---------------------------------------------------------------------------

def show_warning():
    print()
    print("-" * 40)
    print(f"{Colours.FAIL}{Colours.BOLD}PLEASE READ{Colours.END}")
    print(
        "The following program can lag or crash your computer. "
        "It is not designed for all computers. If you experience "
        "any issues with your computer as a result of this program "
        "it is your fault. Only run this program if you know your "
        "PC will handle it. To end the program press Ctrl+C (may "
        "need to press it a couple times)."
    )
    print()
    print(f"{Colours.FAIL}{Colours.BOLD}RUN AT YOUR OWN RISK.{Colours.END}")
    print()
    print(f"{Colours.GREEN}Tip: press Right Shift to toggle video "
          f"mode during playback!{Colours.END}")
    print("-" * 40)
    print()

    agree = questionary.confirm(
        "I have read and agree to the statement above",
        default=False,
        style=style,
    ).ask()

    if not agree:
        print("Cannot run program — you did not agree.")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    try:
        print_banner()
        argv = build_command()
        show_warning()

        print(f"\n{Colours.GREEN}Running: {' '.join(argv)}{Colours.END}\n")
        subprocess.run(argv)

    except KeyboardInterrupt:
        print(f"\n{Colours.FAIL}Cancelled.{Colours.END}")
        sys.exit(0)
    except Exception as e:
        print(f"{Colours.FAIL}Error: {e}{Colours.END}")
        sys.exit(1)

if __name__ == "__main__":
    main()
