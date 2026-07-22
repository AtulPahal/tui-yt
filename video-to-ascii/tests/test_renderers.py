import unittest
from unittest.mock import patch, MagicMock, ANY
import sys
import os
import shutil
import datetime
import queue
import PIL.Image

# Modules under test
import video_render
import live_render
from pynput import keyboard
import cv2

class TestVideoRender(unittest.TestCase):

    @patch("sys.argv", ["video_render.py", "local_video.mp4", "--framerate", "25", "--buffer", "0.5", "--video-mode"])
    def test_parse_args(self):
        args = video_render.parse_args()
        self.assertEqual(args.vid, "local_video.mp4")
        self.assertEqual(args.framerate, 25)
        self.assertEqual(args.buffer, 0.5)
        self.assertTrue(args.video_mode)
        self.assertEqual(args.chars, "standard")
        self.assertFalse(args.no_audio)
        self.assertEqual(args.width, 0)
        self.assertEqual(args.height, 0)
        self.assertEqual(args.speed, 1.0)
        self.assertEqual(args.loop, 0)

    @patch("sys.argv", ["video_render.py", "local_video.mp4"])
    @patch("os.path.isfile")
    @patch("cv2.VideoCapture")
    def test_load_video_local(self, mock_vc, mock_isfile):
        mock_isfile.return_value = True
        
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 24.0,
            cv2.CAP_PROP_FRAME_COUNT: 240
        }.get(prop, 0.0)
        
        mock_vc.return_value = mock_cap
        
        args = video_render.parse_args()
        player = video_render.ASCIIVideoPlayer(args)
        
        with patch("builtins.print"):
            success = player.load_video()
        self.assertTrue(success)
        self.assertEqual(player.framerate, 24.0)
        self.assertEqual(player.total_frames, 240)
        self.assertEqual(player.duration, 10.0)
        self.assertEqual(player.audio_path, "local_video.mp4")
        mock_cap.release.assert_called_once()

    @patch("sys.argv", ["video_render.py", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
    @patch("os.path.isfile")
    @patch("youtubedl_saver.save_file")
    @patch("tempfile.mkdtemp")
    @patch("cv2.VideoCapture")
    def test_load_video_youtube(self, mock_vc, mock_mkdtemp, mock_save_file, mock_isfile):
        mock_isfile.return_value = False
        mock_mkdtemp.return_value = "/tmp/ytdl_xyz"
        mock_save_file.return_value = ("/tmp/ytdl_xyz/video.mp4", 30.0, 300, 10.0)
        
        mock_cap = MagicMock()
        mock_vc.return_value = mock_cap
        
        args = video_render.parse_args()
        player = video_render.ASCIIVideoPlayer(args)
        
        with patch("builtins.print"):
            success = player.load_video()
        self.assertTrue(success)
        self.assertEqual(player.framerate, 30.0)
        self.assertEqual(player.total_frames, 300)
        self.assertEqual(player.duration, 10.0)
        self.assertEqual(player.audio_path, "/tmp/ytdl_xyz/video.mp4")
        self.assertEqual(player._owned_video_path, "/tmp/ytdl_xyz/video.mp4")

    @patch("sys.argv", ["video_render.py", "video.mp4", "--width", "40", "--height", "20"])
    def test_render_size_override(self):
        args = video_render.parse_args()
        player = video_render.ASCIIVideoPlayer(args)
        w, h = player._render_size(640, 480)
        self.assertEqual(w, 40)
        self.assertEqual(h, 20)

    @patch("sys.argv", ["video_render.py", "video.mp4"])
    @patch("shutil.get_terminal_size")
    def test_render_size_auto(self, mock_get_terminal_size):
        mock_get_terminal_size.return_value = os.terminal_size((80, 24))
        args = video_render.parse_args()
        
        # Test standard mode
        player = video_render.ASCIIVideoPlayer(args)
        player.watching_video = True
        player.charset = "standard"
        w, h = player._render_size(640, 480)
        # max_w = (80 - 2) // 2 = 39
        # max_h = max(24 - 8, 5) = 16
        # scale = min(39/640, 16/480) = min(0.0609, 0.0333) = 0.033333
        # w = 640 * 0.03333 = 21, h = 480 * 0.0333 = 16
        self.assertEqual((w, h), (21, 16))

        # Test caching
        w2, h2 = player._render_size(640, 480)
        self.assertEqual((w2, h2), (21, 16))
        self.assertIn((80, 24, 640, 480, True, "standard"), player._aspect_ratio_cache)

        # Test minimal mode without watching_video
        player2 = video_render.ASCIIVideoPlayer(args)
        player2.watching_video = False
        player2.charset = "minimal"
        w3, h3 = player2._render_size(640, 480)
        # max_w = 80 - 2 = 78
        # max_h = 16
        # scale = min(78/640, 16/480) = min(0.1218, 0.0333) = 0.033333
        # w = 640 * 0.0333 = 21, h = 16
        self.assertEqual((w3, h3), (21, 16))

    @patch("sys.argv", ["video_render.py", "video.mp4"])
    @patch("cv2.resize")
    def test_read_frames(self, mock_resize):
        args = video_render.parse_args()
        player = video_render.ASCIIVideoPlayer(args)
        
        dummy_frame = MagicMock()
        dummy_frame.shape = (480, 640, 3)
        resized_frame = MagicMock()
        mock_resize.return_value = resized_frame
        
        mock_cap = MagicMock()
        mock_cap.read.side_effect = [(True, dummy_frame), (False, None)]
        player.video_cap = mock_cap
        
        player._read_frames()
        self.assertTrue(player.all_frames_read)
        self.assertEqual(player.frames_written, 1)
        self.assertFalse(player.frame_queue.empty())
        idx, frame = player.frame_queue.get()
        self.assertEqual(idx, 0)
        self.assertEqual(frame, resized_frame)

    @patch("sys.argv", ["video_render.py", "video.mp4"])
    @patch("cv2.cvtColor")
    @patch("PIL.Image.fromarray")
    @patch("video_render.convert_frame")
    def test_convert_frames(self, mock_convert_frame, mock_fromarray, mock_cvtColor):
        args = video_render.parse_args()
        player = video_render.ASCIIVideoPlayer(args)
        
        dummy_frame = MagicMock()
        player.frame_queue.put((0, dummy_frame))
        player.all_frames_read = True
        
        mock_img = MagicMock()
        mock_fromarray.return_value = mock_img
        mock_convert_frame.return_value = ["#", "#"]
        
        player._convert_frames(0, 3)
        
        self.assertEqual(player.frames_converted, 1)
        self.assertIn(0, player.queue)
        self.assertEqual(player.queue[0], "#\n#")

    @patch("sys.argv", ["video_render.py", "video.mp4"])
    @patch("video_render.stop_audio")
    @patch("video_render.play_audio")
    @patch("video_render.pause_audio")
    @patch("video_render.resume_audio")
    def test_play_loop(self, mock_resume, mock_pause, mock_play, mock_stop):
        args = video_render.parse_args()
        player = video_render.ASCIIVideoPlayer(args)
        player.framerate = 30
        player.speed = 1.0
        player.total_frames = 5
        player.begin_time = datetime.datetime.now()
        player.frame_begin_time = datetime.datetime.now()
        player.queue[0] = "FRAME0"
        
        player.controls = MagicMock()
        player.controls.should_quit.side_effect = [False, True]
        player.controls.consume_seek.return_value = 0
        player.controls.is_paused.return_value = False
        
        player._show_frame = MagicMock()
        player._finish = MagicMock()
        
        player._play_loop()
        
        self.assertTrue(player.stopped)
        player._show_frame.assert_called_once_with("FRAME0", 1, ANY)
        player._finish.assert_called_once()

    @patch("sys.argv", ["video_render.py", "video.mp4"])
    @patch("video_render.Thread")
    @patch("video_render.detect_player")
    @patch("time.sleep")
    def test_run_lifecycle(self, mock_sleep, mock_detect_player, mock_thread_class):
        args = video_render.parse_args()
        player = video_render.ASCIIVideoPlayer(args)
        player.no_intro = True
        
        player.load_video = MagicMock(return_value=True)
        player.controls = MagicMock()
        player.total_frames = 100
        player.frames_converted = 50
        
        # We want to break out of run's buffer/playback loop
        player.stopped = False
        def side_effect(*args, **kwargs):
            player.stopped = True
        mock_sleep.side_effect = side_effect
        
        mock_thread_instance = MagicMock()
        mock_thread_class.return_value = mock_thread_instance
        
        with patch("builtins.print"):
            player.run()
        
        player.load_video.assert_called_once()
        player.controls.start.assert_called_once()
        self.assertTrue(mock_thread_class.called)
        self.assertTrue(mock_thread_instance.start.called)
        self.assertTrue(mock_thread_instance.join.called)

    @patch("sys.argv", ["video_render.py", "video.mp4"])
    @patch("video_render.Thread")
    def test_start_processing_threads(self, mock_thread_class):
        args = video_render.parse_args()
        player = video_render.ASCIIVideoPlayer(args)
        player.video_cap = MagicMock()
        
        mock_thread_instance = MagicMock()
        mock_thread_class.return_value = mock_thread_instance
        
        player._start_processing_threads(start_frame=10)
        
        self.assertFalse(player.all_frames_read)
        self.assertEqual(player.frames_written, 10)
        player.video_cap.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 10)
        self.assertEqual(mock_thread_class.call_count, 4)  # 1 reader + 3 converters

    @patch("sys.argv", ["video_render.py", "video.mp4"])
    @patch("cv2.resize")
    def test_read_frames_seek(self, mock_resize):
        args = video_render.parse_args()
        player = video_render.ASCIIVideoPlayer(args)
        player.video_cap = MagicMock()
        
        # Mock frame reads: first call returns true, second false
        dummy_frame = MagicMock()
        dummy_frame.shape = (480, 640, 3)
        player.video_cap.read.side_effect = [(True, dummy_frame), (False, None)]
        player.seek_request_frame = 20
        player.stopped = False
        
        # Call read frames. Since we have seek_request_frame, it should seek.
        player._read_frames()
        
        player.video_cap.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 20)
        self.assertEqual(player.frames_written, 21)  # start 20 + 1 frame read
        self.assertTrue(player.all_frames_read)
