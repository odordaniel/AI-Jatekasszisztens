"""Progress must paint before JPEG/API work and before hiding the selector."""
import ast
import io
import logging
import unittest
from pathlib import Path
from unittest.mock import patch
import test_settings_navigation as qt_support
import test_region_selector as selector_support

if qt_support.QT_AVAILABLE:
    from PySide6.QtCore import QObject, Signal, QEvent, Qt, QPoint, QTimer
    from PySide6.QtTest import QTest


@unittest.skipUnless(qt_support.QT_AVAILABLE, 'Qt UI dependencies are not installed')
class TranslationHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_support.SettingsNavigationTests.setUpClass.__func__(cls)
        selector_support.RegionSelectorTests.setUpClass.__func__(cls)
        source = Path(__file__).resolve().parents[1] / 'src' / 'assistant.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        node = next(n for n in main.body if isinstance(n, ast.FunctionDef) and n.name == 'send_selection')
        cls.send_code = compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec')

    flush = qt_support.SettingsNavigationTests.flush
    cleanup_windows = qt_support.SettingsNavigationTests.cleanup_windows
    cleanup_selector = selector_support.RegionSelectorTests.cleanup_selector

    def setUp(self):
        qt_support.SettingsNavigationTests.setUp(self)
        selector_support.RegionSelectorTests.setUp(self)
        paths = patch.multiple(self.core, HISTORY_PATH=Path(self.temp.name) / 'translations.json',
                               FOLDERS_PATH=Path(self.temp.name) / 'folders.json')
        paths.start()
        self.addCleanup(paths.stop)
        self.window.history = self.core.HistoryStore()
        self.window.hide()
        native = patch('window_focus.activate_window', return_value=True)
        self.native = native.start()
        self.addCleanup(native.stop)
        self.active = dict(worker=None, suppress_result=False, game='', generation=0)
        self.stages = []
        self.painted_messages = []
        self.handoffs = []
        owner = self
        class PaintObserver(QObject):
            def eventFilter(self, watched, event):
                if event.type() == QEvent.Type.Paint:
                    owner.painted_messages.append(owner.window.label.toPlainText())
                if watched is owner.selector and event.type() == QEvent.Type.Hide:
                    owner.handoffs.append((owner.window.isVisible(), owner.window.label.toPlainText()))
                return False
        self.observer = PaintObserver(self.window)
        self.window.label.installEventFilter(self.observer)
        self.selector.installEventFilter(self.observer)
        class Worker(QObject):
            finished_text = Signal(str)
            model_started = Signal(str, bool)
            def __init__(self, image, cfg):
                super().__init__()
                self.running = False
            def start(self):
                self.running = True
                owner.record_stage('worker-start')
            def isRunning(self):
                return self.running
        namespace = dict(active=self.active, overlay=self.window, cfg=self.cfg,
                         history=self.window.history, Translator=Worker, io=io,
                         QTimer=QTimer, logging=logging)
        exec(self.send_code, namespace)
        self.send = namespace['send_selection']
        self.selector.selected.connect(self.deliver_crop)

    def record_stage(self, name):
        self.stages.append(dict(name=name, window_visible=self.window.isVisible(),
                                selector_visible=self.selector.isVisible(),
                                text=self.window.label.toPlainText(),
                                painted=any('folyamatban' in text for text in self.painted_messages)))

    def deliver_crop(self, image):
        owner = self
        def save(buffer, **kwargs):
            owner.record_stage('jpeg-save')
            buffer.write(b'synthetic-jpeg')
        image.save = save
        self.send(image)

    def begin_and_drag(self):
        self.selector.begin()
        self.selector.setGeometry(0, 0, 320, 240)
        self.flush()
        QTest.mousePress(self.selector, Qt.MouseButton.LeftButton, pos=QPoint(20, 30))
        QTest.mouseMove(self.selector, QPoint(120, 110))
        self.flush()

    def test_progress_visible_and_painted_before_encoding_and_worker_start(self):
        self.begin_and_drag()
        QTest.mouseRelease(self.selector, Qt.MouseButton.LeftButton, pos=QPoint(120, 110))
        self.flush()
        self.assertEqual([stage['name'] for stage in self.stages], ['jpeg-save', 'worker-start'])
        for stage in self.stages:
            self.assertTrue(stage['window_visible'])
            self.assertFalse(stage['selector_visible'])
            self.assertIn('folyamatban', stage['text'])
            self.assertTrue(stage['painted'])
        self.assertFalse(self.selector.isVisible())
        self.assertEqual(self.selector.last_frame_at_hide, (None, None))
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.active['worker'].isRunning())
        self.assertTrue(self.window.history_panel.isHidden())
        self.assertTrue(self.handoffs[0][0])
        self.assertIn('folyamatban', self.handoffs[0][1])
        self.native.assert_called_once_with(int(self.window.winId()))

    def test_delayed_result_replaces_already_visible_progress(self):
        self.begin_and_drag()
        QTest.mouseRelease(self.selector, Qt.MouseButton.LeftButton, pos=QPoint(120, 110))
        self.flush()
        self.assertIn('folyamatban', self.window.label.toPlainText())
        self.active['worker'].finished_text.emit('Kész fordítás.')
        self.flush()
        self.assertEqual(self.window.label.toPlainText(), 'Kész fordítás.')

    def test_cancel_does_not_open_progress_or_start_worker(self):
        self.begin_and_drag()
        QTest.keyClick(self.selector, Qt.Key.Key_Escape)
        self.assertFalse(self.window.isVisible())
        self.assertEqual(self.stages, [])
        self.assertIsNone(self.active['worker'])
        self.native.assert_not_called()

    def test_direct_fps_submission_also_shows_progress_before_encoding(self):
        self.deliver_crop(selector_support.Picture(320, 240))
        self.flush()
        self.assertEqual([stage['name'] for stage in self.stages], ['jpeg-save', 'worker-start'])
        self.assertTrue(all(stage['window_visible'] and stage['painted'] for stage in self.stages))

    def test_closed_progress_is_not_reopened_by_late_result(self):
        self.deliver_crop(selector_support.Picture(320, 240))
        self.flush()
        self.active['suppress_result'] = True
        self.window.hide()
        self.active['worker'].finished_text.emit('Késői fordítás.')
        self.flush()
        self.assertFalse(self.window.isVisible())

    def test_hiding_before_first_paint_does_not_stall_or_duplicate_request(self):
        self.deliver_crop(selector_support.Picture(320, 240))
        self.active['suppress_result'] = True
        self.window.hide()
        self.flush()
        self.assertFalse(self.active['preparing'])
        self.assertTrue(self.active['worker'].isRunning())
        self.assertFalse(self.window.isVisible())
        self.assertEqual([stage['name'] for stage in self.stages].count('worker-start'), 1)

    def test_preparing_guard_prevents_duplicate_submissions(self):
        self.deliver_crop(selector_support.Picture(320, 240))
        self.deliver_crop(selector_support.Picture(320, 240))
        self.assertEqual(self.active['generation'], 1)
        self.flush()
        self.assertEqual([stage['name'] for stage in self.stages].count('worker-start'), 1)

    def test_encoding_failure_clears_preparing_state_and_shows_error(self):
        image = selector_support.Picture(320, 240)
        def fail_save(*args, **kwargs):
            raise OSError('Synthetic image encoding error')
        image.save = fail_save
        self.send(image)
        self.flush()
        self.assertFalse(self.active['preparing'])
        self.assertIsNone(self.active['worker'])
        self.assertIn('Fordítási hiba:', self.window.label.toPlainText())

    def test_shutdown_before_first_paint_does_not_start_api_worker(self):
        self.deliver_crop(selector_support.Picture(320, 240))
        self.active['shutting_down'] = True
        self.window.hide()
        self.flush()
        self.assertIsNone(self.active['worker'])
        self.assertFalse(self.active['preparing'])
        self.assertEqual(self.stages, [])

    def test_withheld_paint_watchdog_starts_request_exactly_once(self):
        scheduled = []
        self.window.setUpdatesEnabled(False)
        try:
            with patch.object(self.core.QTimer, 'singleShot', side_effect=lambda delay, callback: scheduled.append((delay, callback))):
                self.deliver_crop(selector_support.Picture(320, 240))
                watchdog = next(callback for delay, callback in scheduled if delay == 1000)
                watchdog()
                start = next(callback for delay, callback in scheduled if delay == 0)
                start()
                before = len(scheduled)
                watchdog()
                self.assertEqual(len(scheduled), before)
        finally:
            self.window.setUpdatesEnabled(True)
        self.flush()
        self.assertFalse(self.active['preparing'])
        self.assertEqual([stage['name'] for stage in self.stages].count('worker-start'), 1)


if __name__ == '__main__':
    unittest.main()

