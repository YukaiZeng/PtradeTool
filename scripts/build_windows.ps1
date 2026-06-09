$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RootDir

$Python = if ($env:PYTHON) { $env:PYTHON } else { ".venv\Scripts\python.exe" }
& $Python -m PyInstaller ptrade-order-tool.spec --clean --noconfirm

