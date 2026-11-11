"""Dependency-free regression checks for the targeted performance paths."""
import ast
import io
import wave
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'
ASSISTANT = ast.parse((ROOT / 'assistant.py').read_text(encoding='utf-8'))
AUDIO = ast.parse((ROOT / 'live_translation.py').read_text(encoding='utf-8'))


def find_function(tree, name):
    matches = [node for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise AssertionError(f'Expected one function named {name}, got {len(matches)}')
    return matches[0]


class PerformancePathTests(unittest.TestCase):
    def test_screenshot_imports_not_eager(self):
        imports = [node for node in ASSISTANT.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any(isinstance(node, ast.Import) and
                             any(alias.name == 'mss' for alias in node.names) for node in imports))
        self.assertFalse(any(isinstance(node, ast.ImportFrom) and node.module == 'PIL'
                             for node in imports))
        for function in ('begin', 'capture_center'):
            code = ast.unparse(find_function(ASSISTANT, function))
            self.assertIn('import mss', code)
            self.assertIn('from PIL import Image', code)

    def test_center_capture_only_grabs_selected_rectangle(self):
        code = ast.unparse(find_function(ASSISTANT, 'capture_center'))
        self.assertIn('sct.grab(region)', code)
        self.assertNotIn('sct.grab(sct.monitors[1])', code)
        self.assertNotIn('image.crop(', code)

    def test_history_search_is_debounced(self):
        code = (ROOT / 'assistant.py').read_text(encoding='utf-8')
        self.assertIn('self._history_search_timer.setSingleShot(True)', code)
        self.assertIn('self._history_search_timer.timeout.connect(self.refresh_history)', code)
        self.assertIn('self._history_search_timer.stop()', ast.unparse(find_function(ASSISTANT, 'refresh_history')))

    def test_tooltips_built_on_hover_not_for_every_row(self):
        self.assertIn('self.history_tooltip(', ast.unparse(find_function(ASSISTANT, '_show_history_tooltip')))
        self.assertNotIn('self.history_tooltip(', ast.unparse(find_function(ASSISTANT, 'refresh_history')))

    def test_audio_clip_final_header_after_raw_blocks(self):
        worker = next(node for node in AUDIO.body if isinstance(node, ast.ClassDef) and node.name == 'LiveWorker')
        code = ast.unparse(find_function(worker, 'run'))
        self.assertIn('current.writeframesraw(', code)
        # Wave header remains valid when a recording is split into raw blocks.
        result = io.BytesIO()
        with wave.open(result, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            for count in (1600, 1600, 379):
                wav.writeframesraw(b'\x00\x00' * count)
        result.seek(0)
        with wave.open(result, 'rb') as wav:
            self.assertEqual(wav.getnframes(), 3579)
            self.assertEqual(len(wav.readframes(3579)), 7158)


if __name__ == '__main__':
    unittest.main()
