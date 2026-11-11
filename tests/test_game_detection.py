"""Actual filesystem and state tests for offline game recognition."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from game_detection import (GameRecognizer, clean_title, steam_manifest_title,
                            epic_manifest_title, title_from_path)

class OfflineGameRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_unknown_executable_is_not_guessed(self):
        self.assertEqual(title_from_path(str(self.root / 'ordinary.exe')), ('', ''))

    def test_steam_appmanifest_name(self):
        path = self.root / 'appmanifest_123.acf'
        path.write_text('"AppState"\n{\n"name" "Example Quest"\n"installdir" "ExampleQuest"\n}', encoding='utf-8')
        self.assertEqual(steam_manifest_title(path, 'ExampleQuest'), 'Example Quest')
        self.assertEqual(steam_manifest_title(path, 'Elsewhere'), '')

    def test_epic_manifest_requires_matching_install_path(self):
        folder = self.root / 'epic'
        folder.mkdir()
        (folder / 'example.item').write_text(json.dumps({'InstallLocation': str(self.root / 'Installed'),
                                                         'DisplayName': 'Example Adventure'}), encoding='utf-8')
        self.assertEqual(epic_manifest_title(str(self.root / 'Installed' / 'Binaries' / 'app.exe'), folder), 'Example Adventure')
        self.assertEqual(epic_manifest_title(str(self.root / 'Installed2' / 'app.exe'), folder), '')

    def test_manual_pairing_persists(self):
        path = self.root / 'pairings.json'
        a = GameRecognizer(path)
        exe = str(self.root / 'unknown' / 'app.exe')
        self.assertTrue(a.remember(exe, 'My Game'))
        b = GameRecognizer(path)
        self.assertEqual(b.recognize(exe), ('My Game', 'saját párosítás'))

    def test_bad_mapping_not_overwritten(self):
        path = self.root / 'pairings.json'
        path.write_text('{invalid', encoding='utf-8')
        self.assertEqual(GameRecognizer(path).recognize(str(self.root / 'ordinary.exe')), ('', ''))
        self.assertEqual(path.read_text(encoding='utf-8'), '{invalid')

    def test_invalid_title_rejected(self):
        self.assertEqual(clean_title('../'), '')
        self.assertEqual(clean_title('Launcher'), '')
        self.assertEqual(clean_title('Game Name'), 'Game Name')

    def test_no_image_or_audio_ai_detection(self):
        source_dir = Path(__file__).resolve().parents[1] / 'src'
        text = (source_dir / 'assistant.py').read_text(encoding='utf-8')
        audio = (source_dir / 'live_translation.py').read_text(encoding='utf-8')
        self.assertNotIn('ImageGameDetector', text)
        self.assertNotIn('_infer_context(', audio)
        self.assertNotIn('game_inferred.connect(', text)

if __name__ == '__main__':
    unittest.main()
