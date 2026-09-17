$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $projectRoot ".venv-build"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv $venv
}

& $python -m pip install --disable-pip-version-check -r (Join-Path $projectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:PYTHONPATH = (Join-Path $projectRoot "src")
& $python -m unittest discover -s (Join-Path $projectRoot "tests") -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m PyInstaller --noconfirm --clean --distpath (Join-Path $projectRoot "dist") --workpath (Join-Path $projectRoot "build") (Join-Path $PSScriptRoot "VideoJukeboxFactory.spec")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $projectRoot "dist\AGGITS Video Jukebox Factory.exe") --smoke-test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Built: $projectRoot\dist\AGGITS Video Jukebox Factory.exe"
