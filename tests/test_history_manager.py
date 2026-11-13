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
from unittest.mock import patch

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
        self.assertIn("('Ctrl+X', self.cut_selected_history)", text)

    def test_cut_moves_current_record_after_index_shift_and_rename(self):
        original = self.store.items[2]
        self.store.record_id(original)
        clipboard = [copy.deepcopy(original)]
        self.assertTrue(self.store.delete(0))
        self.assertTrue(self.store.rename_folder('Játék', 'Más név'))
        self.assertTrue(self.store.paste_records(clipboard, '', cut=True))
        self.assertEqual(len(self.store.items), 3)
        self.assertEqual(self.store.items[1]['text'], 'Fordítás 2')
        self.assertEqual(self.store.items[1]['folder'], '')
        self.assertEqual(self.store.items[1].get('title'), None)
        self.assertEqual(self.store.items[0]['folder'], 'Más név')

    def test_cut_deleted_source_cannot_move_replacement_at_same_index(self):
        self.store.record_id(self.store.items[0])
        clipboard = [copy.deepcopy(self.store.items[0])]
        self.assertTrue(self.store.delete(0))
        previous = copy.deepcopy(self.store.items)
        self.assertFalse(self.store.paste_records(clipboard, '', cut=True))
        self.assertEqual(self.store.items, previous)

    def test_failed_cut_paste_preserves_source(self):
        self.store.record_id(self.store.items[1])
        clipboard = [copy.deepcopy(self.store.items[1])]
        old = copy.deepcopy(self.store.items)
        self.store.save = lambda: False
        self.assertFalse(self.store.paste_records(clipboard, '', cut=True))
        self.assertEqual(self.store.items, old)

    def test_copy_paste_generates_fresh_identity(self):
        identifier = self.store.record_id(self.store.items[0])
        self.assertTrue(self.store.paste_records([self.store.items[0]], 'Játék'))
        self.assertEqual(len(self.store.items), 5)
        self.assertNotEqual(self.store.items[-1]['_id'], identifier)
        self.assertEqual(self.store.items[0]['folder'], 'Játék')

    def test_mixed_delete_removes_folder_contents_and_explicit_records_once(self):
        self.assertTrue(self.store.create_folder('Marad'))
        self.store.items.extend([dict(text='Külön törlendő'), dict(text='Marad', folder='Marad')])
        self.assertTrue(self.store.delete_selection([0, 4], ['Játék']))
        self.assertEqual(self.store.items, [dict(text='Marad', folder='Marad')])
        self.assertEqual(self.store.folders, ['Marad'])
        restored = self.ns['HistoryStore']()
        self.assertEqual(restored.items, self.store.items)
        self.assertEqual(restored.folders, self.store.folders)

    def test_mixed_delete_can_remove_multiple_empty_folders(self):
        self.store.create_folder('Üres 1')
        self.store.create_folder('Üres 2')
        self.assertTrue(self.store.delete_selection([], ['Üres 1', 'Üres 2']))
        self.assertEqual(len(self.store.items), 4)
        self.assertEqual(self.store.folders, ['Játék'])

    def test_failed_folder_save_rolls_back_history_on_disk(self):
        previous = copy.deepcopy(self.store.items)
        self.store.save_folders = lambda: False
        self.assertFalse(self.store.delete_selection([0], ['Játék']))
        self.assertEqual(self.store.items, previous)
        self.assertEqual(json.loads(self.ns['HISTORY_PATH'].read_text(encoding='utf-8')), previous)
        restored = self.ns['HistoryStore']()
        self.assertEqual(restored.items, previous)
        self.assertEqual(restored.folders, ['Játék'])

    def test_interrupted_folder_delete_is_recovered_on_restart(self):
        previous = copy.deepcopy(self.store.items)
        journal = self.ns['HISTORY_PATH'].with_suffix('.delete-pending.json')
        journal.write_text(json.dumps(dict(items=previous, folders=['Játék'])))
        self.ns['HISTORY_PATH'].write_text('[]')
        self.ns['FOLDERS_PATH'].write_text('[]')
        restored = self.ns['HistoryStore']()
        self.assertEqual(restored.items, previous)
        self.assertEqual(restored.folders, ['Játék'])
        self.assertFalse(journal.exists())

    def test_invalid_pending_delete_is_preserved_and_blocks_writes(self):
        journal = self.ns['HISTORY_PATH'].with_suffix('.delete-pending.json')
        journal.write_text('{broken')
        restored = self.ns['HistoryStore']()
        self.assertFalse(restored.add('New entry'))
        self.assertFalse(restored.create_folder('New folder'))
        self.assertEqual(journal.read_text(encoding='utf-8'), '{broken')

    def test_failed_rollback_can_recover_original_records_after_restart(self):
        previous = copy.deepcopy(self.store.items)
        original_save = self.store.save
        calls = []
        def first_save_only():
            calls.append(True)
            return original_save() if len(calls) == 1 else False
        self.store.save = first_save_only
        self.store.save_folders = lambda: False
        self.assertFalse(self.store.delete_selection([], ['Játék']))
        self.assertEqual(json.loads(self.ns['HISTORY_PATH'].read_text(encoding='utf-8')), [])
        restored = self.ns['HistoryStore']()
        self.assertEqual(restored.items, previous)
        self.assertEqual(restored.folders, ['Játék'])

    def test_damaged_history_preserved_before_next_save(self):
        path = self.ns['HISTORY_PATH']
        for damaged in (b'[{"text":"recoverable translation"},', b'\xff', b'{"unexpected":"object"}'):
            with self.subTest(damaged=damaged):
                path.write_bytes(damaged)
                previous = set(path.parent.glob(path.name + '.corrupt-*'))
                store = self.ns['HistoryStore']()
                self.assertTrue(store.add('New translation'))
                backups = set(path.parent.glob(path.name + '.corrupt-*')) - previous
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups.pop().read_bytes(), damaged)
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))[0]['text'], 'New translation')

    def test_damaged_folders_preserved_before_next_save(self):
        path = self.ns['FOLDERS_PATH']
        damaged = b'["Old game",'
        path.write_bytes(damaged)
        store = self.ns['HistoryStore']()
        self.assertTrue(store.create_folder('New game'))
        backups = list(path.parent.glob(path.name + '.corrupt-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), damaged)

    def test_backup_failure_blocks_overwrite_and_rolls_back_changes(self):
        original_open = Path.open
        def fail_backup(path, mode='r', *args, **kwargs):
            if mode == 'xb':
                raise PermissionError('Backup unavailable')
            return original_open(path, mode, *args, **kwargs)
        for key in ('HISTORY_PATH', 'FOLDERS_PATH'):
            with self.subTest(file=key):
                path = self.ns[key]
                damaged = b'["recoverable data",'
                path.write_bytes(damaged)
                with patch.object(Path, 'open', fail_backup):
                    store = self.ns['HistoryStore']()
                if key == 'HISTORY_PATH':
                    self.assertFalse(store.add('New translation'))
                    self.assertEqual(store.items, [])
                else:
                    self.assertFalse(store.create_folder('New game'))
                    self.assertEqual(store.folders, [])
                self.assertEqual(path.read_bytes(), damaged)

    def test_valid_history_does_not_create_corruption_backup(self):
        store = self.ns['HistoryStore']()
        self.assertEqual(len(store.items), 4)
        self.assertEqual(list(self.ns['HISTORY_PATH'].parent.glob('*.corrupt-*')), [])


if __name__ == '__main__':
    unittest.main()


