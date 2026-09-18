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
$versionFile = Join-Path $projectRoot ".release-build\development-version-info.txt"
& $python (Join-Path $projectRoot "tools\generate_version_resource.py") $versionFile
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:CRISPY_BITS_VERSION_FILE = $versionFile
& $python -m PyInstaller --noconfirm --clean --distpath (Join-Path $projectRoot "dist") --workpath (Join-Path $projectRoot "build") (Join-Path $PSScriptRoot "VideoJukeboxFactory.spec")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$exeName = (& $python -c "from aggits_video_factory.version import EXE_FILENAME; print(EXE_FILENAME)").Trim()
$exePath = Join-Path (Join-Path $projectRoot "dist") $exeName
& $exePath --smoke-test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Built: $exePath"
