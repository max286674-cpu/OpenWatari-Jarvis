# Fix the actual voice latency path without touching secrets.
# - Russian chat is classified as chat (no fake English filler).
# - Pure chat uses a dedicated low-latency GLM-4.5-Air route with reasoning disabled.
# - Tool turns keep the existing quality/tool model chain.
# - ElevenLabs credentials are NOT changed.
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Replace-Once([string]$path, [string]$old, [string]$new, [string]$label) {
    $full = Join-Path $root $path
    $text = Get-Content $full -Raw -Encoding UTF8
    if ($text.Contains($new)) { return }
    if (-not $text.Contains($old)) {
        throw "Patch target not found in $path: $label"
    }
    $text = $text.Replace($old, $new)
    Set-Content -Path $full -Value $text -Encoding UTF8
    Write-Host "patched $path : $label" -ForegroundColor Green
}

# 1) Source defaults: Russian voice deployment + dedicated fast conversational model.
Replace-Once 'src/jarvis/config.py' '    understood_languages: str = "English"  # comma-list of languages he can UNDERSTAND (STT side)\n    reply_language: str = "English"        # the single language he always REPLIES in' '    understood_languages: str = "Russian,English"  # comma-list of languages he can UNDERSTAND (STT side)\n    reply_language: str = "Russian"        # the single language he always REPLIES in' 'Russian source defaults'
Replace-Once 'src/jarvis/config.py' '    wake_words: str = "jarvis,alfred,robbin,assist,time to work,wake up,six-one-nine"\n    wake_word_threshold: float = 0.5' '    wake_words: str = "jarvis"\n    wake_word_threshold: float = 0.45' 'wake defaults'
Replace-Once 'src/jarvis/config.py' '    wake_ack_phrase: str = "Yes, sir?|I''m listening, sir.|Sir?|Go ahead, sir."' '    wake_ack_phrase: str = "Да, сэр.|Слушаю, сэр.|Да, сэр, я слушаю."' 'Russian wake ACK'
Replace-Once 'src/jarvis/config.py' '    listening_pulse: bool = True' '    listening_pulse: bool = False' 'disable listening pulse'
Replace-Once 'src/jarvis/config.py' '    deepgram_endpointing_ms: int = 700' '    deepgram_endpointing_ms: int = 500' 'faster Deepgram endpointing'
Replace-Once 'src/jarvis/config.py' '    whisper_language: str = "en"' '    whisper_language: str = "ru"' 'Russian Whisper default'
Replace-Once 'src/jarvis/config.py' '    piper_voice: str = "en_US-ryan-high"' '    piper_voice: str = "ru_RU-ruslan-medium"' 'Russian Piper default'

# Dedicated non-thinking conversational route. Existing tool/reasoning chain is untouched.
Replace-Once 'src/jarvis/config.py' '    llm_fast_model: str | None = None' '    llm_fast_model: str | None = "z-ai/glm-4.5-air"' 'fast chat model default'

# 2) Russian pure-chat detection and Russian deterministic filler vocabulary.
Replace-Once 'src/jarvis/brain/agent.py' '    r"^\\s*(hi|hey+|hello|hiya|yo|howdy|good\\s*(morning|afternoon|evening|night)|greetings|"' '    r"^\\s*(привет|здравствуй|здравствуйте|доброе\\s*(утро|утро)|добрый\\s*(день|вечер)|как\\s*(ты|дела|поживаешь)|как\\s*себя\\s*чувствуешь|что\\s*нового|как\\s*жизнь|"' 'Russian pure-chat patterns'
Replace-Once 'src/jarvis/brain/agent.py' '    r"how\\s*(are\\s*)?you\\s*doing|how\\'?s\\s*it\\s*going|"' '    r"как\\s*(ты|дела|поживаешь)|как\\s*идут\\s*дела|как\\s*настроение|"' 'Russian chat continuation'
Replace-Once 'src/jarvis/brain/agent.py' '    r"how do you feel|are you (ok|okay|there|alright|awake|listening)|you good|you there|"' '    r"как\\s*ты\\s*себя\\s*чувствуешь|ты\\s*(в порядке|тут|здесь|готов|слушаешь)|"' 'Russian wellbeing patterns'
Replace-Once 'src/jarvis/brain/agent.py' '    r"cool|nice|neat|got it|gotcha|i see|makes sense|no worries|my bad|of course|"' '    r"круто|отлично|понятно|ясно|хорошо|ладно|без проблем|понял|понятно|конечно|"' 'Russian short-chat patterns'
Replace-Once 'src/jarvis/brain/agent.py' '    r"never\\s*mind|nevermind|forget it|just (saying|checking|kidding))"' '    r"неважно|забудь|я просто (спрашиваю|проверяю|шучу))"' 'Russian closing chat patterns'