class TestLiveRender(unittest.TestCase):

    @patch("sys.argv", ["live_render.py", "--monitor", "0", "--region", "10,20,30,40", "--framerate", "15", "--scale", "2", "--video-mode", "--threads", "2"])
    @patch("live_render.mss.mss")
    @patch("live_render.keyboard.Listener")
    @patch("live_render.Thread")
    @patch("live_render.timing_module")
    @patch("live_render.cursor.hide")
    @patch("live_render.cursor.show")
    @patch("time.sleep")
    def test_live_parse_args(self, mock_sleep, mock_cshow, mock_chide, mock_timing, mock_thread_class, mock_listener_class, mock_mss_class):
        mock_sct = MagicMock()
        mock_sct.monitors = [{"left": 0, "top": 0, "width": 100, "height": 100}]
        mock_mss_class.return_value.__enter__.return_value = mock_sct
        
        mock_listener = MagicMock()
        mock_listener_class.return_value = mock_listener
        
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread
        
        mock_timing.side_effect = KeyboardInterrupt()
        
        with patch("builtins.print"):
            live_render.main()
        
        self.assertEqual(live_render.args.monitor, 0)
        self.assertEqual(live_render.args.framerate, 15)
        self.assertEqual(live_render.args.scale, 2)
        self.assertTrue(live_render.args.video_mode)
        self.assertEqual(live_render.args.threads, 2)
        self.assertEqual(live_render.MONITOR, {"left": 10, "top": 20, "width": 30, "height": 40})
        
        mock_listener.start.assert_called_once()
        mock_listener.stop.assert_called_once()
        mock_thread.start.assert_called()

    @patch("sys.argv", ["live_render.py", "--monitor", "0", "--region", "10,20"])
    @patch("live_render.mss.mss")
    def test_live_parse_args_invalid_region(self, mock_mss_class):
        mock_sct = MagicMock()
        mock_sct.monitors = [{"left": 0, "top": 0, "width": 100, "height": 100}]
        mock_mss_class.return_value.__enter__.return_value = mock_sct
        
        with patch('sys.stderr'), patch('sys.stdout'):
            with self.assertRaises(SystemExit):
                live_render.main()

    @patch("sys.argv", ["live_render.py", "--monitor", "5"])
    @patch("live_render.mss.mss")
    def test_live_parse_args_invalid_monitor(self, mock_mss_class):
        mock_sct = MagicMock()
        mock_sct.monitors = [{"left": 0, "top": 0, "width": 100, "height": 100}]
        mock_mss_class.return_value.__enter__.return_value = mock_sct
        
        with patch('sys.stderr'), patch('sys.stdout'):
            with self.assertRaises(SystemExit):
                live_render.main()

    def test_input_checker(self):
        live_render.watching_video = False
        live_render.input_checker(keyboard.Key.shift_r)
        self.assertTrue(live_render.watching_video)
        
        live_render.input_checker(keyboard.Key.shift_r)
        self.assertFalse(live_render.watching_video)
        
        live_render.input_checker(keyboard.Key.space)
        self.assertFalse(live_render.watching_video)

    @patch("live_render.mss.mss")
    @patch("shutil.get_terminal_size")
    @patch("PIL.Image.frombytes")
    @patch("live_render.convert_frame")
    @patch("live_render.display_frame")
    def test_render_image_thread_scaling(self, mock_display, mock_convert, mock_frombytes, mock_get_terminal_size, mock_mss_class):
        mock_sct = MagicMock()
        mock_mss_class.return_value = mock_sct
        
        mock_sct_img = MagicMock()
        mock_sct_img.size = (1920, 1080)
        mock_sct_img.bgra = b"\x00" * (1920 * 1080 * 4)
        
        def grab_side_effect(monitor):
            live_render.stopped = True
            return mock_sct_img
        mock_sct.grab.side_effect = grab_side_effect
        
        mock_get_terminal_size.return_value = (80, 24)
        
        mock_img = MagicMock()
        mock_frombytes.return_value = mock_img
        
        live_render.args = MagicMock()
        live_render.args.framerate = 30
        live_render.args.scale = None
        live_render.args.contrast = 1.0
        live_render.args.brightness = 1.0
        live_render.args.dither = "none"
        
        live_render.MONITOR = {"width": 1920, "height": 1080}
        live_render.stopped = False
        
        live_render.render_image_thread(0)
        
        # Sizing calculation validation:
        # max_w = (80 - 2) // 2 = 39
        # max_h = 24 - 4 = 20
        # aspect_ratio = 1920 / 1080 = 1.7777777777777777
        # h1 = int(39 / 1.77777) = 21 > max_h (20)
        # So width = int(20 * 1.77777) = 35, height = 20
        mock_img.resize.assert_called_once_with((35, 20), ANY)

    @patch("live_render.mss.mss")
    @patch("PIL.Image.frombytes")
    @patch("live_render.convert_frame")
    @patch("live_render.display_frame")
    def test_render_image_thread_fixed_scale(self, mock_display, mock_convert, mock_frombytes, mock_mss_class):
        mock_sct = MagicMock()
        mock_mss_class.return_value = mock_sct
        
        mock_sct_img = MagicMock()
        mock_sct_img.size = (1920, 1080)
        mock_sct_img.bgra = b"\x00" * (1920 * 1080 * 4)
        
        def grab_side_effect(monitor):
            live_render.stopped = True
            return mock_sct_img
        mock_sct.grab.side_effect = grab_side_effect
        
        mock_img = MagicMock()
        mock_frombytes.return_value = mock_img
        
        live_render.args = MagicMock()
        live_render.args.framerate = 30
        live_render.args.scale = 2
        live_render.args.contrast = 1.0
        live_render.args.brightness = 1.0
        live_render.args.dither = "none"
        
        live_render.MONITOR = {"width": 1920, "height": 1080}
        live_render.stopped = False
        
        live_render.render_image_thread(0)
        
        # Sizing logic with scale=2:
        # width = 1920 // 2 = 960
        # height = 1080 // 2 = 540
        mock_img.resize.assert_called_once_with((960, 540), ANY)

if __name__ == "__main__":
    unittest.main()
