param(
    [switch]$SkipInstall,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $root ".python311\python.exe"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

function Resolve-Python311 {
    if (Test-Path -LiteralPath $projectPython) {
        return $projectPython
    }

    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $candidate = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            return $candidate.Trim()
        }
    }

    throw "Python 3.11 was not found. Install Python 3.11 (64-bit), then run scripts/bootstrap_dev.ps1 again."
}

Set-Location $root
$python311 = Resolve-Python311
$version = & $python311 -c 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=chr(46))'
if ($version.Trim() -ne "3.11") {
    throw "NovelForge development requires Python 3.11; detected $version."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[NovelForge] Creating Python 3.11 virtual environment: .venv"
    & $python311 -m venv (Join-Path $root ".venv")
}

if (-not $SkipInstall) {
    Write-Host "[NovelForge] Installing project and test dependencies"
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $root "requirements-dev.txt")
}

if (-not $SkipTests) {
    Write-Host "[NovelForge] Running pytest"
    & $venvPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "pytest failed." }

    Write-Host "[NovelForge] Running project validation"
    & $venvPython scripts/validate_project.py
    if ($LASTEXITCODE -ne 0) { throw "Project validation failed." }
}

$readyVersion = & $venvPython --version
Write-Host "[NovelForge] Development environment ready: $readyVersion"
