"""Win32 focus and cursor release contract using injected native API doubles."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from window_focus import activate_window


class WindowFocusTests(unittest.TestCase):
    def apis(self):
        user = SimpleNamespace(**{name: Mock(return_value=1) for name in (
            'GetForegroundWindow', 'GetWindowThreadProcessId', 'AttachThreadInput',
            'BringWindowToTop', 'SetForegroundWindow', 'IsIconic', 'ShowWindow', 'SetFocus', 'ClipCursor')})
        user.GetForegroundWindow.side_effect = [111, 222]
        user.GetWindowThreadProcessId.return_value = 10
        user.IsIconic.return_value = False
        kernel = SimpleNamespace(GetCurrentThreadId=Mock(return_value=20))
        return user, kernel

    def test_foreground_activation_releases_cursor_and_detaches_threads(self):
        user, kernel = self.apis()
        self.assertTrue(activate_window(222, user, kernel))
        user.SetForegroundWindow.assert_called_once_with(222)
        user.ClipCursor.assert_called_once_with(None)
        self.assertEqual(user.AttachThreadInput.call_args_list, [call(20, 10, True), call(20, 10, False)])
        user.ShowWindow.assert_not_called()

    def test_denied_activation_does_not_release_game_cursor(self):
        user, kernel = self.apis()
        user.GetForegroundWindow.side_effect = [111, 111]
        self.assertFalse(activate_window(222, user, kernel))
        user.ClipCursor.assert_not_called()
        user.AttachThreadInput.assert_called_with(20, 10, False)

    def test_native_failure_still_detaches_thread_input(self):
        user, kernel = self.apis()
        user.SetForegroundWindow.side_effect = OSError('failure')
        self.assertFalse(activate_window(222, user, kernel))
        user.AttachThreadInput.assert_called_with(20, 10, False)

    def test_minimized_window_restored_without_resizing_normal_window(self):
        user, kernel = self.apis()
        user.IsIconic.return_value = True
        self.assertTrue(activate_window(222, user, kernel))
        user.ShowWindow.assert_called_once_with(222, 9)


if __name__ == '__main__':
    unittest.main()
