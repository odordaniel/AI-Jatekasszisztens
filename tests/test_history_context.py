"""Exercise mixed selections, clipboard and context commands with real Qt rows."""
import unittest
from unittest.mock import patch, Mock
from pathlib import Path
import test_settings_navigation as qt_support

if qt_support.QT_AVAILABLE:
    from PySide6.QtCore import Qt, QItemSelectionModel
    from PySide6.QtWidgets import QPushButton
    from PySide6.QtTest import QTest


@unittest.skipUnless(qt_support.QT_AVAILABLE, 'Qt UI dependencies are not installed')
class HistoryContextTests(unittest.TestCase):
    setUpClass = classmethod(qt_support.SettingsNavigationTests.setUpClass.__func__)
    flush = qt_support.SettingsNavigationTests.flush
    cleanup_windows = qt_support.SettingsNavigationTests.cleanup_windows

    def setUp(self):
        qt_support.SettingsNavigationTests.setUp(self)
        root = Path(self.temp.name)
        self.paths = patch.multiple(self.core, HISTORY_PATH=root / 'history-test.json',
                                    FOLDERS_PATH=root / 'folders-test.json')
        self.paths.start()
        self.addCleanup(self.paths.stop)
        self.core.HISTORY_PATH.unlink(missing_ok=True)
        self.core.FOLDERS_PATH.unlink(missing_ok=True)
        self.history = self.core.HistoryStore()
        self.history.folders = ['Alpha', 'Beta', 'Empty']
        self.history.items = [dict(text='A1', folder='Alpha'), dict(text='A2', folder='Alpha'),
                              dict(text='B1', folder='Beta'), dict(text='Loose', folder='')]
        self.history.save()
        self.history.save_folders()
        self.window.history = self.history
        self.window.sync_folders('')
        self.window.set_history_open(True)
        self.flush()

    def select(self, texts=(), folders=()):
        listing = self.window.history_list
        listing.clearSelection()
        first = None
        for row in range(listing.count()):
            item = listing.item(row)
            value = item.data(Qt.ItemDataRole.UserRole)
            index = self.window.history_index_for_item(item)
            if ((isinstance(value, tuple) and value[1] in folders) or
                    (index is not None and self.history.items[index]['text'] in texts)):
                item.setSelected(True)
                first = first or item
        if first:
            listing.setCurrentItem(first, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.flush()

    def test_cut_paste_moves_all_selected_translations(self):
        self.select(['A1', 'A2'])
        self.window.cut_selected_history()
        self.assertEqual(len(self.history.items), 4)
        self.assertEqual([x['folder'] for x in self.history.items[:2]], ['Alpha', 'Alpha'])
        self.window.open_history_folder('Beta')
        self.window.paste_history()
        self.assertEqual([x['folder'] for x in self.history.items[:3]], ['Beta'] * 3)
        self.assertEqual(len(self.history.items), 4)
        self.assertFalse(self.window._history_clipboard)

    def test_failed_paste_keeps_cut_clipboard_and_sources(self):
        self.select(['A1'])
        self.window.cut_selected_history()
        with patch.object(self.history, 'save', return_value=False):
            self.window.paste_history('Beta')
        self.assertEqual(self.history.items[0]['folder'], 'Alpha')
        self.assertTrue(self.window._history_clipboard_cut)
        self.assertEqual(len(self.window._history_clipboard), 1)

    def test_cut_survives_index_shift_but_never_moves_deleted_source(self):
        self.select(['B1'])
        self.window.cut_selected_history()
        self.history.delete(0)
        self.window.refresh_history()
        self.window.paste_history('')
        self.assertEqual(next(x for x in self.history.items if x['text'] == 'B1')['folder'], '')
        self.select(['A2'])
        self.window.cut_selected_history()
        self.history.delete(0)
        self.window.refresh_history()
        self.window.paste_history('Beta')
        self.assertEqual(next(x for x in self.history.items if x['text'] == 'B1')['folder'], '')
        self.assertTrue(self.window._history_clipboard)

    def test_mixed_delete_removes_every_selected_folder_and_file(self):
        self.select(['A1', 'Loose'], ['Alpha', 'Empty'])
        self.assertEqual(len(self.window.history_list.selectedItems()), 4)
        self.window.delete_selected_history()
        self.assertEqual(len(self.history.items), 4)  # Confirmation has not run.
        self.assertIn('2 mappát és 3 fordítást', self.window.confirm_label.text())
        self.window.confirm_delete()
        self.assertEqual([x['text'] for x in self.history.items], ['B1'])
        self.assertEqual(self.history.folders, ['Beta'])
        self.assertEqual(len(self.window.history_list.selectedItems()), 0)

    def test_right_click_selected_folder_preserves_mixed_selection(self):
        self.select(['Loose'], ['Alpha', 'Empty'])
        listing = self.window.history_list
        folder = next(listing.item(i) for i in range(listing.count())
                      if listing.item(i).data(Qt.ItemDataRole.UserRole) == ('folder', 'Alpha'))
        with patch.object(self.window, 'build_history_menu', return_value=Mock()):
            self.window.history_context_menu(listing.visualItemRect(folder).center())
        self.assertEqual(self.window.selected_folders(), ['Alpha', 'Empty'])
        self.assertEqual(self.window.selected_indices(), [3])
        menu = self.window.build_history_menu()
        self.assertIn('Törlés (Delete)', [action.text() for action in menu.actions()])

    def test_clipboard_cancel_never_changes_source(self):
        self.select(['A1'])
        self.window.cut_selected_history()
        self.window.cancel_history_clipboard()
        self.assertFalse(self.window._history_clipboard)
        self.assertEqual(self.history.items[0]['folder'], 'Alpha')
        self.assertEqual(len(self.history.items), 4)

    def test_paste_on_folder_context_targets_that_folder(self):
        self.select(['Loose'])
        self.window.cut_selected_history()
        self.select(folders=['Beta'])
        menu = self.window.build_history_menu('Beta')
        paste = next(action for action in menu.actions() if action.text() == 'Beillesztés (Ctrl+V)')
        paste.trigger()
        self.assertEqual(self.history.items[3]['folder'], 'Beta')

    def test_context_menu_contains_commands_without_toolbar_buttons(self):
        self.select(['A1'])
        texts = [action.text() for action in self.window.build_history_menu().actions()]
        for caption in ('Megnyitás', 'Átnevezés (F2)', 'Kivágás (Ctrl+X)', 'Másolás (Ctrl+C)',
                        'Beillesztés (Ctrl+V)', 'Törlés (Delete)', 'Új mappa (Ctrl+Shift+N)',
                        'Áthelyezés ide', 'Összes kijelölése (Ctrl+A)', 'Frissítés (F5)'):
            self.assertIn(caption, texts)
        # Only the hidden deletion confirmation retains its confirmation buttons.
        self.assertFalse(any(button.isVisible() for button in self.window.history_panel.findChildren(QPushButton)))

    def test_folder_contents_changed_during_confirmation_require_new_confirmation(self):
        self.select(folders=['Alpha'])
        self.window.delete_selected_history()
        self.history.add('Arrived later', 'Alpha')
        self.window.confirm_delete()
        self.assertEqual(len(self.history.items), 5)
        self.assertIsNotNone(self.window.pending_delete)
        self.assertIn('3 fordítást', self.window.confirm_label.text())
        self.window.confirm_delete()
        self.assertEqual([x['text'] for x in self.history.items], ['B1', 'Loose'])

    def test_refresh_keeps_file_and_folder_selection(self):
        self.select(['B1'], ['Empty'])
        self.window.refresh_history()
        self.assertEqual(self.window.selected_folders(), ['Empty'])
        self.assertEqual(self.window.selected_indices(), [2])
        self.history.delete(0)
        self.window.refresh_history()
        self.assertEqual(self.window.selected_indices(), [1])
        self.assertEqual(self.window.selected_folders(), ['Empty'])

    def test_cancel_delete_preserves_files_and_folders(self):
        self.select(['Loose'], ['Alpha'])
        self.window.delete_selected_history()
        self.window.cancel_delete()
        self.window.confirm_delete()
        self.assertEqual(len(self.history.items), 4)
        self.assertEqual(len(self.history.folders), 3)

    def test_rename_escape_does_not_conflict_with_cut_cancel(self):
        self.select(['A1'])
        self.window.cut_selected_history()
        self.window.rename_selected()
        self.flush()
        self.assertFalse(self.window.edit_panel.isHidden())
        QTest.keyClick(self.window.edit_input, Qt.Key.Key_Escape)
        self.flush()
        self.assertTrue(self.window.edit_panel.isHidden())
        self.assertTrue(self.window._history_clipboard_cut)

    def test_keyboard_cut_and_paste_shortcuts(self):
        self.select(['A1', 'A2'])
        self.window.activateWindow()
        self.window.history_list.setFocus()
        self.flush()
        QTest.keyClick(self.window.history_list, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
        self.flush()
        self.assertTrue(self.window._history_clipboard_cut)
        self.window.open_history_folder('Beta')
        self.window.history_list.setFocus()
        QTest.keyClick(self.window.history_list, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.flush()
        self.assertEqual([entry['folder'] for entry in self.history.items[:3]], ['Beta'] * 3)


if __name__ == '__main__':
    unittest.main()
