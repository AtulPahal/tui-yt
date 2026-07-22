"""
ASCII conversion module for video-to-ascii.
Converts PIL images to ASCII art with ANSI color codes.

Usage:
    from ascii_convert import convert_frame, list_charsets

    lines = convert_frame(pil_image, charset="standard", video_mode=False)
    for row in lines:
        print(row)
"""

from __future__ import print_function
import numpy as np
from PIL import ImageEnhance

from sty import fg, bg

# Static Bayer 4x4 matrix for ordered dithering
BAYER_4X4 = np.array([
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5]
], dtype=np.float32)
BAYER_NORM = (BAYER_4X4 / 16.0) - 0.5
# Character sets for colour mode (foreground-coloured characters on default bg)
# Keys are brightness thresholds, values are the character(s) to draw.
CHARSETS = {
    "standard": {
        25: "  ",
        50: "..",
        75: "::",
        100: "--",
        125: "==",
        150: "++",
        175: "**",
        200: "##",
        225: "%%",
        255: "@@",
    },
    "compact": {
        51: "  ",
        102: "..",
        153: "--",
        204: "**",
        255: "@@",
    },
    "minimal": {
        64: ".",
        128: "-",
        192: "+",
        255: "#",
    },
}

# Character set for "video" mode (background-coloured blocks + fixed foreground).
# Each entry is (display_chars, foreground_style).
VIDEO_CHARSET = {
    50: ("  ", fg.white),
    70: ("..", fg.li_grey),
    130: ("--", fg.li_grey),
    230: ("~~", fg.grey),
    240: ("++", fg.da_black),
    255: ("  ", fg.black),
}

CHARSET_DESCRIPTIONS = {
    "standard": "10-level density ramp (default, matches original colour mode)",
    "compact": "5-level compact ramp",
    "minimal": "4-level single-character ramp",
}

# ---------------------------------------------------------------------------
# Precompute Lookup Tables (LUTs) at the module level
# ---------------------------------------------------------------------------

def _precompute_lut(char_map):
    thresholds = sorted(char_map.keys())
    lut = []
    for b in range(256):
        chosen = char_map[thresholds[0]]
        for t in thresholds:
            if b <= t:
                chosen = char_map[t]
                break
        lut.append(chosen)
    return lut

def _precompute_video_lut(video_charset):
    thresholds = sorted(video_charset.keys())
    lut_fg = []
    lut_char = []
    for b in range(256):
        chosen_char, chosen_fg = video_charset[thresholds[0]]
        for t in thresholds:
            if b <= t:
                chosen_char, chosen_fg = video_charset[t]
                break
        lut_fg.append(chosen_fg)
        lut_char.append(chosen_char)
    return lut_fg, lut_char

LUT_STANDARD = _precompute_lut(CHARSETS["standard"])
LUT_COMPACT = _precompute_lut(CHARSETS["compact"])
LUT_MINIMAL = _precompute_lut(CHARSETS["minimal"])
LUT_VIDEO_FG, LUT_VIDEO_CHAR = _precompute_video_lut(VIDEO_CHARSET)

LUTS = {
    "standard": LUT_STANDARD,
    "compact": LUT_COMPACT,
    "minimal": LUT_MINIMAL,
}

def list_charsets():
    """Return dict of {name: description} for available colour-mode charsets."""
    return dict(CHARSET_DESCRIPTIONS)


