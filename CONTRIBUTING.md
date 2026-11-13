# Contributing

Please open an issue before substantial changes. Keep the current UI and hotkey behavior intact. Read `AI_START_HERE.md` and `docs/AI_FEJLESZTOI_UTMUTATO.md` first.

Validate changes with `python -m py_compile src/assistant.py`, then test the built EXE on Windows 11. Never include real API keys or personal screenshots in pull requests.

Third-party dependencies must be checked for license compatibility and redistribution requirements.

Before opening a pull request, run `python -m unittest discover -s tests -v`
and `python -m py_compile src/assistant.py src/live_translation.py`.
The CI build also runs these checks before PyInstaller.

## Community guidelines

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md). Use the [issue forms](https://github.com/odordaniel/AI-Jatekasszisztens/issues/new/choose) for bug reports, feature requests, and accessibility barriers; a blank issue is also welcome when a form is difficult to use. See [ACCESSIBILITY.md](ACCESSIBILITY.md) for supported environments and known accessibility limitations. For vulnerabilities, follow [SECURITY.md](SECURITY.md).

The pull request template asks for the problem, resulting behavior, and actual validation. For documentation-only changes, check links and template syntax; application changes also need the relevant tests and Windows checks described above. Report checks you could not run rather than marking them as passed.
