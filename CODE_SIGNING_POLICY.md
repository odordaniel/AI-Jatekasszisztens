Code Signing Policy

AI Játékasszisztens

Project: AI Játékasszisztens
Repository: https://github.com/odordaniel/AI-Jatekasszisztens
License: MIT

1. Release authorization

Ódor Dániel is the sole authorized release manager and code-signing approver.

External contributors may submit issues and pull requests, but they are not authorized to approve releases or request production code signing.

2. Build and signing process

Official Windows builds are produced from the public GitHub repository using GitHub Actions.

The build process uses Python and PyInstaller.

Code signing will be performed through SignPath Foundation after project approval and signing integration.

Only builds originating from reviewed and approved source code may be submitted for signing.

3. Release security

* Release approval is restricted to the project maintainer.
* The maintainer’s GitHub account is protected by two-factor authentication.
* API keys, signing credentials, and other secrets must never be committed to the repository.
* GitHub Secret scanning is enabled.
* Production signing credentials must not be stored in source code.
* Signed releases must be verified before publication.

4. Privacy and data handling

The application captures screenshots only when the user initiates a translation.

The selected screenshot is transmitted to the AI API endpoint configured by the user for translation.

API credentials are stored locally using Windows Credential Manager.

Translation history and application settings are stored locally.

The application does not intentionally collect telemetry or transmit translation history to the project maintainer.

Third-party AI providers process submitted screenshots according to their own terms and privacy policies.

5. Release integrity

Official releases must be associated with identifiable Git commits and version tags.

Build artifacts must be traceable to the corresponding source revision.

The maintainer is responsible for reviewing changes before release and verifying the resulting signed artifacts.

6. Security incidents

If signing credentials are compromised, unauthorized releases are discovered, or a security incident affects release integrity, signing must be suspended until the issue is investigated and resolved.

7. Policy maintenance

This policy may be updated by the sole authorized maintainer, Ódor Dániel.