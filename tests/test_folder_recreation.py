"""Regression tests for game folder deletion and saving during UI focus."""
import ast
import copy
from datetime import datetime
import json
import logging
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'src'
SRC = (ROOT / 'assistant.py').read_text(encoding='utf-8')
TREE = ast.parse(SRC)
STORE = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == 'HistoryStore')
MAIN = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
DETECTOR = next(node for node in ast.walk(MAIN) if isinstance(node, ast.FunctionDef) and node.name == 'game_detector')


class FolderRecreationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name)
        ns = {'_STORAGE_LOCK': threading.RLock(), 'HISTORY_PATH': path / 'history.json',
              'FOLDERS_PATH': path / 'folders.json', 'json': json,
              'logging': logging, 'datetime': datetime, 'copy': copy}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[STORE], type_ignores=[])),
                     str(ROOT / 'assistant.py'), 'exec'), ns)
        self.store = ns['HistoryStore']()
        self.ns = ns

    def test_folder_deleted_during_game_is_recreated_on_save(self):
        self.assertTrue(self.store.add('Első fordítás', 'Example Game'))
        self.assertTrue(self.store.delete_folder('Example Game'))
        self.assertEqual(self.store.items[0].get('folder', ''), '')
        self.assertTrue(self.store.add('Második fordítás', 'Example Game'))
        self.assertIn('Example Game', self.store.folders)
        self.assertEqual(self.store.items[-1]['folder'], 'Example Game')
        self.assertIn('Example Game', json.loads(self.ns['FOLDERS_PATH'].read_text(encoding='utf-8')))
        self.assertEqual(json.loads(self.ns['HISTORY_PATH'].read_text(encoding='utf-8'))[-1]['folder'], 'Example Game')

    def test_folder_failure_does_not_route_known_game_to_unsorted(self):
        self.store.create_folder = lambda name: False
        self.assertFalse(self.store.add('Nem veszíthet mappát', 'Example Game'))
        self.assertEqual(self.store.items, [])

    def test_unknown_game_stays_unsorted(self):
        self.assertTrue(self.store.add('Ismeretlen játék', ''))
        self.assertEqual(self.store.items[-1].get('folder', ''), '')
        self.assertEqual(self.store.folders, [])

    def test_own_overlay_keeps_only_still_running_recognized_game(self):
        import sys
        sys.path.insert(0, str(ROOT))
        recognizer = SimpleNamespace(last_polled_executable='')
        result = [('Example Game', 'Steam')]
        recognizer.poll = lambda: result[0]
        recognizer.last_running = lambda: ('Example Game', 'Steam')
        game = {'name': '', 'source': '', 'last_seen': 0.0}
        clock = [100.0]
        namespace = {'recognizer': recognizer, 'recent_game': game,
                     'time': SimpleNamespace(monotonic=lambda: clock[0])}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[DETECTOR], type_ignores=[])),
                     'assistant.py', 'exec'), namespace)
        detect = namespace['game_detector']
        self.assertEqual(detect(), 'Example Game')
        clock[0] += 120
        result[0] = ('', '')
        with patch('game_detection.foreground_is_ours', return_value=True):
            self.assertEqual(detect(), 'Example Game')
            recognizer.last_running = lambda: ('', '')  # Game process exited
            self.assertEqual(detect(), '')
        self.assertEqual(game['name'], '')
        # Unknown, non-game foreground process must not inherit the last game.
        recognizer.last_polled_executable = 'other.exe'
        result[0] = ('', '')
        self.assertEqual(detect(), '')

if __name__ == '__main__':
    unittest.main()
