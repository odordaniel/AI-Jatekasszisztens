"""Exercise production main closures with deterministic timers and fake workers."""
import ast
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'src' / 'assistant.py'
MAIN = next(n for n in ast.parse(SOURCE.read_text(encoding='utf-8')).body
            if isinstance(n, ast.FunctionDef) and n.name == 'main')


class LifecycleAuditTests(unittest.TestCase):
    def setUp(self):
        self.pending = []
        self.active = dict(worker=None, preparing=False, capturing=False, shutting_down=False)
        self.overlay = Mock(discovery_worker=None)
        self.selector = Mock()
        self.selector.isVisible.return_value = False
        self.live = Mock(worker=None, device_loader=None, model_loader=None, text_model_loader=None)
        self.app = Mock()
        self.ns = dict(active=self.active, overlay=self.overlay, selector=self.selector,
            live_settings=self.live, app=self.app, current_hotkeys={'obj': None},
            shutting_down={'value': False}, QTimer=SimpleNamespace(singleShot=lambda ms, cb: self.pending.append(cb)),
            cfg={}, screenshot_game=Mock(return_value='Game'), logging=logging)
        names = {'translate_center', 'close_current_view', 'shutdown', 'shutdown_after_live'}
        nodes = [n for n in MAIN.body if isinstance(n, ast.FunctionDef) and n.name in names]
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(SOURCE), 'exec'), self.ns)

    def test_repeated_center_hotkey_schedules_only_one_capture(self):
        for _ in range(5):
            self.ns['translate_center']()
        self.assertEqual(len(self.pending), 1)
        self.ns['screenshot_game'].assert_called_once()

    def test_capture_hands_crop_to_translation_and_clears_busy_flag(self):
        capture = Mock()
        capture.__enter__ = Mock(return_value=capture)
        capture.__exit__ = Mock(return_value=False)
        capture.monitors = [{}, dict(left=0, top=0, width=1000, height=800)]
        capture.grab.return_value = SimpleNamespace(size=(550, 320), rgb=b'synthetic')
        image = Mock()
        send = Mock()
        self.ns['send_selection'] = send
        self.ns['translate_center']()
        with patch.dict('sys.modules', {'mss': SimpleNamespace(MSS=lambda: capture),
                'PIL': SimpleNamespace(Image=image)}):
            self.pending.pop()()
        self.assertFalse(self.active['capturing'])
        send.assert_called_once_with(image.frombytes.return_value)
        capture.grab.assert_called_once_with(dict(left=225, top=240, width=550, height=320))

    def test_close_cancels_delayed_capture(self):
        self.ns['translate_center']()
        self.ns['close_current_view']()
        self.pending.pop()()  # Must return before importing mss or taking a screenshot.
        self.assertFalse(self.active['capturing'])

    def test_old_capture_cannot_run_new_request_after_cancel(self):
        self.ns['translate_center']()
        old = self.pending.pop()
        self.ns['close_current_view']()
        self.ns['translate_center']()
        old()
        self.assertTrue(self.active['capturing'])
        self.assertEqual(len(self.pending), 1)

    def test_center_hotkey_during_region_selection_does_nothing(self):
        self.selector.isVisible.return_value = True
        self.ns['translate_center']()
        self.assertEqual(self.pending, [])
        self.overlay.hide.assert_not_called()

    def test_shutdown_waits_for_each_discovery_and_translation_worker(self):
        for owner, attribute in ((self.overlay, 'discovery_worker'), (self.live, 'device_loader'),
                (self.live, 'model_loader'), (self.live, 'text_model_loader'), (self.live, 'worker')):
            with self.subTest(attribute=attribute):
                worker = Mock()
                worker.isRunning.return_value = True
                setattr(owner, attribute, worker)
                self.ns['shutdown_after_live']()
                self.app.quit.assert_not_called()
                worker.isRunning.return_value = False
                self.pending.pop()()
                self.app.quit.assert_called_once()
                self.app.quit.reset_mock()
                setattr(owner, attribute, None)

    def test_shutdown_invalidates_capture_and_blocks_new_screenshot(self):
        self.ns['translate_center']()
        capture = self.pending.pop()
        self.ns['shutdown']()
        capture()
        self.ns['translate_center']()
        self.assertEqual(self.pending, [])
        self.assertTrue(self.active['shutting_down'])
        self.assertTrue(self.active['suppress_result'])
        self.live.request_shutdown.assert_called_once()
        self.app.quit.assert_called_once()
        self.ns['shutdown']()
        self.app.quit.assert_called_once()
