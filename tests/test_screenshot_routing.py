"""Screenshot-specific game detection regression checks, Qt-free."""
import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'src'
SRC = (ROOT / 'assistant.py').read_text(encoding='utf-8')
TREE = ast.parse(SRC)
MAIN = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'main')

def function(name):
    return next(n for n in MAIN.body if isinstance(n, ast.FunctionDef) and n.name == name)

class ScreenshotRoutingTests(unittest.TestCase):
    def setUp(self):
        self.recognizer = SimpleNamespace(last_polled_executable='', last_running=lambda: ('Example Game', 'Steam'))
        self.detected = ''
        ns = {'recognizer': self.recognizer, 'resolved_game': lambda: self.detected}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function('screenshot_game')], type_ignores=[])),
                     str(ROOT / 'assistant.py'), 'exec'), ns)
        self.screenshot_game = ns['screenshot_game']
        sys.path.insert(0, str(ROOT))

    def test_game_in_foreground_has_priority(self):
        self.detected = 'New Game'
        self.assertEqual(self.screenshot_game(), 'New Game')

    def test_own_selector_carries_still_running_game(self):
        with patch('game_detection.foreground_is_ours', return_value=True):
            self.assertEqual(self.screenshot_game(), 'Example Game')

    def test_tray_capture_carries_still_running_game(self):
        self.recognizer.last_polled_executable = r'C:\\Windows\\explorer.exe'
        with patch('game_detection.foreground_is_ours', return_value=False):
            self.assertEqual(self.screenshot_game(from_tray=True), 'Example Game')

    def test_unrecognized_foreground_never_reuses_old_game(self):
        self.recognizer.last_polled_executable = r'C:\\Games\\unknown.exe'
        with patch('game_detection.foreground_is_ours', return_value=False):
            self.assertEqual(self.screenshot_game(), '')

    def test_exited_game_does_not_get_old_folder(self):
        self.recognizer.last_running = lambda: ('', '')
        with patch('game_detection.foreground_is_ours', return_value=True):
            self.assertEqual(self.screenshot_game(), '')
            self.assertEqual(self.screenshot_game(from_tray=True), '')

    def test_both_screenshot_entry_points_use_snapshot(self):
        for name in ('translate', 'translate_center'):
            code = ast.unparse(function(name))
            self.assertIn('screenshot_game(from_tray=from_tray)', code)
        code = ast.unparse(function('send_selection'))
        self.assertIn("saved_game = active.get('game', '')", code)

    def test_tray_action_passes_tray_context(self):
        code = ast.unparse(MAIN)
        self.assertIn('translate(from_tray=True)', code)
        self.assertIn('translate_center(from_tray=True)', code)

if __name__ == '__main__':
    unittest.main()
