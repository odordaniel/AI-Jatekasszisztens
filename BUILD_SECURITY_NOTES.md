# Build security status

This maintenance change does not modify application behavior or sign executables.

## Implemented
- CI and local PowerShell build check installed dependency compatibility with `pip check`.
- CI validates Python syntax before packaging.
- CI fails if the expected EXE is missing.
- CI includes a SHA-256 checksum of the EXE inside the uploaded artifact.
- CI checkout does not persist GitHub credentials.
- CI uses a named Windows runner image and a job timeout.

## Still required
- Dependencies use version ranges, **not** an audited, hash-pinned lockfile. Do not claim reproducible builds.
- GitHub Actions are version-tagged rather than pinned to verified commit SHAs.
- SignPath approval and signing workflow are pending.
- The Actions artifact is **unsigned** and is not automatically published to GitHub Releases.
- The checksum helps detect changes relative to this artifact, but is not proof of publisher authenticity.

To create a hash-pinned lockfile safely, resolve all direct and transitive dependencies on the target Windows/Python version, test the resulting build, then enforce hashes in both CI and local build scripts. Do not generate incomplete hashes from another OS.
