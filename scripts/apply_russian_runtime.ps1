$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

& "$PSScriptRoot\fix_russian_runtime.ps1"

# The base migration historically replaced the example fast-model line after inserting it.
# Repair it idempotently so the example remains a valid copy template.
$example = '.env.example'
$text = Get-Content $example -Raw -Encoding UTF8
$text = [regex]::Replace($text, '(?m)^# JARVIS_LLM_FAST_MODEL is set above for the fast Russian voice/chat path\s*$', 'JARVIS_LLM_FAST_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507')
if ($text -notmatch '(?m)^JARVIS_LLM_PRIMARY_MODEL=') {
    $anchor = 'JARVIS_FREELLMAPI_API_KEY='
    $text = $text.Replace($anchor, $anchor + "`r`nJARVIS_LLM_PRIMARY_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507`r`nJARVIS_LLM_FAST_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507")
}
Set-Content $example -Value $text -Encoding UTF8 -NoNewline

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
