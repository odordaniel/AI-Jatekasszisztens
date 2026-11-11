# Contributing

Please open an issue before substantial changes. Keep the current UI and hotkey behavior intact. Read `AI_START_HERE.md` and `docs/AI_FEJLESZTOI_UTMUTATO.md` first.

Validate changes with `python -m py_compile src/assistant.py`, then test the built EXE on Windows 11. Never include real API keys or personal screenshots in pull requests.

Third-party dependencies must be checked for license compatibility and redistribution requirements.

Before opening a pull request, run `python -m unittest discover -s tests -v`
and `python -m py_compile src/assistant.py src/live_translation.py`.
The CI build also runs these checks before PyInstaller.
