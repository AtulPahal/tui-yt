import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
import shutil

from PIL import Image

# Import units to test
from colours import Colours
from video_render import VideoNotYoutubeLink, intro
import ascii_convert
import ascii_html
import ascii as ascii_cli
from questionary import ValidationError

class TestColours(unittest.TestCase):
    def test_colours_attributes(self):
        """Verify all Colours class ANSI attributes are defined and valid."""
        attrs = [
            "CYAN", "GREEN", 
            "WARNING", "FAIL", "END", "BOLD", "UNDERLINE"
        ]
        for attr in attrs:
            self.assertTrue(hasattr(Colours, attr), f"Colours lacks attribute: {attr}")
            val = getattr(Colours, attr)
            self.assertIsInstance(val, str, f"Attribute {attr} is not a string")
            self.assertTrue(val.startswith("\033["), f"Attribute {attr} does not start with ANSI escape sequence")
            self.assertTrue(val.endswith("m"), f"Attribute {attr} does not end with 'm'")

class TestErrors(unittest.TestCase):
    def test_video_not_youtube_link(self):
        """Verify custom exception VideoNotYoutubeLink works and carries fields."""
        video_link = "https://example.com/video.mp4"
        message = "Custom error message for youtube"
        
        # Test with custom message
        exc = VideoNotYoutubeLink(video_link, message)
        self.assertEqual(exc.video_link, video_link)
        self.assertEqual(exc.message, message)
        self.assertEqual(str(exc), message)
        
        # Test with default message
        exc_default = VideoNotYoutubeLink(video_link)
        self.assertEqual(exc_default.video_link, video_link)
        self.assertEqual(exc_default.message, "The video entered was not a youtube video")
        self.assertEqual(str(exc_default), "The video entered was not a youtube video")

class TestIntro(unittest.TestCase):
    @patch("video_render.time.sleep")
    @patch("video_render.print")
    def test_intro(self, mock_print, mock_sleep):
        """Verify intro() counts down from 3 to 1, sleeps 1s each time, and returns True."""
        result = intro()
        self.assertTrue(result)
        
        # Assert sleep is called exactly 3 times with 1 second argument
        self.assertEqual(mock_sleep.call_count, 3)
        mock_sleep.assert_has_calls([unittest.mock.call(1)] * 3)
        
        # Inspect printed arguments to ensure countdown from 3 to 1
        printed_args = [call[0][0] for call in mock_print.call_args_list if call[0]]
        
        c3 = f"{Colours.WARNING}{Colours.BOLD}3{Colours.END}"
        c2 = f"{Colours.WARNING}{Colours.BOLD}2{Colours.END}"
        c1 = f"{Colours.WARNING}{Colours.BOLD}1{Colours.END}"
        
        self.assertIn(c3, printed_args)
        self.assertIn(c2, printed_args)
        self.assertIn(c1, printed_args)
        self.assertTrue(printed_args.index(c3) < printed_args.index(c2) < printed_args.index(c1))

class TestAsciiConvert(unittest.TestCase):
    def test_list_charsets(self):
        """Test list_charsets() output structure and keys."""
        charsets = ascii_convert.list_charsets()
        self.assertIsInstance(charsets, dict)
        self.assertIn("standard", charsets)
        self.assertIn("compact", charsets)
        self.assertIn("minimal", charsets)
        for name, desc in charsets.items():
            self.assertIsInstance(name, str)
            self.assertIsInstance(desc, str)

    def test_convert_frame_modes(self):
        """Test convert_frame() with a dummy PIL image in standard, compact, minimal, and video mode."""
        # Create a 4x4 dummy RGB image
        img = Image.new("RGB", (4, 4), color=(128, 128, 128))
        
        # Standard mode
        res_standard = ascii_convert.convert_frame(img, charset="standard", video_mode=False)
        self.assertEqual(len(res_standard), 4)
        for line in res_standard:
            self.assertIsInstance(line, str)
            self.assertIn("\x1b[38;2;128;128;128m", line)
            
        # Compact mode
        res_compact = ascii_convert.convert_frame(img, charset="compact", video_mode=False)
        self.assertEqual(len(res_compact), 4)
        for line in res_compact:
            self.assertIsInstance(line, str)
            self.assertIn("\x1b[38;2;128;128;128m", line)

        # Minimal mode
        res_minimal = ascii_convert.convert_frame(img, charset="minimal", video_mode=False)
        self.assertEqual(len(res_minimal), 4)
        for line in res_minimal:
            self.assertIsInstance(line, str)
            self.assertIn("\x1b[38;2;128;128;128m", line)

        # Video mode
        res_video = ascii_convert.convert_frame(img, video_mode=True)
        self.assertEqual(len(res_video), 4)
        for line in res_video:
            self.assertIsInstance(line, str)
            # Video mode uses background styling
            self.assertIn("\x1b[48;2;128;128;128m", line)

        # Invalid charset fallback (should fallback to standard)
        res_invalid = ascii_convert.convert_frame(img, charset="invalid_charset_name", video_mode=False)
        self.assertEqual(len(res_invalid), 4)
        for line in res_invalid:
            self.assertIn("\x1b[38;2;128;128;128m", line)

    def test_convert_frame_enhancements_and_dither(self):
        """Test convert_frame() with contrast, brightness, and both dither modes."""
        img = Image.new("RGB", (4, 4), color=(128, 128, 128))
        
        # Test contrast adjustment
        res_contrast = ascii_convert.convert_frame(img, contrast=1.5)
        self.assertEqual(len(res_contrast), 4)
        
        # Test brightness adjustment
        res_brightness = ascii_convert.convert_frame(img, brightness=0.8)
        self.assertEqual(len(res_brightness), 4)
        
        # Test both dither modes
        res_ordered = ascii_convert.convert_frame(img, dither="ordered")
        self.assertEqual(len(res_ordered), 4)
        
        res_floyd = ascii_convert.convert_frame(img, dither="floyd")
        self.assertEqual(len(res_floyd), 4)
        
        # Floyd dither with video_mode
        res_floyd_video = ascii_convert.convert_frame(img, video_mode=True, dither="floyd")
        self.assertEqual(len(res_floyd_video), 4)

