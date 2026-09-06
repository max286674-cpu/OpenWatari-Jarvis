# One-time migration for an existing local deployment.
# Keeps secrets untouched and only fixes legacy English voice defaults.
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$path = Join-Path $root '.env'
if (-not (Test-Path $path)) {
    throw "'.env' not found. Copy .env.example to .env first and fill your existing secrets."
}

$text = Get-Content $path -Raw

function Set-EnvValue([string]$name, [string]$value) {
    $script:text = $script:text -replace "(?m)^$([regex]::Escape($name))=.*$", "$name=$value"
    if ($script:text -notmatch "(?m)^$([regex]::Escape($name))=") {
        $script:text += "`r`n$name=$value`r`n"
    }
}

Set-EnvValue 'JARVIS_REPLY_LANGUAGE' 'Russian'
Set-EnvValue 'JARVIS_UNDERSTOOD_LANGUAGES' 'Russian,English'
Set-EnvValue 'JARVIS_PRILER_REACTIONS' 'true'
Set-EnvValue 'JARVIS_PRILER_VOICE' 'jarvis-remaster'
Set-EnvValue 'JARVIS_PRILER_LANGUAGE' 'ru'

# The old Piper English voice is retained in config as a backwards-compatible value;
# tts.py already maps that legacy value to native Russian Piper when Russian is active.
Set-Content -Path $path -Value $text -Encoding UTF8

Write-Host "Russian voice configuration applied to .env" -ForegroundColor Green
Select-String -Path $path -Pattern 'JARVIS_REPLY_LANGUAGE|JARVIS_UNDERSTOOD_LANGUAGES|JARVIS_PRILER' | ForEach-Object { $_.Line }
