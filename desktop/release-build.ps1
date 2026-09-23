param(
    [string]$WorkerDeployment = "NOT DEPLOYED",
    [string]$D1Migration = "NOT APPLIED",
    [string]$DeliveryVerification = "NOT EXECUTED"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot ".release-build"))
$sourceRoot = Join-Path $projectRoot "src"
$env:PYTHONPATH = $sourceRoot
$appVersion = (& py -3.12 -c "from aggits_video_factory.version import APP_VERSION; print(APP_VERSION)").Trim()
if (-not $appVersion) { throw "Unable to resolve application version." }
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "release-artifacts\v$appVersion"))
$releaseDocs = [IO.Path]::GetFullPath((Join-Path $projectRoot "docs\release-v$appVersion"))

function Assert-WorkspaceChild([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $prefix = $projectRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to alter a path outside the repository: $full"
    }
    return $full
}

function Invoke-Checked([scriptblock]$Command, [string]$Description) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

$branch = (& git -C $projectRoot branch --show-current).Trim()
if ($branch -notlike "crispy-bits-desktop*-development") {
    throw "Release builds must run from a Crispy Bits Desktop development branch; current branch is '$branch'."
}
$dirty = (& git -C $projectRoot status --porcelain)
if ($dirty) {
    throw "Release builds require a clean working tree."
}
$sourceCommit = (& git -C $projectRoot rev-parse HEAD).Trim()

$buildRoot = Assert-WorkspaceChild $buildRoot
$releaseRoot = Assert-WorkspaceChild $releaseRoot
if (Test-Path -LiteralPath $buildRoot) { Remove-Item -LiteralPath $buildRoot -Recurse -Force }
if (Test-Path -LiteralPath $releaseRoot) { Remove-Item -LiteralPath $releaseRoot -Recurse -Force }
New-Item -ItemType Directory -Path $buildRoot | Out-Null
New-Item -ItemType Directory -Path $releaseRoot | Out-Null

Invoke-Checked { py -3.12 -m venv (Join-Path $buildRoot "venv") } "Fresh Python environment creation"
$python = Join-Path $buildRoot "venv\Scripts\python.exe"
Invoke-Checked { & $python -m pip install --disable-pip-version-check -r (Join-Path $projectRoot "requirements-release.txt") } "Pinned dependency installation"

$actualPython = (& $python -c "import platform; print(platform.python_version())").Trim()
if ($actualPython -ne "3.12.10") { throw "Release requires Python 3.12.10; found $actualPython." }
$actualPyInstaller = (& $python -c "import PyInstaller; print(PyInstaller.__version__)").Trim()
if ($actualPyInstaller -ne "6.22.2") { throw "Release requires PyInstaller 6.22.2; found $actualPyInstaller." }

$env:PYTHONPATH = $sourceRoot
$env:CRISPY_BITS_TEST_DIR = Join-Path $projectRoot "tests"
Invoke-Checked { & $python -m compileall -q (Join-Path $projectRoot "src") (Join-Path $projectRoot "desktop") (Join-Path $projectRoot "tests") (Join-Path $projectRoot "tools") } "Python compilation"
$pythonTestCount = [int]((& $python -c "import os, unittest; print(unittest.defaultTestLoader.discover(os.environ['CRISPY_BITS_TEST_DIR']).countTestCases())").Trim())
if ($pythonTestCount -lt 62) { throw "Expected at least 62 Python tests; discovered $pythonTestCount." }
Invoke-Checked { & $python -m unittest discover -s (Join-Path $projectRoot "tests") -v } "Python tests"

