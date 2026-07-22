import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import subprocess

# Import modules to test
import youtubedl_saver
import audio
import controls
from controls import PlaybackControls
from pynput import keyboard


class TestYoutubedlSaver(unittest.TestCase):
    @patch('youtubedl_saver.youtube_dl.YoutubeDL')
    def test_save_file_success(self, mock_ydl_class):
        # Set up mock instance
        mock_ydl_instance = MagicMock()
        mock_ydl_class.return_value = mock_ydl_instance
        # YoutubeDL is a context manager, so __enter__ returns the instance
        mock_ydl_instance.__enter__.return_value = mock_ydl_instance
        
        # Mock extract_info output
        mock_ydl_instance.extract_info.return_value = {
            'fps': 30,
            'duration': 10,
            'title': 'test'
        }
        
        # Test success call
        outtmpl, fps, total_frames, duration = youtubedl_saver.save_file("https://youtube.com/watch?v=123", "custom_tmpl")
        
        self.assertEqual(outtmpl, "custom_tmpl")
        self.assertEqual(fps, 30)
        self.assertEqual(total_frames, 300)
        self.assertEqual(duration, 10)
        mock_ydl_instance.extract_info.assert_called_once_with(url="https://youtube.com/watch?v=123", download=True)

    @patch('youtubedl_saver.youtube_dl.YoutubeDL')
    def test_save_file_default_outtmpl(self, mock_ydl_class):
        mock_ydl_instance = MagicMock()
        mock_ydl_class.return_value = mock_ydl_instance
        mock_ydl_instance.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.extract_info.return_value = {
            'fps': 24,
            'duration': 5,
            'title': 'test'
        }
        
        outtmpl, fps, total_frames, duration = youtubedl_saver.save_file("https://youtube.com/watch?v=123")
        
        self.assertEqual(outtmpl, "video")
        self.assertEqual(fps, 24)
        self.assertEqual(total_frames, 120)
        self.assertEqual(duration, 5)

    @patch('youtubedl_saver.youtube_dl.YoutubeDL')
    def test_save_file_missing_fps_duration(self, mock_ydl_class):
        mock_ydl_instance = MagicMock()
        mock_ydl_class.return_value = mock_ydl_instance
        mock_ydl_instance.__enter__.return_value = mock_ydl_instance
        # fps defaults to 30, duration defaults to 0 if None
        mock_ydl_instance.extract_info.return_value = {
            'title': 'test'
        }
        
        outtmpl, fps, total_frames, duration = youtubedl_saver.save_file("https://youtube.com/watch?v=123")
        
        self.assertEqual(fps, 30)
        self.assertEqual(duration, 0)
        self.assertEqual(total_frames, 0)

    @patch('youtubedl_saver.youtube_dl.YoutubeDL')
    @patch('builtins.print')
    def test_save_file_error(self, mock_print, mock_ydl_class):
        mock_ydl_instance = MagicMock()
        mock_ydl_class.return_value = mock_ydl_instance
        mock_ydl_instance.__enter__.return_value = mock_ydl_instance
        
        # Force an exception
        mock_ydl_instance.extract_info.side_effect = Exception("Network error")
        
        # Test error case
        outtmpl, fps, total_frames, duration = youtubedl_saver.save_file("https://youtube.com/watch?v=123", "custom_tmpl")
        
        self.assertEqual(outtmpl, "error")
        self.assertEqual(fps, 0)
        self.assertEqual(total_frames, 0)
        self.assertEqual(duration, 0)
        mock_print.assert_called_once_with("Error downloading video: Network error")


