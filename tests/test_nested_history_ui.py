"""Real Qt coverage for nested navigation, counts, preview and explicit focus."""
import unittest
from unittest.mock import patch
import test_history_context as context_support
import test_settings_navigation as qt_support

if qt_support.QT_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest


@unittest.skipUnless(qt_support.QT_AVAILABLE, 'Qt UI dependencies are not installed')
class NestedHistoryUITests(unittest.TestCase):
    setUpClass = classmethod(context_support.HistoryContextTests.setUpClass.__func__)
    setUp = context_support.HistoryContextTests.setUp
    flush = context_support.HistoryContextTests.flush
    cleanup_windows = context_support.HistoryContextTests.cleanup_windows
    select = context_support.HistoryContextTests.select

    def create_child(self, parent='Alpha', title='Dialogues'):
        self.window.open_history_folder(parent)
        self.window.begin_edit('new_folder')
        self.window.edit_input.setText(title)
        self.window.apply_edit()
        self.flush()
        key = self.history.find_folder(title, parent)
        self.assertIsNotNone(key)
        return key

    def test_create_in_current_folder_and_navigate_back(self):
        child = self.create_child()
        self.assertEqual(self.window.selected_folder(), child)
        self.window.open_parent_folder()
        self.assertEqual(self.window.selected_folder(), 'Alpha')
        self.assertTrue(any(self.window.history_list.item(i).data(Qt.ItemDataRole.UserRole) == ('folder', child)
                            for i in range(self.window.history_list.count())))

    def test_folder_context_new_command_creates_inside_clicked_folder(self):
        menu = self.window.build_history_menu('Beta')
        next(action for action in menu.actions() if action.text() == 'Új mappa (Ctrl+Shift+N)').trigger()
        self.window.edit_input.setText('Chapter 1')
        self.window.apply_edit()
        self.assertEqual(self.window.selected_folder(), self.history.find_folder('Chapter 1', 'Beta'))

    def test_counts_and_paths_update_after_move(self):
        child = self.create_child()
        self.history.move_many([0, 1], child)
        self.window.sync_folders('Alpha')
        row = next(self.window.history_list.item(i) for i in range(self.window.history_list.count())
                   if self.window.history_list.item(i).data(Qt.ItemDataRole.UserRole) == ('folder', child))
        self.assertIn('2 fordítás', row.text())
        caption = self.window.folder_filter.itemText(self.window.folder_filter.findData(child))
        self.assertIn('Alpha / Dialogues', caption)
        self.assertIn('2 fordítás', caption)
        self.history.move_many([1], 'Beta')
        self.window.refresh_history()
        caption = self.window.folder_filter.itemText(self.window.folder_filter.findData(child))
        self.assertIn('1 fordítás', caption)

    def test_single_click_previews_in_top_field_without_collapsing_list(self):
        listing = self.window.history_list
        item = next(listing.item(i) for i in range(listing.count())
                    if (index := self.window.history_index_for_item(listing.item(i))) is not None
                    and self.history.items[index]['text'] == 'B1')
        self.window.label.setPlainText('Previous translation')
        geometry = self.window.geometry()
        listing.scrollToItem(item)
        self.flush()
        QTest.mouseClick(listing.viewport(), Qt.MouseButton.LeftButton,
                         pos=listing.visualItemRect(item).center())
        self.flush()
        self.assertEqual(self.window.label.toPlainText(), 'B1')
        self.assertFalse(self.window.history_panel.isHidden())
        self.assertEqual(self.window.geometry(), geometry)

    def test_keyboard_current_row_previews_translation(self):
        self.select(['A2'])
        self.assertEqual(self.window.label.toPlainText(), 'A2')

    def test_explicit_history_open_activates_window_and_list(self):
        self.window._history_preference = False
        self.window.set_history_open(False)
        self.window.hide()
        with patch('window_focus.activate_window', return_value=False) as native:
            self.window.show_history_from_hotkey()
            self.flush()
            native.assert_called_once_with(int(self.window.winId()))
        self.assertFalse(self.window.history_panel.isHidden())
        self.assertFalse(self.window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertTrue(self.window.isVisible())
        # The offscreen platform can reject foreground activation; the intended
        # Qt focus target must still be the list. Native activation is covered
        # separately by the Win32 contract tests.
        self.assertIs(self.window.focusWidget(), self.window.history_list)

    def test_automatic_translation_does_not_use_explicit_history_activation(self):
        with patch('window_focus.activate_window', return_value=True) as native:
            self.window.prepare_translation()
            self.window.show_message('Translated text')
            self.flush()
            native.assert_not_called()

    def test_new_empty_descendant_during_delete_requires_reconfirmation(self):
        self.select(folders=['Alpha'])
        self.window.delete_selected_history()
        self.history.create_folder('New empty child', 'Alpha')
        self.window.confirm_delete()
        self.assertIn('Alpha', self.history.folders)
        self.assertIn('2 mappát', self.window.confirm_label.text())
        self.window.confirm_delete()
        self.assertNotIn('Alpha', self.history.folders)
        self.assertEqual(self.history.folder_parents, {})


if __name__ == '__main__':
    unittest.main()
