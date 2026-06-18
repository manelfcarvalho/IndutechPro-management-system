$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$targets = @(
    (Join-Path $root "__pycache__"),
    (Join-Path $root "database\__pycache__"),
    (Join-Path $root "ui\__pycache__"),
    (Join-Path $root "ui\pages\__pycache__"),
    (Join-Path $root "ui\utils\__pycache__"),
    (Join-Path $root "tests\__pycache__"),
    (Join-Path $root ".DS_Store")
)

foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target) {
        $resolved = (Resolve-Path -LiteralPath $target).Path
        if ($resolved -eq $root -or -not $resolved.StartsWith($root)) {
            throw "Unsafe cleanup target: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
        Write-Host "Removed $resolved"
    }
}

Write-Host "Generated caches cleaned."
