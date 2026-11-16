"""Progress/result pinning must survive game focus and stop on user dismissal."""
import unittest
from unittest.mock import patch
import test_translation_handoff as handoff_support
import test_settings_navigation as qt_support
import test_region_selector as selector_support

if qt_support.QT_AVAILABLE:
    from PySide6.QtCore import QEvent


@unittest.skipUnless(qt_support.QT_AVAILABLE, 'Qt UI dependencies are not installed')
class PinnedTranslationTests(unittest.TestCase):
    setUpClass = classmethod(handoff_support.TranslationHandoffTests.setUpClass.__func__)
    flush = handoff_support.TranslationHandoffTests.flush
    cleanup_windows = handoff_support.TranslationHandoffTests.cleanup_windows
    cleanup_selector = handoff_support.TranslationHandoffTests.cleanup_selector
    deliver_crop = handoff_support.TranslationHandoffTests.deliver_crop
    record_stage = handoff_support.TranslationHandoffTests.record_stage

    def setUp(self):
        handoff_support.TranslationHandoffTests.setUp(self)
        self.topmost_patch = patch('window_focus.keep_on_top', return_value=True)
        self.topmost = self.topmost_patch.start()
        self.addCleanup(self.topmost_patch.stop)
        self.window.translation_dismissed.connect(lambda: self.active.__setitem__('suppress_result', True))

    def start_translation(self):
        self.deliver_crop(selector_support.Picture(320, 240))
        self.flush()

    def test_progress_and_result_remain_pinned_after_deactivation(self):
        self.start_translation()
        geometry = self.window.geometry()
        calls = self.topmost.call_count
        with patch.object(self.window, 'isActiveWindow', return_value=False):
            self.window.changeEvent(QEvent(QEvent.Type.ActivationChange))
            self.flush()
        self.assertGreater(self.topmost.call_count, calls)
        self.assertTrue(self.window._translation_pinned)
        self.assertTrue(self.window.translation_topmost_timer.isActive())
        self.assertEqual(self.window.geometry(), geometry)
        self.native.assert_called_once()  # No repeated foreground activation.
        self.active['worker'].finished_text.emit('Kész fordítás.')
        self.flush()
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window._translation_pinned)
        self.assertTrue(self.window.translation_topmost_timer.isActive())
        self.assertEqual(self.window.label.toPlainText(), 'Kész fordítás.')
        self.native.assert_called_once()

    def test_close_button_stops_pinning_and_suppresses_late_result(self):
        self.start_translation()
        self.window.close_button.click()
        self.flush()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window._translation_pinned)
        self.assertFalse(self.window.translation_topmost_timer.isActive())
        self.assertTrue(self.active['suppress_result'])
        self.active['worker'].finished_text.emit('Késői fordítás.')
        self.flush()
        self.assertFalse(self.window.isVisible())

    def test_stale_timer_after_hide_cannot_reshow_or_reorder_window(self):
        self.start_translation()
        self.window.close_button.click()
        self.flush()
        self.topmost.reset_mock()
        self.window.translation_topmost_timer.timeout.emit()
        self.window.keep_translation_on_top()
        self.assertFalse(self.window.isVisible())
        self.topmost.assert_not_called()

    def test_manual_new_capture_can_pin_again_after_close(self):
        self.start_translation()
        self.window.close_button.click()
        self.flush()
        self.active['worker'].running = False
        self.start_translation()
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window._translation_pinned)
        self.assertFalse(self.active['suppress_result'])

    def test_topmost_failure_keeps_retrying_without_stealing_focus(self):
        self.topmost.return_value = False
        self.start_translation()
        self.assertTrue(self.window.translation_topmost_timer.isActive())
        before = self.topmost.call_count
        self.topmost.return_value = True
        self.window.translation_topmost_timer.timeout.emit()
        self.assertGreater(self.topmost.call_count, before)
        self.native.assert_called_once()


if __name__ == '__main__':
    unittest.main()
