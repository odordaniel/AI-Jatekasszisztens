"""Critical pure-logic regression tests; no Windows GUI required."""
import ast
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

def load_pure(path, functions, constants=()):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in constants for t in node.targets
        ):
            selected.append(node)
    namespace = {"re": re, "urlsplit": urlsplit}
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])),
                 str(path), "exec"), namespace)
    return namespace

core = load_pure(ROOT / "src/assistant.py",
                 {"validate_api_url", "parse_hotkey", "normalize_hotkeys"},
                 {"KEY_NAMES", "ACTION_NAMES", "HOTKEY_DEFAULTS"})
audio = load_pure(ROOT / "src/live_translation.py", {"safe_api_url"})

class UrlTests(unittest.TestCase):
    def test_v1_path(self):
        self.assertEqual(core["validate_api_url"]("https://example.org/v1/chat/completions"),
                         "https://example.org/v1/chat/completions")
    def test_local_http(self):
        self.assertEqual(core["validate_api_url"]("http://127.0.0.1:8080/api/chat/completions"),
                         "http://127.0.0.1:8080/api/chat/completions")
    def test_remote_http_blocked(self):
        with self.assertRaises(ValueError):
            core["validate_api_url"]("http://example.org/v1/chat/completions")
    def test_secret_in_url_blocked(self):
        for url in ("https://user:pass@example.org/v1/chat/completions",
                    "https://example.org/v1/chat/completions?key=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                core["validate_api_url"](url)
    def test_unrelated_path_blocked(self):
        with self.assertRaises(ValueError):
            core["validate_api_url"]("https://example.org/v1/models")
    def test_audio_url(self):
        self.assertEqual(audio["safe_api_url"]("https://example.org/"),
                         "https://example.org")
        with self.assertRaises(ValueError):
            audio["safe_api_url"]("http://example.org")

class HotkeyTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(core["normalize_hotkeys"](None)["select"], "Ctrl+Shift+T")
    def test_win_modifier(self):
        self.assertEqual(core["parse_hotkey"]("Win+Shift+F9"),
                         ("Shift+Win+F9", ("key", 12, 0x78)))
    def test_mouse(self):
        self.assertEqual(core["parse_hotkey"]("Ctrl+Mouse4"),
                         ("Ctrl+Mouse4", ("mouse", 2, 1)))
    def test_duplicates(self):
        with self.assertRaises(ValueError):
            core["normalize_hotkeys"]({"select": "Ctrl+F9", "audio": "Ctrl+F9"})
    def test_invalid(self):
        for value in ("Ctrl++A", "Ctrl+Ctrl+A", "Ctrl+Nonexistent"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                core["parse_hotkey"](value)

if __name__ == "__main__":
    unittest.main()