# Replace the acknowledgement pools with Russian so even non-chat/tool turns never emit English.
Replace-Once 'src/jarvis/brain/agent.py' '    "Right away, sir.", "On it, sir.", "Of course, sir.", "Let me take care of that, sir.",\n              "Consider it done, sir.")\n_CHAT_ACKS = ("Yes, sir.", "Certainly, sir.", "Of course, sir.", "One moment, sir.")' '    "Сейчас, сэр.", "Уже занимаюсь, сэр.", "Разумеется, сэр.", "Будет сделано, сэр.",\n              "Принято, сэр.")\n_CHAT_ACKS = ("Да, сэр.", "Разумеется, сэр.", "Конечно, сэр.", "Слушаю, сэр.")' 'Russian conversational ACK pools'

# Use the dedicated fast model only for pure chat; tool turns keep the existing chain.
Replace-Once 'src/jarvis/brain/agent.py' '                    async for kind, payload in self._llm.stream_with_tools(\n                        messages, tools=turn_tools, tool_choice=attempt, skip_primary=prefer_fb\n                    ):' '                    fast_chat = settings.llm_fast_model if _is_pure_chat(user_text) else None\n                    async for kind, payload in self._llm.stream_with_tools(\n                        messages, tools=turn_tools, tool_choice=attempt, skip_primary=prefer_fb,\n                        prepend_model=fast_chat,\n                    ):' 'fast chat routing'

# 3) LLM client: support prepending a dedicated fast model and disable GLM-4.5-Air reasoning.
Replace-Once 'src/jarvis/brain/llm.py' '    if "gpt-oss" in model_name:\n        return {"reasoning_effort": "low"}\n    return {}' '    if "gpt-oss" in model_name:\n        return {"reasoning_effort": "low"}\n    if "glm-4.5-air" in model_name.lower():\n        return {"extra_body": {"reasoning": {"enabled": False}}}\n    return {}' 'GLM-4.5-Air non-thinking mode'
Replace-Once 'src/jarvis/brain/llm.py' '        skip_primary: bool = False,\n    ) -> AsyncIterator[tuple[str, Any]]:' '        skip_primary: bool = False,\n        prepend_model: str | None = None,\n    ) -> AsyncIterator[tuple[str, Any]]:' 'stream fast-model parameter'
Replace-Once 'src/jarvis/brain/llm.py' '        chain = self._candidate_chain()\n        if skip_primary and len(chain) > 1:' '        chain = self._candidate_chain()\n        if prepend_model:\n            chain = [prepend_model] + [m for m in chain if m != prepend_model]\n        if skip_primary and len(chain) > 1:' 'prepend fast model in stream chain'

# 4) Apply the same settings to the existing local .env, without touching API keys.
$envPath = Join-Path $root '.env'
if (Test-Path $envPath) {
    $envText = Get-Content $envPath -Raw -Encoding UTF8
    function Set-EnvValue([string]$name, [string]$value) {
        $pattern = "(?m)^$([regex]::Escape($name))=.*$"
        if ($script:envText -match $pattern) {
            $script:envText = [regex]::Replace($script:envText, $pattern, "$name=$value")
        } else {
            $script:envText += "`r`n$name=$value`r`n"
        }
    }
    Set-EnvValue 'JARVIS_REPLY_LANGUAGE' 'Russian'
    Set-EnvValue 'JARVIS_UNDERSTOOD_LANGUAGES' 'Russian,English'
    Set-EnvValue 'JARVIS_WHISPER_LANGUAGE' 'ru'
    Set-EnvValue 'JARVIS_WAKE_WORDS' 'jarvis'
    Set-EnvValue 'JARVIS_WAKE_WORD_THRESHOLD' '0.45'
    Set-EnvValue 'JARVIS_WAKE_ACK_PHRASE' 'Да, сэр.|Слушаю, сэр.|Да, сэр, я слушаю.'
    Set-EnvValue 'JARVIS_LISTENING_PULSE' 'false'
    Set-EnvValue 'JARVIS_DEEPGRAM_ENDPOINTING_MS' '500'
    Set-EnvValue 'JARVIS_PIPER_VOICE' 'ru_RU-ruslan-medium'
    Set-EnvValue 'JARVIS_LLM_FAST_MODEL' 'z-ai/glm-4.5-air'
    Set-Content -Path $envPath -Value $envText -Encoding UTF8
    Write-Host '.env: Russian + fast-chat profile applied; secrets untouched.' -ForegroundColor Green
} else {
    Write-Warning '.env not found; source defaults were patched. Run this again after creating .env.'
}

Write-Host ''
Write-Host 'Done. ElevenLabs API key/voice ID were NOT changed.' -ForegroundColor Cyan
Write-Host 'For arbitrary speech, Piper remains the safe fallback until a valid ElevenLabs Voice ID is configured.' -ForegroundColor Cyan
