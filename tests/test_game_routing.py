"""Regression tests for game-to-history routing without loading the Qt UI."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'src'
SOURCE = (ROOT / 'assistant.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)


def nested_function(parent, name):
    scope = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == parent)
    return next(node for node in ast.walk(scope) if isinstance(node, ast.FunctionDef) and node.name == name)


def make_detector():
    timer = [100.0]
    recognizer = SimpleNamespace(last_polled_executable='')
    result = [('', '')]
    def poll():
        return result[0]
    recognizer.poll = poll
    recent = {'name': '', 'source': '', 'last_seen': 0.0}
    namespace = {'recognizer': recognizer, 'recent_game': recent,
                 'time': SimpleNamespace(monotonic=lambda: timer[0])}
    node = nested_function('main', 'game_detector')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), 'assistant.py', 'exec'), namespace)
    return namespace['game_detector'], recognizer, result, recent, timer


class GameRoutingTests(unittest.TestCase):
    def test_game_switch_replaces_previous_game(self):
        detect, rec, result, _, _ = make_detector()
        rec.last_polled_executable = r'C:\\Games\\A\\a.exe'
        result[0] = ('Game A', 'Steam')
        self.assertEqual(detect(), 'Game A')
        rec.last_polled_executable = r'C:\\Games\\B\\b.exe'
        result[0] = ('Game B', 'Epic')
        self.assertEqual(detect(), 'Game B')

    def test_unknown_foreground_clears_previous_game(self):
        detect, rec, result, recent, _ = make_detector()
        rec.last_polled_executable = 'known.exe'
        result[0] = ('Known Game', 'Steam')
        self.assertEqual(detect(), 'Known Game')
        rec.last_polled_executable = 'unrecognized.exe'
        result[0] = ('', '')
        self.assertEqual(detect(), '')
        self.assertEqual(recent['name'], '')
        rec.last_polled_executable = ''
        self.assertEqual(detect(), '')

    def test_overlay_focus_short_grace_only(self):
        detect, rec, result, _, clock = make_detector()
        rec.last_polled_executable = 'known.exe'
        result[0] = ('Known Game', 'Steam')
        self.assertEqual(detect(), 'Known Game')
        rec.last_polled_executable = ''
        result[0] = ('', '')
        clock[0] += 10
        self.assertEqual(detect(), 'Known Game')
        clock[0] += 6
        self.assertEqual(detect(), '')

    def test_saved_manual_game_cannot_override_detection(self):
        node = nested_function('main', 'resolved_game')
        namespace = {'game_status_provider': lambda: ('New Game', 'Steam'),
                     'cfg': {'manual_game': 'Old Game'}}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), 'assistant.py', 'exec'), namespace)
        self.assertEqual(namespace['resolved_game'](), 'New Game')
        namespace['game_status_provider'] = lambda: ('', '')
        self.assertEqual(namespace['resolved_game'](), '')

    def test_screenshot_uses_capture_game_not_later_game(self):
        node = nested_function('main', 'send_selection')
        saved_game_assignments = [item for item in ast.walk(node)
                                  if isinstance(item, ast.Assign)
                                  and any(isinstance(target, ast.Name) and target.id == 'saved_game'
                                          for target in item.targets)]
        self.assertEqual(len(saved_game_assignments), 1)
        self.assertNotIn('resolved_game', ast.unparse(saved_game_assignments[0].value))

    def test_field_tracks_recognition_and_not_legacy_config(self):
        refresh = next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef)
                       and n.name == 'refresh_game_status')
        self.assertIn('setText(recognized)', ast.unparse(refresh))
        self.assertNotIn("cfg.get('manual_game'", ast.unparse(refresh))

if __name__ == '__main__':
    unittest.main()
