# Builds "dist\Backloggd Checklist.exe".
# Uses a separate virtual environment (.build-venv) so your global Python stays untouched.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".build-venv")) {
    python -m venv .build-venv
    .\.build-venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check pyinstaller
}

python make_icon.py

.\.build-venv\Scripts\python.exe -m PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --name "Backloggd Checklist" `
    --icon "$PSScriptRoot\icon.ico" `
    --add-data "$PSScriptRoot\icon.ico;." `
    --distpath dist --workpath build --specpath build `
    app.pyw

Write-Host "Built: $PSScriptRoot\dist\Backloggd Checklist.exe"
