$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

# Use UTF-8 explicitly. Windows PowerShell 5.1 otherwise commonly decodes
# UTF-8 Cyrillic as CP1252/ANSI and produces mojibake before parsing.
$script = Join-Path $PSScriptRoot 'fix_russian_runtime.ps1'
if (-not (Test-Path $script)) { throw "Missing $script" }

# Read and rewrite the migration script as UTF-8 without BOM, then execute it.
$utf8 = New-Object System.Text.UTF8Encoding($false)
$text = [System.IO.File]::ReadAllText($script, $utf8)
[System.IO.File]::WriteAllText($script, $text, $utf8)

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script
if ($LASTEXITCODE -ne 0) { throw "Russian runtime migration failed with exit code $LASTEXITCODE" }

Write-Host ''
Write-Host 'Migration completed. Restart JARVIS before testing.' -ForegroundColor Green
Write-Host 'Then run: uv run python -m unittest discover -s tests -v'
