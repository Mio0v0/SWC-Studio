$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "py"
}

$DistDir = Join-Path $RootDir "dist"
$BuildDir = Join-Path $RootDir "build"
$SpecPath = Join-Path $RootDir "packaging\swcstudio_gui_windows.spec"
$ZipPath = Join-Path $DistDir "SWC-Studio-windows.zip"
$AppDir = Join-Path $DistDir "SWC-Studio"

Write-Host "Generating Windows icon from packaging/icon.png..."
if ($PythonExe -eq "py") {
    & py -3 "$RootDir\packaging\make_windows_icon.py"
} else {
    & $PythonExe "$RootDir\packaging\make_windows_icon.py"
}

Write-Host "Building Windows executable with PyInstaller..."
if ($PythonExe -eq "py") {
    & py -3 -m PyInstaller --noconfirm --clean $SpecPath
} else {
    & $PythonExe -m PyInstaller --noconfirm --clean $SpecPath
}

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

if (-not (Test-Path $AppDir)) {
    throw "Expected build output folder was not created: $AppDir"
}

Write-Host "Creating shareable zip..."
Compress-Archive -Path $AppDir -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "Build complete:"
Write-Host "  App folder: $AppDir"
Write-Host "  Zip file:   $ZipPath"
