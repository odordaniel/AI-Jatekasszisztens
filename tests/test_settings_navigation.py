"""Real Qt layout checks; no audio device, API request or Windows hooks."""
import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtWidgets import QApplication, QScrollArea
    from PySide6.QtCore import QSize, QPoint
    import keyring
    import requests
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, 'Qt UI dependencies are not installed')
class SettingsNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
        with patch.dict(os.environ, LOCALAPPDATA=cls.temp.name):
            import assistant
            import live_translation
        cls.core, cls.audio = assistant, live_translation
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.get_key = patch.object(keyring, 'get_password', return_value='')
        self.get_key.start()
        self.addCleanup(self.get_key.stop)
        self.device_scan = patch.object(self.audio.LiveTranslationSettings, 'load_devices')
        self.device_scan.start()
        self.addCleanup(self.device_scan.stop)
        self.window_file = patch.object(self.core.Overlay, 'WINDOW_PATH', Path(self.temp.name) / 'window.json')
        self.window_file.start()
        self.addCleanup(self.window_file.stop)
        self.core.Overlay.WINDOW_PATH.unlink(missing_ok=True)
        self.cfg = dict(self.core.DEFAULTS, model='vision-model')
        self.window = self.core.Overlay(self.cfg, self.core.HistoryStore())
        self.settings = self.audio.LiveTranslationSettings(
            self.temp.name, lambda *args: True, lambda: self.cfg)
        self.window.attach_audio_settings(self.settings)
        self.window.audio_settings_requested.connect(self.settings.open_settings)
        self.window.show()
        self.flush()
        self.addCleanup(self.cleanup_windows)

    def flush(self):
        for _ in range(4):
            self.app.processEvents()

    def cleanup_windows(self):
        self.window.geometry_timer.stop()
        self.window.game_status_timer.stop()
        self.settings.indicator.stop()
        self.settings.indicator.close()
        self.settings.subtitle.close()
        self.window.hide()
        self.window.deleteLater()
        self.flush()

    def test_navigation_keeps_geometry_and_uncommitted_fields(self):
        self.window.toggle_settings()
        self.window.api_url_input.setText('https://unsaved.example/v1/chat/completions')
        for size in (QSize(660, 680), QSize(465, 400), QSize(900, 800)):
            with self.subTest(size=size):
                self.window.resize(size)
                self.window.move(QPoint(38, 42))
                self.flush()
                geometry = self.window.geometry()
                self.window.audio_settings_button.click()
                self.flush()
                self.assertEqual(self.window.geometry(), geometry)
                self.assertTrue(self.window.audio_settings_button.isChecked())
                footer = self.settings.save_button
                self.assertTrue(self.window.rect().contains(footer.mapTo(self.window, footer.rect().bottomRight())))
                self.window.general_settings_button.click()
                self.flush()
                self.assertEqual(self.window.geometry(), geometry)
                self.assertFalse(self.window.settings_panel.isHidden())
                self.assertTrue(self.window.general_settings_button.isChecked())
                self.assertEqual(self.window.api_url_input.text(), 'https://unsaved.example/v1/chat/completions')

    def test_back_and_gear_return_to_general_without_closing_settings(self):
        self.window.toggle_settings()
        self.flush()
        for return_action in (self.window.close_audio_settings, self.window.toggle_settings):
            self.window.show_audio_settings()
            self.window.resize(720, 710)
            self.flush()
            geometry = self.window.geometry()
            return_action()
            self.flush()
            self.assertEqual(self.window.geometry(), geometry)
            self.assertFalse(self.window.settings_panel.isHidden())

    def test_direct_audio_entry_and_return_restore_compact_view(self):
        compact = self.window.size()
        self.window.show_audio_settings()
        self.flush()
        self.window.general_settings_button.click()
        self.flush()
        self.window.close_settings()
        self.flush()
        self.assertEqual(self.window.size(), compact)
        self.assertTrue(self.window.settings_navigation.isHidden())

    def test_tabs_fit_narrow_window_without_horizontal_scroll(self):
        self.window.toggle_settings()
        self.window.resize(465, 500)
        for audio in (False, True):
            if audio:
                self.window.show_audio_settings()
            tabs = self.settings.settings_tabs if audio else self.window.settings_tabs
            for index in range(tabs.count()):
                tabs.setCurrentIndex(index)
                self.flush()
                self.assertEqual(self.window.width(), 465)
                scroll = tabs.widget(index)
                self.assertIsInstance(scroll, QScrollArea)
                self.assertLessEqual(scroll.widget().minimumSizeHint().width(), scroll.viewport().width())

    def test_settings_size_is_shared_and_persisted(self):
        self.window.toggle_settings()
        self.window.show_audio_settings()
        self.window.resize(710, 730)
        self.flush()
        self.window.close_audio_settings()
        self.window.save_geometry()
        self.window.close_settings()
        data = json.loads(self.core.Overlay.WINDOW_PATH.read_text())
        data.update(audio_width=1000, audio_height=1000)
        self.core.Overlay.WINDOW_PATH.write_text(json.dumps(data))
        self.window.restore_geometry()
        self.window.toggle_settings()
        self.flush()
        self.assertEqual(self.window.size(), QSize(710, 730))
        self.assertEqual(self.window._audio_size, self.window._settings_size)


if __name__ == '__main__':
    unittest.main()
