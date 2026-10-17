$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
py -3 -m pip install --upgrade pyinstaller
py -3 -m PyInstaller --noconfirm --clean --onefile --name KTNS-SQLBench `
    --add-data "web;web" --add-data "examples;examples" scripts\launcher.py
Write-Host "Unsigned development executable: dist\KTNS-SQLBench.exe"