$javascriptFiles = Get-ChildItem (Join-Path $projectRoot "worker\src"), (Join-Path $projectRoot "worker\tests"), (Join-Path $projectRoot "static") -Recurse -File -Filter "*.js"
foreach ($javascriptFile in $javascriptFiles) {
    Invoke-Checked { node --check $javascriptFile.FullName } "JavaScript syntax check for $($javascriptFile.Name)"
}
Push-Location (Join-Path $projectRoot "worker")
try {
    Invoke-Checked { node --test tests/*.test.mjs } "Worker tests"
}
finally {
    Pop-Location
}
$workerTestCount = 26

$versionFile = Join-Path $buildRoot "windows-version-info.txt"
Invoke-Checked { & $python (Join-Path $projectRoot "tools\generate_version_resource.py") $versionFile } "Windows version-resource generation"
$env:CRISPY_BITS_VERSION_FILE = $versionFile
$distRoot = Join-Path $buildRoot "dist"
$workRoot = Join-Path $buildRoot "pyinstaller-work"
Invoke-Checked { & $python -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath $workRoot (Join-Path $projectRoot "desktop\VideoJukeboxFactory.spec") } "PyInstaller build"

$exeName = (& $python -c "from aggits_video_factory.version import EXE_FILENAME; print(EXE_FILENAME)").Trim()
$builtExe = Join-Path $distRoot $exeName
if (-not (Test-Path -LiteralPath $builtExe -PathType Leaf)) { throw "Final executable is missing: $builtExe" }

$smoke = Start-Process -FilePath $builtExe -ArgumentList "--smoke-test" -WindowStyle Hidden -Wait -PassThru
if ($smoke.ExitCode -ne 0) { throw "Packaged-resource smoke test failed with exit code $($smoke.ExitCode)." }

$info = (Get-Item -LiteralPath $builtExe).VersionInfo
if ($info.ProductName -ne "CRISPY BITS DESKTOP") { throw "Incorrect ProductName: $($info.ProductName)" }
if ($info.FileDescription -ne "CRISPY BITS DESKTOP") { throw "Incorrect FileDescription: $($info.FileDescription)" }
if ($info.FileVersion -ne "$appVersion.0") { throw "Incorrect FileVersion: $($info.FileVersion)" }
if ($info.ProductVersion -ne $appVersion) { throw "Incorrect ProductVersion: $($info.ProductVersion)" }
if ($info.OriginalFilename -ne $exeName) { throw "Incorrect OriginalFilename: $($info.OriginalFilename)" }

$releaseExe = Join-Path $releaseRoot $exeName
Copy-Item -LiteralPath $builtExe -Destination $releaseExe
Copy-Item -LiteralPath (Join-Path $releaseDocs "RELEASE-NOTES.txt") -Destination (Join-Path $releaseRoot "RELEASE-NOTES.txt")
Copy-Item -LiteralPath (Join-Path $releaseDocs "OPERATOR-GUIDE.txt") -Destination (Join-Path $releaseRoot "OPERATOR-GUIDE.txt")

$releaseSmoke = Start-Process -FilePath $releaseExe -ArgumentList "--smoke-test" -WindowStyle Hidden -Wait -PassThru
if ($releaseSmoke.ExitCode -ne 0) { throw "Copied release executable smoke test failed with exit code $($releaseSmoke.ExitCode)." }

$manifest = Join-Path $releaseRoot "RELEASE-MANIFEST.txt"
Invoke-Checked {
    & $python (Join-Path $projectRoot "tools\write_release_manifest.py") `
        --exe $releaseExe `
        --output $manifest `
        --commit $sourceCommit `
        --python-tests $pythonTestCount `
        --worker-tests $workerTestCount `
        --worker-deployment $WorkerDeployment `
        --d1-migration $D1Migration `
        --delivery-verification $DeliveryVerification
} "Release-manifest generation"

$expected = @($exeName, "RELEASE-MANIFEST.txt", "RELEASE-NOTES.txt", "OPERATOR-GUIDE.txt") | Sort-Object
$actual = @(Get-ChildItem -LiteralPath $releaseRoot -File | ForEach-Object Name | Sort-Object)
if (Compare-Object $expected $actual) { throw "Release directory contains unexpected or missing files." }

$hash = (Get-FileHash -LiteralPath $releaseExe -Algorithm SHA256).Hash
Write-Host "Release candidate built: $releaseExe"
Write-Host "SHA-256: $hash"
Write-Host "Source commit: $sourceCommit"
