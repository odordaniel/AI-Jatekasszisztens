"""Selector frame lifecycle with real Qt painting and synthetic screen data."""
import ast
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import test_settings_navigation as qt_support

if qt_support.QT_AVAILABLE:
    from PySide6.QtCore import Qt, QRect, QPoint, Signal
    from PySide6.QtGui import QPainter, QColor, QPen
    from PySide6.QtWidgets import QApplication, QWidget
    from PySide6.QtTest import QTest


class Picture:
    def __init__(self, width, height, box=None):
        self.width, self.height, self.box = width, height, box

    def crop(self, box):
        return Picture(box[2] - box[0], box[3] - box[1], box)


@unittest.skipUnless(qt_support.QT_AVAILABLE, 'Qt UI dependencies are not installed')
class RegionSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / 'src' / 'assistant.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        selector = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'RegionSelector')
        namespace = dict(QWidget=QWidget, Qt=Qt, QRect=QRect, QPoint=QPoint,
                         Signal=Signal, QPainter=QPainter, QColor=QColor, QPen=QPen,
                         QApplication=QApplication)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[selector], type_ignores=[])),
                     str(source), 'exec'), namespace)
        base = namespace['RegionSelector']
        class Probe(base):
            def __init__(self):
                super().__init__()
                self.frames = []
                self.last_frame_at_hide = None

            def paintEvent(self, event):
                super().paintEvent(event)
                self.frames.append((self.origin, self.current))

            def hideEvent(self, event):
                self.last_frame_at_hide = self.frames[-1] if self.frames else None
                super().hideEvent(event)
        cls.Selector = Probe
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.captures = []
        self.capture_error = None
        owner = self
        class Screen:
            monitors = [None, dict(left=0, top=0, width=320, height=240)]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def grab(self, monitor):
                if owner.capture_error:
                    raise owner.capture_error
                owner.captures.append(monitor)
                return SimpleNamespace(size=(320, 240), rgb=b'\0' * (320 * 240 * 3))
        mss = ModuleType('mss')
        mss.MSS = Screen
        pil = ModuleType('PIL')
        pil.Image = SimpleNamespace(frombytes=lambda mode, size, data: Picture(*size))
        modules = patch.dict(sys.modules, {'mss': mss, 'PIL': pil})
        modules.start()
        self.addCleanup(modules.stop)
        self.selector = self.Selector()
        self.results = []
        self.selector.selected.connect(self.results.append)
        self.addCleanup(self.cleanup_selector)

    def flush(self):
        for _ in range(3):
            self.app.processEvents()

    def cleanup_selector(self):
        self.selector.close()
        self.selector.deleteLater()
        self.flush()

    def begin(self):
        self.selector.begin()
        self.selector.setGeometry(0, 0, 320, 240)
        self.flush()

    def drag(self, end=QPoint(120, 110) if qt_support.QT_AVAILABLE else None):
        QTest.mousePress(self.selector, Qt.MouseButton.LeftButton, pos=QPoint(20, 30))
        QTest.mouseMove(self.selector, end)
        self.flush()
        self.assertIsNotNone(self.selector.origin)
        self.assertTrue(any(origin is not None for origin, current in self.selector.frames))

    def assert_clean_dismissal(self):
        self.assertFalse(self.selector.isVisible())
        self.assertIsNone(self.selector.origin)
        self.assertIsNone(self.selector.current)
        self.assertIsNone(self.selector.image)
        self.assertEqual(self.selector.last_frame_at_hide, (None, None))

    def test_success_repaints_clean_frame_before_hiding_and_preserves_crop(self):
        self.begin()
        self.drag()
        QTest.mouseRelease(self.selector, Qt.MouseButton.LeftButton, pos=QPoint(120, 110))
        self.assert_clean_dismissal()
        self.assertEqual(len(self.results), 1)
        self.assertEqual(self.results[0].box, (20, 30, 121, 111))

    def test_cancel_repaints_clean_frame_before_hiding_without_emitting(self):
        self.begin()
        self.drag()
        QTest.keyClick(self.selector, Qt.Key.Key_Escape)
        self.assert_clean_dismissal()
        self.assertEqual(self.results, [])

    def test_tiny_selection_is_discarded_with_clean_last_frame(self):
        self.begin()
        self.drag(QPoint(24, 34))
        QTest.mouseRelease(self.selector, Qt.MouseButton.LeftButton, pos=QPoint(24, 34))
        self.assert_clean_dismissal()
        self.assertEqual(self.results, [])

    def test_window_close_cleans_the_last_frame(self):
        self.begin()
        self.drag()
        self.selector.close()
        self.assert_clean_dismissal()
        self.assertEqual(self.results, [])

    def test_reopen_has_no_old_cutout_or_border(self):
        for _ in range(4):
            self.begin()
            self.drag()
            self.selector.cancel()
            self.assert_clean_dismissal()
            start = len(self.selector.frames)
            self.begin()
            self.assertTrue(self.selector.frames[start:])
            self.assertTrue(all(frame == (None, None) for frame in self.selector.frames[start:]))
            image = self.selector.grab().toImage()
            self.assertEqual(image.pixelColor(60, 70), QColor(0, 0, 0, 85))
            self.assertEqual(image.pixelColor(20, 30), QColor(0, 0, 0, 85))
            self.selector.cancel()

    def test_repeated_hotkey_does_not_capture_its_own_visible_overlay(self):
        self.begin()
        self.drag()
        self.selector.begin()
        self.assertEqual(len(self.captures), 1)
        self.assertEqual(self.selector.origin, QPoint(20, 30))

    def test_capture_failure_does_not_retain_previous_selection_or_image(self):
        self.selector.origin = QPoint(10, 10)
        self.selector.current = QPoint(50, 50)
        self.selector.image = Picture(320, 240)
        self.capture_error = OSError('Synthetic capture failure')
        with self.assertRaises(OSError):
            self.selector.begin()
        self.assertFalse(self.selector.isVisible())
        self.assertIsNone(self.selector.origin)
        self.assertIsNone(self.selector.current)
        self.assertIsNone(self.selector.image)


if __name__ == '__main__':
    unittest.main()
