"""First hotkey presentation, including native handoff timing and cancellation."""
import threading
import unittest
from unittest.mock import patch
import test_settings_navigation as support

if support.QT_AVAILABLE:
    from PySide6.QtCore import QObject, Signal, QEvent
    from PySide6.QtTest import QTest

    class HistoryShortcut(QObject):
        requested = Signal()


@unittest.skipUnless(support.QT_AVAILABLE, 'Qt UI dependencies are not installed')
class HistoryFirstOpenTests(unittest.TestCase):
    setUpClass = classmethod(support.SettingsNavigationTests.setUpClass.__func__)
    setUp = support.SettingsNavigationTests.setUp
    flush = support.SettingsNavigationTests.flush
    cleanup_windows = support.SettingsNavigationTests.cleanup_windows

    def test_single_worker_signal_opens_hidden_window_and_paints_before_cursor_move(self):
        self.window.set_history_open(False)
        self.window.hide()
        shortcut = HistoryShortcut()
        shortcut.requested.connect(self.window.show_history_from_hotkey)
        order = []
        original = self.window.repaint
        def repaint():
            order.append('paint')
            original()
        with patch.object(self.window, 'repaint', side_effect=repaint), \
                patch('window_focus.activate_window', side_effect=lambda _: order.append('activate') or True), \
                patch('window_focus.keep_on_top', side_effect=lambda _: order.append('top') or True), \
                patch.object(self.core.QCursor, 'setPos', side_effect=lambda _: order.append('cursor')):
            worker = threading.Thread(target=shortcut.requested.emit)
            worker.start()
            worker.join()
            self.flush()
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window.history_panel.isVisible())
        self.assertEqual(order, ['paint', 'activate', 'top', 'paint', 'cursor'])
        self.assertIs(self.window.focusWidget(), self.window.history_list)

    def test_first_press_restores_minimized_qt_window(self):
        self.window.showMinimized()
        self.flush()
        self.assertTrue(self.window.isMinimized())
        with patch('window_focus.activate_window', return_value=True) as activate:
            self.window.show_history_from_hotkey()
            self.flush()
            activate.assert_called_once()
        self.assertFalse(self.window.isMinimized())
        self.assertTrue(self.window.history_panel.isVisible())

    def test_one_press_reopens_hidden_window_with_already_open_history(self):
        self.window.set_history_open(True)
        self.window.hide()
        with patch('window_focus.activate_window', return_value=True) as activate:
            self.window.show_history_from_hotkey()
            self.flush()
            activate.assert_called_once()
        self.assertTrue(self.window.history_list.isVisible())

    def test_hotkey_from_both_settings_views(self):
        for audio in (False, True):
            self.window.toggle_settings()
            if audio:
                self.window.show_audio_settings()
            with patch('window_focus.activate_window', return_value=True) as activate:
                self.window.show_history_from_hotkey()
                self.flush()
                activate.assert_called_once()
            self.assertTrue(self.window.history_list.isVisible())
            self.assertTrue(self.window.settings_panel.isHidden())
            self.assertTrue(self.window.audio_settings_scroll.isHidden())

    def test_transient_denial_retries_without_second_key_and_stops_after_success(self):
        with patch('window_focus.activate_window', side_effect=[False, True]) as activate, \
                patch.object(self.core.QCursor, 'setPos') as cursor:
            self.window.show_history_from_hotkey()
            self.flush()
            cursor.assert_not_called()
            QTest.qWait(160)
            self.assertEqual(activate.call_count, 2)
            cursor.assert_called_once()
            QTest.qWait(300)
            self.assertEqual(activate.call_count, 2)

    def test_denied_activation_is_bounded_and_never_moves_cursor(self):
        with patch('window_focus.activate_window', return_value=False) as activate, \
                patch.object(self.core.QCursor, 'setPos') as cursor:
            self.window.show_history_from_hotkey()
            QTest.qWait(450)
            self.assertEqual(activate.call_count, 3)
            cursor.assert_not_called()
            self.assertIsNone(self.window._history_focus_request)

    def test_close_or_switch_before_queued_activation_cancels_handoff(self):
        for cancel in (self.window.hide, self.window.prepare_translation, self.window.toggle_settings):
            with patch('window_focus.activate_window', return_value=True) as activate:
                self.window.show_history_from_hotkey()
                cancel()
                self.flush()
                activate.assert_not_called()

    def test_close_during_retry_cannot_reactivate_reopened_compact_window(self):
        with patch('window_focus.activate_window', return_value=False) as activate:
            self.window.show_history_from_hotkey()
            self.flush()
            self.window.hide()
            self.window.show_message('Translation')
            QTest.qWait(180)
            self.assertEqual(activate.call_count, 1)

    def test_new_request_supersedes_queued_old_request(self):
        with patch('window_focus.activate_window', return_value=True) as activate:
            self.window.show_history_from_hotkey()
            self.window.show_history_from_hotkey()
            self.flush()
            activate.assert_called_once()

    def test_focus_loss_cancels_pending_retry(self):
        with patch('window_focus.activate_window', return_value=False) as activate:
            self.window.show_history_from_hotkey()
            self.flush()
            with patch.object(self.window, 'isActiveWindow', return_value=False):
                self.window.changeEvent(QEvent(QEvent.Type.ActivationChange))
            QTest.qWait(180)
            self.assertEqual(activate.call_count, 1)


if __name__ == '__main__':
    unittest.main()
