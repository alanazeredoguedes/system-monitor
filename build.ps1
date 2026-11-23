# Gera o executável do Windows em dist\sysmon.exe
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --clean sysmon.spec
Write-Host "Pronto: dist\sysmon.exe"
