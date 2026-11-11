"""Behavioral tests for JSON-backed bulk history operations, without Qt dependencies."""
import ast
import copy
import json
import logging
import tempfile
import threading
import unittest
from pathlib import Path
from datetime import datetime

SOURCE = Path(__file__).resolve().parents[1] / 'src' / 'assistant.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
STORE = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == 'HistoryStore')


class HistoryManagerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.ns = {'_STORAGE_LOCK': threading.RLock(), 'HISTORY_PATH': root / 'history.json',
                   'FOLDERS_PATH': root / 'folders.json', 'json': json, 'logging': logging,
                   'datetime': datetime, 'copy': copy}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[STORE], type_ignores=[])), str(SOURCE), 'exec'), self.ns)
        self.store = self.ns['HistoryStore']()
        self.assertTrue(self.store.create_folder('Játék'))
        self.store.items = [dict(text=f'Fordítás {i}', folder='Játék', time=str(i)) for i in range(4)]
        self.assertTrue(self.store.save())

    def test_copy_many_preserves_originals(self):
        self.assertTrue(self.store.copy_many([1, 3], ''))
        self.assertEqual(len(self.store.items), 6)
        self.assertEqual([x['folder'] for x in self.store.items[-2:]], ['', ''])
        self.assertEqual(self.store.items[1]['text'], 'Fordítás 1')
        self.assertIn('másolat', self.store.items[-1]['title'])

    def test_move_many_and_reject_unknown_folder(self):
        self.assertFalse(self.store.move_many([0, 1], 'Nemlétező'))
        self.assertTrue(self.store.move_many([0, 2], ''))
        self.assertEqual([x.get('folder') for x in self.store.items], ['', 'Játék', '', 'Játék'])

    def test_bulk_delete_keeps_order(self):
        self.assertTrue(self.store.delete_many([1, 3]))
        self.assertEqual([x['text'] for x in self.store.items], ['Fordítás 0', 'Fordítás 2'])
        self.assertEqual(len(json.loads(self.ns['HISTORY_PATH'].read_text(encoding='utf-8'))), 2)

    def test_failed_save_rolls_back_bulk_operations(self):
        original = copy.deepcopy(self.store.items)
        self.store.save = lambda: False
        self.assertFalse(self.store.copy_many([0, 1], ''))
        self.assertEqual(original, self.store.items)
        self.assertFalse(self.store.move_many([0, 1], ''))
        self.assertEqual(original, self.store.items)
        self.assertFalse(self.store.delete_many([0, 1]))
        self.assertEqual(original, self.store.items)

    def test_bad_index_rejected_without_mutation(self):
        original = copy.deepcopy(self.store.items)
        self.assertFalse(self.store.delete_many([999]))
        self.assertFalse(self.store.move_many([-1], ''))
        self.assertFalse(self.store.copy_many([0, 999], ''))
        self.assertEqual(original, self.store.items)

    def test_ui_has_context_menu_and_multiselect(self):
        text = SOURCE.read_text(encoding='utf-8')
        self.assertIn('SelectionMode.ExtendedSelection', text)
        self.assertIn('customContextMenuRequested.connect(self.history_context_menu)', text)
        self.assertIn("('Ctrl+C', self.copy_selected_history)", text)
        self.assertIn("('Ctrl+V', self.paste_history)", text)
        self.assertIn("('Delete', self.delete_selected_history)", text)


if __name__ == '__main__':
    unittest.main()
