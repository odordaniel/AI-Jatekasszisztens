"""Folder hierarchy persistence and subtree operations without GUI dependencies."""
import copy
import json
import unittest
import test_history_manager as storage_support


class NestedFolderTests(unittest.TestCase):
    setUp = storage_support.HistoryManagerTests.setUp

    def child(self, title, parent):
        self.assertTrue(self.store.create_folder(title, parent))
        key = self.store.find_folder(title, parent)
        self.assertIsNotNone(key)
        return key

    def test_nested_folders_persist_with_same_names_under_different_parents(self):
        self.store.create_folder('Másik játék')
        first = self.child('Párbeszédek', 'Játék')
        second = self.child('Párbeszédek', 'Másik játék')
        grandchild = self.child('Első fejezet', first)
        self.assertNotEqual(first, second)
        self.assertFalse(self.store.create_folder('párbeszédek', 'Játék'))
        loaded = self.ns['HistoryStore']()
        self.assertEqual(loaded.find_folder('Párbeszédek', 'Játék'), first)
        self.assertEqual(loaded.folder_path(grandchild), 'Játék / Párbeszédek / Első fejezet')
        self.assertEqual(loaded.child_folders('Játék'), [first])
        self.assertEqual(json.loads(self.ns['FOLDERS_PATH'].read_text(encoding='utf-8'))['version'], 2)

    def test_legacy_names_containing_separators_are_not_reinterpreted(self):
        legacy = ['Játék / DLC', 'Játék\\Másik']
        self.ns['FOLDERS_PATH'].write_text(json.dumps(legacy), encoding='utf-8')
        loaded = self.ns['HistoryStore']()
        self.assertEqual(loaded.child_folders(), legacy)
        self.assertEqual(loaded.folder_parents, {})

    def test_counts_include_all_descendants_and_follow_moves(self):
        child = self.child('Párbeszédek', 'Játék')
        grandchild = self.child('Első fejezet', child)
        self.store.items.extend([dict(text='Child', folder=child), dict(text='Grandchild', folder=grandchild)])
        counts = self.store.folder_counts()
        self.assertEqual((counts['Játék'], counts[child], counts[grandchild]), (6, 2, 1))
        self.assertTrue(self.store.move_many([5], ''))
        counts = self.store.folder_counts()
        self.assertEqual((counts['Játék'], counts[child], counts[grandchild]), (5, 1, 0))

    def test_renaming_ancestors_keeps_records_and_child_links(self):
        child = self.child('Párbeszédek', 'Játék')
        grandchild = self.child('Fejezet', child)
        self.store.items.append(dict(text='Nested', folder=grandchild))
        self.assertTrue(self.store.rename_folder('Játék', 'Új játék'))
        self.assertTrue(self.store.rename_folder(child, 'Dialógusok'))
        loaded = self.ns['HistoryStore']()
        self.assertEqual(loaded.folder_path(grandchild), 'Új játék / Dialógusok / Fejezet')
        self.assertEqual(loaded.items[-1]['folder'], grandchild)
        self.assertEqual(loaded.items[0]['folder'], 'Új játék')

    def test_subtree_delete_deduplicates_descendants_and_records(self):
        child = self.child('Párbeszédek', 'Játék')
        grandchild = self.child('Fejezet', child)
        self.store.items.extend([dict(text='Nested', folder=grandchild), dict(text='Unsorted', folder='')])
        self.assertTrue(self.store.delete_selection([4], ['Játék', child]))
        self.assertEqual(self.store.folders, [])
        self.assertEqual(self.store.folder_parents, {})
        self.assertEqual(self.store.items, [dict(text='Unsorted', folder='')])

    def test_failed_nested_delete_preserves_hierarchy_on_restart(self):
        child = self.child('Párbeszédek', 'Játék')
        self.store.items.append(dict(text='Nested', folder=child))
        self.store.save()
        previous = copy.deepcopy(self.store.items)
        self.store.save_folders = lambda: False
        self.assertFalse(self.store.delete_selection([], ['Játék']))
        loaded = self.ns['HistoryStore']()
        self.assertEqual(loaded.items, previous)
        self.assertEqual(loaded.folder_parents[child], 'Játék')
        self.assertEqual(loaded.folder_title(child), 'Párbeszédek')

    def test_failed_create_does_not_leave_orphan_metadata(self):
        self.store.save_folders = lambda: False
        self.assertFalse(self.store.create_folder('Párbeszédek', 'Játék'))
        self.assertEqual(self.store.folders, ['Játék'])
        self.assertEqual(self.store.folder_parents, {})
        self.assertEqual(self.store.folder_titles, {})

    def test_game_save_uses_root_even_if_child_has_same_title(self):
        self.store.create_folder('Másik játék')
        child = self.child('Játék', 'Másik játék')
        self.assertTrue(self.store.add('Game translation', 'Játék'))
        self.assertEqual(self.store.items[-1]['folder'], 'Játék')
        self.assertEqual(self.store.folder_counts()[child], 0)

    def test_missing_parent_rejected(self):
        self.assertFalse(self.store.create_folder('Child', 'Missing'))
        self.assertEqual(self.store.folders, ['Játék'])

    def test_cyclic_folder_file_is_backed_up_before_replacement(self):
        invalid = {'version': 2, 'folders': [dict(id='a', name='A', parent='b'), dict(id='b', name='B', parent='a')]}
        self.ns['FOLDERS_PATH'].write_text(json.dumps(invalid), encoding='utf-8')
        loaded = self.ns['HistoryStore']()
        self.assertEqual(loaded.folders, [])
        backups = list(self.ns['FOLDERS_PATH'].parent.glob('folders.json.corrupt-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding='utf-8')), invalid)


if __name__ == '__main__':
    unittest.main()
