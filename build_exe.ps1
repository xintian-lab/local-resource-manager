$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
$AppName = "Local Resource Manager"
$EntryPoint = Join-Path $ProjectRoot "main.py"
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build"
$SpecFile = Join-Path $ProjectRoot "$AppName.spec"

Set-Location $ProjectRoot

Write-Host "Building $AppName.exe..." -ForegroundColor Cyan
Write-Host "Using Python: $Python" -ForegroundColor DarkGray

try {
    & $Python -m PyInstaller --version | Out-Null
} catch {
    Write-Host "PyInstaller not found. Installing project requirements..." -ForegroundColor Yellow
    & $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
}

if (Test-Path $BuildDir) {
    Remove-Item $BuildDir -Recurse -Force
}

if (Test-Path $SpecFile) {
    Remove-Item $SpecFile -Force
}

$IconsDir = Join-Path $ProjectRoot "assets\icons"
& $Python -c "from app.ui.app_icon import ensure_build_icons; ensure_build_icons()"
$IconFile = Join-Path $IconsDir "app_icon.ico"
$AddDataArg = "$(Join-Path $ProjectRoot 'assets\icons');assets/icons"

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onefile",
    "--name", $AppName,
    "--add-data", $AddDataArg
)

if (Test-Path $IconFile) {
    $PyInstallerArgs += @("--icon", $IconFile)
}

$PyInstallerArgs += $EntryPoint

& $Python -m PyInstaller @PyInstallerArgs

Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host (Join-Path $DistDir "$AppName.exe")
Write-Host ""
Write-Host "Run it with:"
Write-Host ".\dist\$AppName.exe"
