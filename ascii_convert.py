"""
ASCII conversion module for tui-yt.
Converts PIL images and video frames to ASCII art with 24-bit true-color ANSI escape sequences.
"""

import numpy as np
from PIL import ImageEnhance
from sty import fg

_FS_LUT_CACHE: dict[tuple, np.ndarray] = {}

# Static Bayer 4x4 matrix for ordered dithering
BAYER_4X4 = np.array([
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5]
], dtype=np.float32)
BAYER_NORM = (BAYER_4X4 / 16.0) - 0.5

# Character sets for colour mode (foreground-coloured characters on default bg)
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


def convert_frame(image, charset="standard", video_mode=False,
                  contrast=1.0, brightness=1.0, dither="none"):
    """
    Convert a PIL Image or numpy RGB array to a list of ASCII strings with ANSI colour codes.
    """
    if isinstance(image, np.ndarray):
        pixels = image
        if contrast != 1.0 or brightness != 1.0:
            pixels = pixels.astype(np.float32)
            if contrast != 1.0:
                pixels = 128.0 + (pixels - 128.0) * contrast
            if brightness != 1.0:
                pixels = pixels + (brightness - 1.0) * 128.0
            pixels = np.clip(pixels, 0, 255).astype(np.uint8)
    else:
        pil_image = image
        if contrast != 1.0:
            pil_image = ImageEnhance.Contrast(pil_image).enhance(contrast)
        if brightness != 1.0:
            pil_image = ImageEnhance.Brightness(pil_image).enhance(brightness)
        pixels = np.array(pil_image, dtype=np.uint8)

    height, width = pixels.shape[:2]

    r_chan = pixels[:, :, 0].astype(np.uint32)
    g_chan = pixels[:, :, 1].astype(np.uint32)
    b_chan = pixels[:, :, 2].astype(np.uint32)
    brightness_arr = (r_chan * 299 + g_chan * 587 + b_chan * 114) // 1000

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
            lut_key = ("video",)
        else:
            charset_name = charset if charset in CHARSETS else "standard"
            thresholds = sorted(CHARSETS[charset_name].keys())
            lut_key = ("colour", charset_name)

        cached = _FS_LUT_CACHE.get(lut_key)
        if cached is not None:
            closest_threshold_lut = cached
        else:
            closest_threshold_lut = np.array([
                min(thresholds, key=lambda t: abs(i - t))
                for i in range(256)
            ], dtype=np.float32)
            _FS_LUT_CACHE[lut_key] = closest_threshold_lut

        padded = np.zeros((height + 1, width + 2), dtype=np.float32)
        padded[:height, 1:width+1] = brightness_arr.astype(np.float32)

        lut = closest_threshold_lut
        for y in range(height):
            row = padded[y]
            nrow = padded[y + 1]
            for x in range(1, width + 1):
                v = row[x]
                if v <= 0.0:
                    idx = 0
                elif v >= 255.0:
                    idx = 255
                else:
                    idx = int(v + 0.5)
                closest = lut[idx]
                err = v - closest
                row[x] = closest
                row[x + 1]  += err * 0.4375
                nrow[x - 1] += err * 0.1875
                nrow[x]     += err * 0.3125
                nrow[x + 1] += err * 0.0625

        brightness_arr = padded[:height, 1:width+1].astype(np.uint8)

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
