"""Exercise audio completion and persistence without Windows or Qt."""
import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1] / 'src' / 'live_translation.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
SETTINGS = next(n for n in TREE.body if isinstance(n, ast.ClassDef)
                and n.name == 'LiveTranslationSettings')
COMPLETED = next(n for n in SETTINGS.body if isinstance(n, ast.FunctionDef)
                 and n.name == '_completed')
namespace = {}
exec(compile(ast.fix_missing_locations(ast.Module(body=[COMPLETED], type_ignores=[])),
             str(SOURCE), 'exec'), namespace)
complete = namespace['_completed']


class AudioHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.recovery = Path(temporary.name) / 'recovery.json'
        self.recovery.write_text('recoverable transcript', encoding='utf-8')
        self.view = SimpleNamespace(
            cfg={'show_original': False},
            worker=SimpleNamespace(inferred_game='Example Game',
                                   _segment_errors=[], _fatal_error=''),
            transcript_ready=Mock(), status=Mock(),
            on_history=Mock(return_value=True), recovery_path=self.recovery)
        self.entry = dict(time='00:00:01', speaker='Speaker 1',
                          original='The gate is locked.', magyar='A kapu zárva.', error='')

    def test_hidden_original_is_still_saved(self):
        complete(self.view, [self.entry], '2026-11-12')
        body, game = self.view.on_history.call_args.args
        self.assertIn(self.entry['original'], body)
        self.assertIn(self.entry['magyar'], body)
        self.assertEqual(game, 'Example Game')
        self.assertFalse(self.view.transcript_ready.emit.call_args.args[-1])
        self.assertFalse(self.recovery.exists())

    def test_failed_translation_preserves_original_and_error(self):
        self.entry.update(magyar='', error='HTTP 503')
        self.view.worker._segment_errors = ['HTTP 503']
        complete(self.view, [self.entry], '2026-11-12')
        body = self.view.on_history.call_args.args[0]
        self.assertIn(self.entry['original'], body)
        self.assertIn('Fordítás nem sikerült: HTTP 503', body)

    def test_failed_history_save_keeps_recovery(self):
        self.view.on_history.return_value = False
        complete(self.view, [self.entry], '2026-11-12')
        self.assertEqual(self.recovery.read_text(), 'recoverable transcript')

    def test_show_original_does_not_duplicate_saved_source(self):
        self.view.cfg['show_original'] = True
        complete(self.view, [self.entry], '2026-11-12')
        body = self.view.on_history.call_args.args[0]
        self.assertEqual(body.count(self.entry['original']), 1)
        self.assertTrue(self.view.transcript_ready.emit.call_args.args[-1])


if __name__ == '__main__':
    unittest.main()
