$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

# The migration is implemented in Python so Windows PowerShell 5.1 cannot corrupt
# Cyrillic source text before the script is parsed.
$script = Join-Path $PSScriptRoot 'fix_russian_runtime.py'
if (-not (Test-Path $script)) { throw "Missing $script" }

& uv run python $script
if ($LASTEXITCODE -ne 0) { throw "Russian runtime migration failed with exit code $LASTEXITCODE" }

Write-Host ''
Write-Host 'Migration completed. Restart JARVIS before testing.' -ForegroundColor Green
Write-Host 'Then run: uv run python -m unittest discover -s tests -v'
