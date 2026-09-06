$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

& "$PSScriptRoot\fix_russian_runtime.ps1"

# Repair the example template idempotently.
$example = '.env.example'
$text = Get-Content $example -Raw -Encoding UTF8
$text = [regex]::Replace($text, '(?m)^# JARVIS_LLM_FAST_MODEL is set above for the fast Russian voice/chat path\s*$', 'JARVIS_LLM_FAST_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507')
if ($text -notmatch '(?m)^JARVIS_LLM_PRIMARY_MODEL=') {
    $anchor = 'JARVIS_FREELLMAPI_API_KEY='
    $text = $text.Replace($anchor, $anchor + "`r`nJARVIS_LLM_PRIMARY_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507`r`nJARVIS_LLM_FAST_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507")
}
Set-Content $example -Value $text -Encoding UTF8 -NoNewline

# Migrate a key already present in local .env under the common generic name without printing it.
$envPath = '.env'
if (Test-Path $envPath) {
    $envText = Get-Content $envPath -Raw -Encoding UTF8
    if ($envText -match '(?m)^OPENROUTER_API_KEY\s*=\s*(\S+)\s*$') {
        $key = $Matches[1]
        if ($envText -match '(?m)^JARVIS_OPENROUTER_API_KEY\s*=') {
            $envText = [regex]::Replace($envText, '(?m)^JARVIS_OPENROUTER_API_KEY\s*=.*$', 'JARVIS_OPENROUTER_API_KEY=' + $key, 1)
        } else {
            $envText += "`r`nJARVIS_OPENROUTER_API_KEY=$key`r`n"
        }
        Set-Content $envPath -Value $envText -Encoding UTF8 -NoNewline
        Write-Host 'Migrated existing OPENROUTER_API_KEY to JARVIS_OPENROUTER_API_KEY (secret not printed).'
    }
}

# Lightweight post-patch assertions. These fail loudly instead of leaving a half-migrated install.
$checks = @{
    'src/jarvis/config.py' = @('reply_language: str = "Russian"', 'openrouter_api_key: str | None = None', 'llm_primary_model: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"')
    'src/jarvis/brain/llm.py' = @('("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),')
    'src/jarvis/brain/agent.py' = @('"One moment, sir."')
    'personality/jarvis.md' = @('Raw tool/web/news output must NEVER be sent directly to TTS')
}
foreach ($path in $checks.Keys) {
    $body = Get-Content $path -Raw -Encoding UTF8
    foreach ($needle in $checks[$path]) {
        if ($path -like '*agent.py' -and $needle -eq '"One moment, sir."') {
            if ($body.Contains($needle)) { throw "English spoken acknowledgement still exists in $path" }
        } elseif (!$body.Contains($needle)) {
            throw "Post-patch assertion failed: $path missing $needle"
        }
    }
}

Write-Host ''
Write-Host 'OK: Russian runtime migration applied and verified.' -ForegroundColor Green
Write-Host 'Run: uv run python -m unittest discover -s tests -v'
