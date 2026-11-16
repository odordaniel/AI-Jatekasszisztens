"""Interrupted two-file mutations and deep history trees."""
import copy
import unittest
from unittest.mock import patch
import test_history_manager as support


class AuditStorageTests(unittest.TestCase):
    setUp = support.HistoryManagerTests.setUp

    def test_interrupted_rename_restores_records_and_child_links_on_restart(self):
        self.store.create_folder('Child', 'Játék')
        old_items = copy.deepcopy(self.store.items)
        old_folders = list(self.store.folders)
        old_parents = dict(self.store.folder_parents)
        with patch.object(self.store, 'save_folders', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.store.rename_folder('Játék', 'Renamed')
        reloaded = self.ns['HistoryStore']()
        self.assertEqual(reloaded.items, old_items)
        self.assertEqual(reloaded.folders, old_folders)
        self.assertEqual(reloaded.folder_parents, old_parents)
        self.assertFalse(self.ns['HISTORY_PATH'].with_suffix('.delete-pending.json').exists())

    def test_interrupted_preserve_records_delete_restores_on_restart(self):
        with patch.object(self.store, 'save_folders', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.store.delete_folder('Játék')
        reloaded = self.ns['HistoryStore']()
        self.assertIn('Játék', reloaded.folders)
        self.assertTrue(all(x['folder'] == 'Játék' for x in reloaded.items))

    def test_failed_rollback_retains_journal_and_blocks_later_writes(self):
        with patch.object(self.store, 'save_folders', return_value=False):
            self.assertFalse(self.store.rename_folder('Játék', 'Renamed'))
        self.assertFalse(self.store.add('New record'))
        self.assertTrue(self.ns['HISTORY_PATH'].with_suffix('.delete-pending.json').exists())
        self.assertIn('Játék', self.ns['HistoryStore']().folders)

    def test_failed_journal_creation_never_changes_data(self):
        before = copy.deepcopy(self.store.items)
        journal = self.ns['HISTORY_PATH'].with_suffix('.delete-pending.json')
        journal.mkdir()
        self.assertFalse(self.store.rename_folder('Játék', 'Renamed'))
        self.assertEqual(self.store.items, before)
        self.assertEqual(self.store.folders, ['Játék'])

    def test_deep_tree_counts_include_descendants_without_recursion(self):
        depth = 2000
        self.store.folders = [str(i) for i in range(depth)]
        self.store.folder_parents = {str(i): str(i-1) for i in range(1, depth)}
        self.store.items = [dict(text='text', folder=str(depth-1)) for _ in range(1000)]
        self.store.items.append(dict(text='root', folder='0'))
        counts = self.store.folder_counts()
        self.assertEqual(counts['0'], 1001)
        self.assertEqual(counts[str(depth-1)], 1000)
        self.assertEqual(len(self.store.descendant_folders(['0'])), depth)
        self.assertEqual(self.store.descendant_folders([str(depth-1)]), {str(depth-1)})