class TestAudio(unittest.TestCase):
    @patch('audio.subprocess.run')
    @patch('sys.platform', 'win32')
    def test_detect_player_win32_ffplay_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        player = audio.detect_player()
        self.assertEqual(player, "ffplay")
        mock_run.assert_called_with(["ffplay", "-version"], capture_output=True, timeout=2)

    @patch('audio.subprocess.run')
    @patch('sys.platform', 'win32')
    def test_detect_player_win32_ffplay_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        player = audio.detect_player()
        self.assertIsNone(player)

    @patch('audio.subprocess.run')
    @patch('sys.platform', 'darwin')
    def test_detect_player_darwin_ffplay_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        player = audio.detect_player()
        self.assertEqual(player, "ffplay")
        mock_run.assert_called_with(["ffplay", "--version"], capture_output=True, timeout=2)

    @patch('audio.subprocess.run')
    @patch('sys.platform', 'darwin')
    def test_detect_player_darwin_ffplay_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        player = audio.detect_player()
        self.assertEqual(player, "afplay")

    @patch('audio.subprocess.run')
    @patch('sys.platform', 'linux')
    def test_detect_player_linux_ffplay_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        player = audio.detect_player()
        self.assertEqual(player, "ffplay")

    @patch('audio.subprocess.run')
    @patch('sys.platform', 'linux')
    def test_detect_player_linux_ffplay_missing_aplay_available(self, mock_run):
        def side_effect(cmd, *args, **kwargs):
            if cmd[0] == "ffplay":
                raise FileNotFoundError()
            elif cmd[0] == "aplay":
                return MagicMock(returncode=0)
            raise FileNotFoundError()
        mock_run.side_effect = side_effect
        player = audio.detect_player()
        self.assertEqual(player, "aplay")

    @patch('audio.subprocess.run')
    @patch('sys.platform', 'linux')
    def test_detect_player_linux_ffplay_missing_aplay_missing_paplay_available(self, mock_run):
        def side_effect(cmd, *args, **kwargs):
            if cmd[0] == "ffplay":
                raise FileNotFoundError()
            elif cmd[0] == "aplay":
                raise FileNotFoundError()
            elif cmd[0] == "paplay":
                return MagicMock(returncode=0)
            raise FileNotFoundError()
        mock_run.side_effect = side_effect
        player = audio.detect_player()
        self.assertEqual(player, "paplay")

    @patch('audio.subprocess.run')
    @patch('sys.platform', 'linux')
    def test_detect_player_linux_all_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        player = audio.detect_player()
        self.assertIsNone(player)

    @patch('audio.os.path.isfile')
    @patch('audio.subprocess.Popen')
    def test_play_audio_invalid_path(self, mock_popen, mock_isfile):
        mock_isfile.return_value = False
        self.assertIsNone(audio.play_audio("nonexistent.mp4", "ffplay"))
        mock_popen.assert_not_called()

    @patch('audio.os.path.isfile')
    @patch('audio.subprocess.Popen')
    def test_play_audio_afplay(self, mock_popen, mock_isfile):
        mock_isfile.return_value = True
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        proc = audio.play_audio("test.mp4", "afplay")
        self.assertEqual(proc, mock_process)
        mock_popen.assert_called_with(
            ["afplay", "test.mp4", "-q", "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    @patch('audio.os.path.isfile')
    @patch('audio.subprocess.Popen')
    def test_play_audio_ffplay_no_start_time(self, mock_popen, mock_isfile):
        mock_isfile.return_value = True
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        proc = audio.play_audio("test.mp4", "ffplay")
        self.assertEqual(proc, mock_process)
        mock_popen.assert_called_with(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "test.mp4"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    @patch('audio.os.path.isfile')
    @patch('audio.subprocess.Popen')
    def test_play_audio_ffplay_with_start_time(self, mock_popen, mock_isfile):
        mock_isfile.return_value = True
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        proc = audio.play_audio("test.mp4", "ffplay", start_time=15)
        self.assertEqual(proc, mock_process)
        mock_popen.assert_called_with(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-ss", "15", "test.mp4"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    @patch('audio.os.path.isfile')
    @patch('audio.subprocess.Popen')
    def test_play_audio_aplay(self, mock_popen, mock_isfile):
        mock_isfile.return_value = True
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        proc = audio.play_audio("test.mp4", "aplay")
        self.assertEqual(proc, mock_process)
        mock_popen.assert_called_with(
            ["aplay", "-q", "test.mp4"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    @patch('audio.os.path.isfile')
    @patch('audio.subprocess.Popen')
    def test_play_audio_paplay(self, mock_popen, mock_isfile):
        mock_isfile.return_value = True
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        proc = audio.play_audio("test.mp4", "paplay")
        self.assertEqual(proc, mock_process)
        mock_popen.assert_called_with(
            ["paplay", "test.mp4"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    @patch('audio.os.path.isfile')
    @patch('audio.subprocess.Popen')
    def test_play_audio_exception(self, mock_popen, mock_isfile):
        mock_isfile.return_value = True
        mock_popen.side_effect = Exception("Spawn failed")
        
        proc = audio.play_audio("test.mp4", "ffplay")
        self.assertIsNone(proc)

    def test_stop_audio_none(self):
        # Should not raise any exception
        audio.stop_audio(None)

    def test_stop_audio_success(self):
        mock_process = MagicMock()
        audio.stop_audio(mock_process)
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=3)
        mock_process.kill.assert_not_called()

    def test_stop_audio_terminate_raises_kill_succeeds(self):
        mock_process = MagicMock()
        mock_process.terminate.side_effect = Exception("Cannot terminate")
        audio.stop_audio(mock_process)
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    def test_stop_audio_wait_raises_kill_succeeds(self):
        mock_process = MagicMock()
        mock_process.wait.side_effect = Exception("Timeout waiting")
        audio.stop_audio(mock_process)
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=3)
        mock_process.kill.assert_called_once()

    def test_stop_audio_kill_raises(self):
        mock_process = MagicMock()
        mock_process.terminate.side_effect = Exception("Cannot terminate")
        mock_process.kill.side_effect = Exception("Cannot kill")
        # Should catch and handle without raising
        audio.stop_audio(mock_process)
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    def test_pause_audio_none(self):
        self.assertFalse(audio.pause_audio(None))

    @patch('sys.platform', 'win32')
    def test_pause_audio_win32(self):
        mock_process = MagicMock()
        self.assertFalse(audio.pause_audio(mock_process))
        mock_process.send_signal.assert_not_called()

    @patch('sys.platform', 'linux')
    def test_pause_audio_linux_success(self):
        import signal
        mock_process = MagicMock()
        self.assertTrue(audio.pause_audio(mock_process))
        mock_process.send_signal.assert_called_once_with(signal.SIGSTOP)

    @patch('sys.platform', 'linux')
    def test_pause_audio_linux_failure(self):
        import signal
        mock_process = MagicMock()
        mock_process.send_signal.side_effect = Exception("Failed to send signal")
        self.assertFalse(audio.pause_audio(mock_process))
        mock_process.send_signal.assert_called_once_with(signal.SIGSTOP)

    def test_resume_audio_none(self):
        self.assertFalse(audio.resume_audio(None))

    @patch('sys.platform', 'win32')
    def test_resume_audio_win32(self):
        mock_process = MagicMock()
        self.assertFalse(audio.resume_audio(mock_process))
        mock_process.send_signal.assert_not_called()

    @patch('sys.platform', 'linux')
    def test_resume_audio_linux_success(self):
        import signal
        mock_process = MagicMock()
        self.assertTrue(audio.resume_audio(mock_process))
        mock_process.send_signal.assert_called_once_with(signal.SIGCONT)

    @patch('sys.platform', 'linux')
    def test_resume_audio_linux_failure(self):
        import signal
        mock_process = MagicMock()
        mock_process.send_signal.side_effect = Exception("Failed to send signal")
        self.assertFalse(audio.resume_audio(mock_process))
        mock_process.send_signal.assert_called_once_with(signal.SIGCONT)


class TestControls(unittest.TestCase):
    def test_init_state(self):
        controls_obj = PlaybackControls()
        self.assertFalse(controls_obj.is_paused())
        self.assertFalse(controls_obj.should_quit())
        self.assertEqual(controls_obj.consume_seek(), 0)

    @patch('controls.keyboard.Listener')
    def test_start_stop(self, mock_listener_class):
        mock_listener_instance = MagicMock()
        mock_listener_class.return_value = mock_listener_instance
        
        controls_obj = PlaybackControls()
        controls_obj.start()
        
        mock_listener_class.assert_called_once_with(on_press=controls_obj.on_press)
        mock_listener_instance.start.assert_called_once()
        
        controls_obj.stop()
        mock_listener_instance.stop.assert_called_once()

    def test_on_press_space(self):
        controls_obj = PlaybackControls()
        self.assertFalse(controls_obj.is_paused())
        
        # Mock key event for space
        mock_key = MagicMock(char=" ")
        controls_obj.on_press(mock_key)
        self.assertTrue(controls_obj.is_paused())
        
        # Press space again to resume
        controls_obj.on_press(mock_key)
        self.assertFalse(controls_obj.is_paused())

    def test_on_press_k(self):
        controls_obj = PlaybackControls()
        self.assertFalse(controls_obj.is_paused())
        
        mock_key = MagicMock(char="k")
        controls_obj.on_press(mock_key)
        self.assertTrue(controls_obj.is_paused())

        mock_key_caps = MagicMock(char="K")
        controls_obj.on_press(mock_key_caps)
        self.assertFalse(controls_obj.is_paused())

    def test_on_press_quit(self):
        controls_obj = PlaybackControls()
        self.assertFalse(controls_obj.should_quit())
        
        mock_key = MagicMock(char="q")
        controls_obj.on_press(mock_key)
        self.assertTrue(controls_obj.should_quit())

        controls_obj = PlaybackControls()
        self.assertFalse(controls_obj.should_quit())
        mock_key_caps = MagicMock(char="Q")
        controls_obj.on_press(mock_key_caps)
        self.assertTrue(controls_obj.should_quit())

    def test_on_press_arrows(self):
        controls_obj = PlaybackControls()
        self.assertEqual(controls_obj.consume_seek(), 0)
        
        # Seek right
        controls_obj.on_press(keyboard.Key.right)
        # It adds SEEK_STEP_SECONDS (5)
        self.assertEqual(controls_obj.consume_seek(), 5)
        # consume_seek should reset it to 0
        self.assertEqual(controls_obj.consume_seek(), 0)
        
        # Seek left
        controls_obj.on_press(keyboard.Key.left)
        self.assertEqual(controls_obj.consume_seek(), -5)
        self.assertEqual(controls_obj.consume_seek(), 0)

    def test_on_press_j_l(self):
        controls_obj = PlaybackControls()
        
        # Seek right with 'l'
        mock_key_l = MagicMock(char='l')
        controls_obj.on_press(mock_key_l)
        self.assertEqual(controls_obj.consume_seek(), 5)
        
        # Seek left with 'j'
        mock_key_j = MagicMock(char='j')
        controls_obj.on_press(mock_key_j)
        self.assertEqual(controls_obj.consume_seek(), -5)

        # Seek right with 'L'
        mock_key_l_caps = MagicMock(char='L')
        controls_obj.on_press(mock_key_l_caps)
        self.assertEqual(controls_obj.consume_seek(), 5)
        
        # Seek left with 'J'
        mock_key_j_caps = MagicMock(char='J')
        controls_obj.on_press(mock_key_j_caps)
        self.assertEqual(controls_obj.consume_seek(), -5)


if __name__ == '__main__':
    unittest.main()
