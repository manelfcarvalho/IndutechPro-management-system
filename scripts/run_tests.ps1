$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
    python -m compileall -q main.py database ui tests
    python -m unittest discover tests
}
finally {
    Pop-Location
}
