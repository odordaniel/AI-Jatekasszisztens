# Versioned Windows releases

Regular pushes to `main` build an unsigned Actions artifact only. A pushed version tag like `v2.0.0` builds the program and publishes a GitHub Release with a portable ZIP and SHA-256 checksum. Tag pushes do not require a separate manual workflow run.

## Publishing

1. Merge and test changes on `main`; confirm its Windows portable build succeeds.
2. In GitHub, create and **push a new annotated version tag** such as `v2.0.0` pointing to the tested commit on `main`. One command-line method:

   ```bash
   git checkout main
   git pull --ff-only
   git tag -a v2.0.0 -m "Release v2.0.0"
   git push origin v2.0.0
   ```

3. Wait for the tagged `Windows portable build` run to complete. Its release job creates the GitHub Release and uploads the ZIP and checksum.
4. Check the release page and test the extracted EXE on Windows. Confirm that the application settings display `v2.0.0`, screenshot and audio translation work, and game-specific history folders are created correctly.

**Important:** Do not create the Release manually before the workflow runs: `gh release create` expects a new release. If an older Release with the same tag exists, create a new version tag for the new release. The release workflow uses `GITHUB_TOKEN` with `contents: write` only for its release job. Repository/org Actions settings must permit GitHub Actions to create releases. The release is **unsigned** until SignPath approval and signing integration. The checksum alone does not prove authenticity.

SignPath Foundation should be mentioned on the project's download page. This workflow also mentions the pending signing status in the release notes.

## 2.0 release checklist

- Update `src/assistant.py` to `APP_VERSION = '2.0.0'` before tagging.
- Commit the updated README, changelog and developer documentation together with the last verified source version.
- Run `python -m unittest discover -s tests -v` and `python -m py_compile src/assistant.py src/live_translation.py src/game_detection.py`.
- On Windows 11, verify screenshot translation, audio translation, game switching, unknown-game routing, re-creating deleted game folders, and history operations.
- Push the tag `v2.0.0` only after the tested commit is on `main`. This is not an automatic publication until the tag is pushed.