def convert_frame(pil_image, charset="standard", video_mode=False,
                  contrast=1.0, brightness=1.0, dither="none"):
    """
    Convert a PIL image to a list of ASCII strings with ANSI colour codes.

    Args:
        pil_image: PIL Image object (RGB mode).
        charset: Name of the character set to use (only applies in colour mode).
        video_mode: If True, uses background-coloured blocks (more vibrant,
                    matches the original --video_mode flag). If False, uses
                    foreground-coloured characters on the terminal background.
        contrast: Contrast adjustment factor (1.0 is original).
        brightness: Brightness adjustment factor (1.0 is original).
        dither: Dithering method ("none", "ordered", "floyd").

    Returns:
        list[str]: Each element is one row of ASCII art including ANSI codes.
    """
    # 1. Apply image enhancements if requested
    if contrast != 1.0:
        enhancer = ImageEnhance.Contrast(pil_image)
        pil_image = enhancer.enhance(contrast)
    if brightness != 1.0:
        enhancer = ImageEnhance.Brightness(pil_image)
        pil_image = enhancer.enhance(brightness)

    pixels = np.array(pil_image, dtype=np.uint8)
    height, width = pixels.shape[:2]

    # 2. Standard luminance grayscale formula: (R * 299 + G * 587 + B * 114) // 1000
    # Ensure np.uint32 is used for intermediate sums to prevent overflow.
    r_chan = pixels[:, :, 0].astype(np.uint32)
    g_chan = pixels[:, :, 1].astype(np.uint32)
    b_chan = pixels[:, :, 2].astype(np.uint32)
    brightness_arr = (r_chan * 299 + g_chan * 587 + b_chan * 114) // 1000

    # 3. Dithering
    if dither == "ordered":
        brightness_f = brightness_arr.astype(np.float32)
        tile_y = (height + 3) // 4
        tile_x = (width + 3) // 4
        tiled_bayer = np.tile(BAYER_NORM, (tile_y, tile_x))[:height, :width]
        brightness_f += tiled_bayer * 40.0
        brightness_arr = np.clip(brightness_f, 0.0, 255.0).astype(np.uint8)
    elif dither == "floyd":
        if video_mode:
            thresholds = sorted(VIDEO_CHARSET.keys())
        else:
            charset_name = charset if charset in CHARSETS else "standard"
            thresholds = sorted(CHARSETS[charset_name].keys())

        # Precompute closest threshold mapping
        closest_threshold_lut = np.array([
            min(thresholds, key=lambda t: abs(i - t))
            for i in range(256)
        ], dtype=np.float32)

        # Pad to avoid boundary checks: +1 row at bottom, +1 col at left and right
        padded = np.zeros((height + 1, width + 2), dtype=np.float32)
        padded[:height, 1:width+1] = brightness_arr.astype(np.float32)

        for y in range(height):
            for x in range(1, width + 1):
                v = padded[y, x]
                # Clip input to [0.0, 255.0]
                v_clipped = 0.0 if v < 0.0 else (255.0 if v > 255.0 else v)
                idx = int(v_clipped + 0.5)
                closest = closest_threshold_lut[idx]
                err = v - closest

                padded[y, x] = closest
                # Diffuse error to neighbors
                padded[y, x + 1]     += err * 0.4375    # 7/16
                padded[y + 1, x - 1] += err * 0.1875    # 3/16
                padded[y + 1, x]     += err * 0.3125    # 5/16
                padded[y + 1, x + 1] += err * 0.0625    # 1/16

        brightness_arr = padded[:height, 1:width+1].astype(np.uint8)

    # Convert to Python native lists/tuples for fast traversal inside list comprehensions
    pixels_list = pixels.tolist()
    brightness_list = brightness_arr.tolist()

    if video_mode:
        frame_lines = [
            "".join([
                f"\033[48;2;{p[0]};{p[1]};{p[2]}m{LUT_VIDEO_FG[b]}{LUT_VIDEO_CHAR[b]}"
                for p, b in zip(row_pixels, row_brightness)
            ]) + "\033[39m\033[49m"
            for row_pixels, row_brightness in zip(pixels_list, brightness_list)
        ]
    else:
        lut = LUTS.get(charset, LUTS["standard"])
        frame_lines = [
            "".join([
                f"\033[38;2;{p[0]};{p[1]};{p[2]}m{lut[b]}"
                for p, b in zip(row_pixels, row_brightness)
            ]) + "\033[39m"
            for row_pixels, row_brightness in zip(pixels_list, brightness_list)
        ]

    return frame_lines
