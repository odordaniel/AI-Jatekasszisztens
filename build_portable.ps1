$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.buildvenv\Scripts\python.exe')) {
    py -3 -m venv .buildvenv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}
$python = Join-Path $PSScriptRoot '.buildvenv\Scripts\python.exe'
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python -m py_compile src\assistant.py
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }
& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name AIJatekasszisztens --icon src\app.ico --add-data 'src\app.ico;.' --collect-submodules keyring.backends src\assistant.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
Write-Host 'Portable folder: dist\AIJatekasszisztens' -ForegroundColor Green
Write-Host 'EXE: dist\AIJatekasszisztens\AIJatekasszisztens.exe' -ForegroundColor Green
Write-Host 'Copy the FULL folder to a permanent location, then start the EXE.' -ForegroundColor Yellow
