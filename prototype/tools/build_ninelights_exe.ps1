param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$buildRoot = Join-Path $repoRoot "prototype\build\pyinstaller"
$source = Join-Path $repoRoot "prototype\ninelights_gui.py"
$icon = Join-Path $repoRoot "docs\assets\ninelights-icon.ico"

Push-Location $repoRoot
try {
    $versionOutput = & $Python -c "import tkinter; import PyInstaller; print(PyInstaller.__version__)"
    if ($LASTEXITCODE -ne 0) {
        throw "Python must include tkinter and PyInstaller. Install PyInstaller 6.21.0 in the selected environment."
    }
    $pyinstallerVersion = ([string]($versionOutput | Select-Object -Last 1)).Trim()
    if ($pyinstallerVersion -ne "6.21.0") {
        throw "PyInstaller 6.21.0 is required for a reproducible build; found $pyinstallerVersion."
    }

    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --noupx `
        --icon $icon `
        --add-data "$icon;." `
        --name "JidanNineLights" `
        --distpath (Join-Path $buildRoot "dist") `
        --workpath (Join-Path $buildRoot "work") `
        --specpath (Join-Path $buildRoot "spec") `
        $source
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $exe = Join-Path $buildRoot "dist\JidanNineLights.exe"
    Write-Host "Built: $exe"
    Get-FileHash -LiteralPath $exe -Algorithm SHA256
}
finally {
    Pop-Location
}