class TestAsciiHtml(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_ansi_to_html(self):
        """Test _ansi_to_html conversion of various ANSI escape sequences."""
        # Bold
        html_bold = ascii_html._ansi_to_html("\x1b[1mBoldText\x1b[0m")
        self.assertIn("font-weight:bold", html_bold)
        self.assertIn("BoldText", html_bold)
        
        # Underline
        html_underline = ascii_html._ansi_to_html("\x1b[4mUnderlinedText\x1b[0m")
        self.assertIn("text-decoration:underline", html_underline)
        self.assertIn("UnderlinedText", html_underline)
        
        # Standard color (e.g. 31 -> red: 128,0,0)
        html_red = ascii_html._ansi_to_html("\x1b[31mRedText\x1b[0m")
        self.assertIn("color:rgb(128,0,0)", html_red)
        self.assertIn("RedText", html_red)
        
        # Bright color (e.g. 91 -> bright red: 255,85,85)
        html_bright_red = ascii_html._ansi_to_html("\x1b[91mBrightRedText\x1b[0m")
        self.assertIn("color:rgb(255,85,85)", html_bright_red)
        self.assertIn("BrightRedText", html_bright_red)
        
        # 8-bit xterm color foreground (38;5;12 -> blue: 0,0,255)
        html_xterm_fg = ascii_html._ansi_to_html("\x1b[38;5;12mXtermFg\x1b[0m")
        self.assertIn("color:rgb(0,0,255)", html_xterm_fg)
        self.assertIn("XtermFg", html_xterm_fg)
        
        # 8-bit xterm color background (48;5;12 -> blue: 0,0,255)
        html_xterm_bg = ascii_html._ansi_to_html("\x1b[48;5;12mXtermBg\x1b[0m")
        self.assertIn("background:rgb(0,0,255)", html_xterm_bg)
        self.assertIn("XtermBg", html_xterm_bg)
        
        # 24-bit true color foreground (38;2;10;20;30)
        html_true_fg = ascii_html._ansi_to_html("\x1b[38;2;10;20;30mTrueFg\x1b[0m")
        self.assertIn("color:rgb(10,20,30)", html_true_fg)
        self.assertIn("TrueFg", html_true_fg)
        
        # 24-bit true color background (48;2;40;50;60)
        html_true_bg = ascii_html._ansi_to_html("\x1b[48;2;40;50;60mTrueBg\x1b[0m")
        self.assertIn("background:rgb(40,50,60)", html_true_bg)
        self.assertIn("TrueBg", html_true_bg)
        
        # Escape sequence that resets colors (code 39 or 49)
        html_fg_reset = ascii_html._ansi_to_html("\x1b[31mRed\x1b[39mReset\x1b[0m")
        self.assertIn("color:rgb(128,0,0)", html_fg_reset)
        self.assertIn("Red", html_fg_reset)
        self.assertIn("Reset", html_fg_reset)
        
        html_bg_reset = ascii_html._ansi_to_html("\x1b[48;2;40;50;60mBg\x1b[49mReset\x1b[0m")
        self.assertIn("background:rgb(40,50,60)", html_bg_reset)
        self.assertIn("Bg", html_bg_reset)
        self.assertIn("Reset", html_bg_reset)

    def test_write_html(self):
        """Test write_html() creates a valid file with frames and expected HTML structure."""
        frames = [
            "\x1b[31mFrameOne\x1b[0m",
            "\x1b[32mFrameTwo\x1b[0m"
        ]
        fps = 10
        filepath = os.path.join(self.test_dir, "output.html")
        
        res_path = ascii_html.write_html(frames, fps, filepath)
        self.assertEqual(res_path, filepath)
        self.assertTrue(os.path.exists(filepath))
        
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Basic validation of HTML structure
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn('<html lang="en">', content)
        self.assertIn("<head>", content)
        self.assertIn("</head>", content)
        self.assertIn("<body>", content)
        self.assertIn("</body>", content)
        self.assertIn("</html>", content)
        
        # Verify frame divs are written and mapped via _ansi_to_html
        self.assertIn('id="f0"', content)
        self.assertIn('id="f1"', content)
        self.assertIn("FrameOne", content)
        self.assertIn("FrameTwo", content)
        
        # Verify controls/info and JS timer setup
        self.assertIn('id="playBtn"', content)
        self.assertIn('id="frameInfo"', content)
        self.assertIn("const delay = 100;", content) # 1000 / 10 fps = 100ms
        
        # Verify empty frames case
        empty_filepath = os.path.join(self.test_dir, "empty.html")
        ascii_html.write_html([], fps, empty_filepath)
        with open(empty_filepath, "r", encoding="utf-8") as f:
            empty_content = f.read()
        self.assertIn("No frames.", empty_content)
class MockDocument:
    def __init__(self, text):
        self.text = text

class TestAsciiCLI(unittest.TestCase):
    def test_url_validator(self):
        validator = ascii_cli.URLValidator()
        # Valid URL
        validator.validate(MockDocument("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        validator.validate(MockDocument("https://youtu.be/dQw4w9WgXcQ"))
        # Invalid URL
        with self.assertRaises(ValidationError):
            validator.validate(MockDocument("https://google.com"))
        with self.assertRaises(ValidationError):
            validator.validate(MockDocument("not_a_url"))

    def test_file_validator(self):
        validator = ascii_cli.FileValidator()
        # Valid file
        with patch("os.path.isfile", return_value=True):
            validator.validate(MockDocument("video.mp4"))
        # Invalid file
        with patch("os.path.isfile", return_value=False):
            with self.assertRaises(ValidationError):
                validator.validate(MockDocument("missing.mp4"))

    def test_buffer_validator(self):
        validator = ascii_cli.BufferValidator()
        # Valid buffer values
        validator.validate(MockDocument("0"))
        validator.validate(MockDocument("0.5"))
        validator.validate(MockDocument("1"))
        # Invalid values
        with self.assertRaises(ValidationError):
            validator.validate(MockDocument("-0.1"))
        with self.assertRaises(ValidationError):
            validator.validate(MockDocument("1.1"))
        with self.assertRaises(ValidationError):
            validator.validate(MockDocument("not_a_number"))

    def test_positive_float_validator(self):
        validator = ascii_cli.PositiveFloatValidator()
        # Valid positive floats
        validator.validate(MockDocument("0"))
        validator.validate(MockDocument("1.5"))
        # Invalid
        with self.assertRaises(ValidationError):
            validator.validate(MockDocument("-0.1"))
        with self.assertRaises(ValidationError):
            validator.validate(MockDocument("not_a_number"))

    @patch("questionary.select")
    @patch("questionary.text")
    @patch("questionary.confirm")
    def test_build_video_command_custom(self, mock_confirm, mock_text, mock_select):
        # Mock answers for _build_video_command
        # Select choices: 
        # 1. Where is the video? -> Local file
        # 2. Dithering method -> ordered
        mock_select_instances = [MagicMock(), MagicMock()]
        mock_select_instances[0].ask.return_value = "Local file"
        mock_select_instances[1].ask.return_value = "ordered"
        mock_select.side_effect = mock_select_instances

        # Text inputs:
        # 1. Path to local file -> video.mp4
        # 2. Pre-buffer -> 0.2
        # 3. Contrast -> 1.5
        # 4. Brightness -> 0.8
        mock_text_instances = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        mock_text_instances[0].ask.return_value = "video.mp4"
        mock_text_instances[1].ask.return_value = "0.2"
        mock_text_instances[2].ask.return_value = "1.5"
        mock_text_instances[3].ask.return_value = "0.8"
        mock_text.side_effect = mock_text_instances

        # Confirms:
        # 1. Use video mode? -> True
        # 2. Customize advanced settings? -> True
        mock_confirm_instances = [MagicMock(), MagicMock()]
        mock_confirm_instances[0].ask.return_value = True
        mock_confirm_instances[1].ask.return_value = True
        mock_confirm.side_effect = mock_confirm_instances

        cmd = ascii_cli._build_video_command()
        self.assertIn("video.mp4", cmd)
        self.assertIn("--buffer=0.2", cmd)
        self.assertIn("--video-mode", cmd)
        self.assertIn("--dither=ordered", cmd)
        self.assertIn("--contrast=1.5", cmd)
        self.assertIn("--brightness=0.8", cmd)

if __name__ == "__main__":
    unittest.main()
