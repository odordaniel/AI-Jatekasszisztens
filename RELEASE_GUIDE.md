# Versioned Windows releases

Regular pushes to `main` build an unsigned Actions artifact only. A pushed version tag like `v1.10.0` builds the program and publishes a GitHub Release with a portable ZIP and SHA-256 checksum. Tag pushes do not require a separate manual workflow run.

## Publishing

1. Merge and test changes on `main`; confirm its Windows portable build succeeds.
2. In GitHub, create and **push a new annotated version tag** such as `v1.10.0` pointing to the tested commit on `main`. One command-line method:

   ```bash
   git checkout main
   git pull --ff-only
   git tag -a v1.10.0 -m "Release v1.10.0"
   git push origin v1.10.0
   ```

3. Wait for the tagged `Windows portable build` run to complete. Its release job creates the GitHub Release and uploads the ZIP and checksum.
4. Check the release page and test the extracted EXE on Windows.

**Important:** Do not create the Release manually before the workflow runs: `gh release create` expects a new release. If an older Release with the same tag exists, create a new version tag for the new release. The release workflow uses `GITHUB_TOKEN` with `contents: write` only for its release job. Repository/org Actions settings must permit GitHub Actions to create releases. The release is **unsigned** until SignPath approval and signing integration. The checksum alone does not prove authenticity.

SignPath Foundation should be mentioned on the project's download page. This workflow also mentions the pending signing status in the release notes.
