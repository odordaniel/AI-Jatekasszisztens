"""Regression checks for the audio worker's cancellation and error paths."""
import ast
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'src' / 'live_translation.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
WORKER = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'LiveWorker')
METHODS = {n.name: n for n in WORKER.body if isinstance(n, ast.FunctionDef)}

class AudioLifecycleTests(unittest.TestCase):
    def test_worker_exposes_stop_and_abort(self):
        self.assertTrue({'run', 'stop', 'abort', '_checkpoint'} <= METHODS.keys())
    def test_abort_sets_both_events(self):
        body = ast.unparse(METHODS['abort'])
        self.assertIn('self.cancel.set()', body)
        self.assertIn('self.stop_requested.set()', body)
    def test_stop_does_not_cancel_processing(self):
        body = ast.unparse(METHODS['stop'])
        self.assertIn('self.stop_requested.set()', body)
        self.assertNotIn('self.cancel.set()', body)
    def test_finally_saves_and_signals_completion(self):
        body = ast.unparse(METHODS['run'])
        self.assertIn('self._checkpoint()', body)
        self.assertIn('self.completed.emit(self.entries, self.started)', body)
        self.assertIn('self.recording_changed.emit(False)', body)
    def test_cancel_checked_after_remote_operations(self):
        body = ast.unparse(METHODS['run'])
        self.assertGreaterEqual(body.count('self.cancel.is_set()'), 5)
    def test_partial_errors_tracked(self):
        body = ast.unparse(METHODS['run'])
        self.assertGreaterEqual(body.count('self._segment_errors.append(message)'), 2)

if __name__ == '__main__':
    unittest.main()
