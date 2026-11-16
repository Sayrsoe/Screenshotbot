# ScreenshotBot

ScreenshotBot SB-1 is a manually triggered Windows screenshot collector for two bundled synthetic football pages. A capture saves an original PNG and a JSON receipt. The accepted local target is installed Microsoft Edge on Windows 11. The project expects an editable source checkout and has no live-source profiles.

## Acceptance and limits

The owner accepts SB-1 as a local Windows/installed-Edge synthetic prototype. The recorded fresh Python/project setup on the same host passed 21 tests with 0 failures, errors, skips or blocked cases (16.441 seconds). Four additional CLI captures succeeded. CPython 3.12.10, Playwright 1.65.1 and Edge 157.0.4341.46 were recorded.

These are historical results, not tests rerun during documentation preparation. Setup reused the existing Windows host and installed Edge. Different-PC, fresh Windows/Edge and independent reviewer runtime reproduction remain unverified. Independent review was static. Browser/font updates and security-policy changes may affect later execution; no production-security certification is claimed.

Original project-local Chromium encountered a Windows Code Integrity signing-policy denial at launch. Using installed Edge succeeded without changing security settings. The default channel remains chromium; explicitly select msedge for the accepted workflow.

## Set up in PowerShell

Prerequisites: Windows, an existing compatible CPython 3.12 interpreter, installed Microsoft Edge permitted by local policy, and PyPI access for dependency installation. No browser installation is part of this accepted setup.

Open PowerShell at the project root. Replace the placeholder with your verified Python executable. The historical fresh session could not resolve its interpreter using the py launcher; do not assume that launcher exists. These are future setup instructions, not commands executed during documentation preparation.

~~~powershell
$pythonExe = '<absolute path to your installed Python 3.12 python.exe>'
& $pythonExe --version
~~~

Confirm the interpreter. Use a new .venv directory; do not overwrite an existing environment. Run each command individually and stop on failure.

~~~powershell
$env:PIP_CONFIG_FILE = 'nul'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:PIP_NO_CACHE_DIR = '1'
Remove-Item Env:PIP_EXTRA_INDEX_URL, Env:PIP_FIND_LINKS -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH, Env:PYTHONHOME -ErrorAction SilentlyContinue
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = Join-Path (Get-Location) 'tasks/local-setup/scratch/tmp'
$env:TMP = $env:TEMP
[IO.Directory]::CreateDirectory($env:TEMP) | Out-Null
& $pythonExe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --only-binary=:all: -r requirements-sb1.txt
.\.venv\Scripts\python.exe -m pip install --no-index --no-deps --no-build-isolation --editable .
.\.venv\Scripts\python.exe -m pip check
~~~

Environment changes apply to this PowerShell session. This setup reuses installed Edge. Do not download Chromium as a recovery for the recorded policy denial. A blocked selected browser requires the responsible policy owner's review; bypassing security policy is outside scope.

## Capture

~~~powershell
.\.venv\Scripts\python.exe -m screenshotbot capture --fixture match-stats --mode panel --channel msedge
.\.venv\Scripts\python.exe -m screenshotbot capture --fixture league-xg --mode full-page --channel msedge
~~~

Both fixtures support both modes. --channel accepts chromium (the preserved default) or msedge. Edge is not pinned and may update. Success prints JSON with PNG and receipt paths under captures/<capture-id>/. Exit 0 means success, exit 2 rejected CLI input, and exit 1 capture/storage failure. Codes include busy, missing_panel, missing_header, network_denied, redirect_denied, timeout and browser_failed. A policy-blocked launch can surface as Playwright's generic "Target page, context or browser has been closed."

## Verify a receipt

Replace the placeholder with the ID from a successful capture.

~~~powershell
$folder = Join-Path 'captures' '<capture-id>'
$receipt = Get-Content -Raw -LiteralPath (Join-Path $folder 'receipt.json') | ConvertFrom-Json
$digest = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $folder 'original.png')).Hash
$digest.ToLowerInvariant() -eq $receipt.sha256
~~~

Open the PNG and check teams, column headers and values are legible. The digest compares byte identity against the receipt; it does not independently authenticate the source or establish when statistics first existed.

## Tests and contract

For a separately authorized run using installed Edge:

~~~powershell
$env:SCREENSHOTBOT_TEST_CHANNEL = 'msedge'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

Tests use owned fixtures, temporary variations and local loopback tripwires. Test outputs use temporary scratch folders. Captures and historical machine evidence are excluded from the proposed public snapshot. See [the capture and receipt contract](docs/capture.md) for fields, source boundaries and limitations.

## License and scope

Original ScreenshotBot code, tests and owned synthetic fixtures are licensed under the [MIT License](LICENSE), copyright 2026 Sayrsoe. Dependencies retain their own licenses: Playwright Python Apache-2.0, greenlet MIT AND PSF-2.0, and setuptools MIT. Dependencies, browsers and Windows fonts are not bundled in the source snapshot. MIT does not grant rights to third-party websites, data, trademarks or browser binaries.

No real-provider collection, OCR, database, prediction or betting functionality is included. FotMob access, capture, retention and reuse require separate permission. SB-2, external integration, publication and deployment require separate owner authorization.
