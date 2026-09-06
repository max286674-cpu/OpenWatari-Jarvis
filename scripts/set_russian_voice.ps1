# One-time migration for an existing local deployment.
# Keeps secrets untouched and only fixes legacy English/latency voice defaults.
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

# One deterministic conversation language: Russian. STT may still understand English.
Set-EnvValue 'JARVIS_REPLY_LANGUAGE' 'Russian'
Set-EnvValue 'JARVIS_UNDERSTOOD_LANGUAGES' 'Russian,English'
Set-EnvValue 'JARVIS_WHISPER_LANGUAGE' 'ru'

# Exact prerecorded Priler acknowledgement; arbitrary replies use the normal TTS provider.
Set-EnvValue 'JARVIS_PRILER_REACTIONS' 'true'
Set-EnvValue 'JARVIS_PRILER_VOICE' 'jarvis-remaster'
Set-EnvValue 'JARVIS_PRILER_LANGUAGE' 'ru'

# Wake tuning: 0.45 matches the observed real "Hey Jarvis" confidence better than the old 0.50.
# Only the actual pretrained "jarvis" model is enabled here; unsupported aliases are ignored.
Set-EnvValue 'JARVIS_WAKE_WORDS' 'jarvis'
Set-EnvValue 'JARVIS_WAKE_WORD_THRESHOLD' '0.45'

# Remove unnecessary latency/voice variability from the critical path.
Set-EnvValue 'JARVIS_TTS_AFFECT_ENABLED' 'false'
Set-EnvValue 'JARVIS_DEEPGRAM_ENDPOINTING_MS' '500'

# Keep the proven local fallback deterministic and native-Russian.
Set-EnvValue 'JARVIS_TTS_FALLBACK_PROVIDER' 'piper'
Set-EnvValue 'JARVIS_PIPER_VOICE' 'ru_RU-ruslan-medium'

# The listening heartbeat is useful for diagnostics but is distracting and can contaminate
# the microphone on a laptop. Disable it in the normal conversational profile.
Set-EnvValue 'JARVIS_LISTENING_PULSE' 'false'

Set-Content -Path $path -Value $text -Encoding UTF8

Write-Host "Russian low-latency voice profile applied to .env" -ForegroundColor Green
Select-String -Path $path -Pattern 'JARVIS_REPLY_LANGUAGE|JARVIS_UNDERSTOOD_LANGUAGES|JARVIS_PRILER|JARVIS_WAKE_WORD|JARVIS_TTS_AFFECT|JARVIS_DEEPGRAM_ENDPOINTING|JARVIS_PIPER|JARVIS_LISTENING_PULSE' | ForEach-Object { $_.Line }
