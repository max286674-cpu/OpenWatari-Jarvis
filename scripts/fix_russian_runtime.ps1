$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Edit-File([string]$Path, [scriptblock]$Edit) {
    if (!(Test-Path $Path)) { throw "Missing file: $Path" }
    $text = Get-Content $Path -Raw -Encoding UTF8
    $original = $text
    $text = & $Edit $text
    if ($text -eq $original) { Write-Host "UNCHANGED $Path" } else { Set-Content $Path -Value $text -Encoding UTF8 -NoNewline; Write-Host "UPDATED $Path" }
}

function Replace-Required([string]$Text, [string]$Pattern, [string]$Replacement, [string]$Label) {
    $out = [regex]::Replace($Text, $Pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $Replacement }, 1)
    if ($out -eq $Text) { throw "Patch target not found: $Label" }
    return $out
}

# 1) Russian is the hard runtime default; local Piper is always native Russian in tts.py.
Edit-File 'src/jarvis/config.py' {
    param($t)
    $t = $t.Replace('understood_languages: str = "English"', 'understood_languages: str = "Russian,English"')
    $t = $t.Replace('reply_language: str = "English"', 'reply_language: str = "Russian"')
    $t = $t.Replace('whisper_language: str = "en"', 'whisper_language: str = "ru"')
    $t = $t.Replace('piper_voice: str = "en_US-ryan-high"', 'piper_voice: str = "ru_RU-ruslan-medium"')
    $t = $t.Replace('wake_words: str = "jarvis,alfred,robbin,assist,time to work,wake up,six-one-nine"', 'wake_words: str = "jarvis"')
    $t = $t.Replace('wake_word_threshold: float = 0.5', 'wake_word_threshold: float = 0.45')
    $t = $t.Replace('wake_ack_phrase: str = "Yes, sir?|I''m listening, sir.|Sir?|Go ahead, sir."', 'wake_ack_phrase: str = "Слушаю, сэр.|Да, сэр?|Я здесь, сэр."')
    $t = $t.Replace('deepgram_endpointing_ms: int = 700', 'deepgram_endpointing_ms: int = 500')
    $t = $t.Replace('deepgram_language: str = "multi"', 'deepgram_language: str = "ru"')
    $t = $t.Replace('listening_pulse: bool = True', 'listening_pulse: bool = False')
    $t = $t.Replace('llm_fast_model: str | None = None', 'llm_fast_model: str | None = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"')
    $t = $t.Replace('llm_primary_model: str = "minimax:MiniMax-Text-01"', 'llm_primary_model: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"')
    $t = $t.Replace('llm_fallback_models: str = ("groq:llama-3.3-70b-versatile,",\n                                "groq:llama-3.1-8b-instant,gemini-3.5-flash")', 'llm_fallback_models: str = ("groq:llama-3.3-70b-versatile,groq:llama-3.1-8b-instant,gemini-3.5-flash")')
    if ($t -notmatch 'openrouter_api_key') {
        $anchor = '    minimax_base_url: str = "https://api.minimax.io/v1"'
        if ($t -notmatch [regex]::Escape($anchor)) { throw 'OpenRouter insertion anchor not found in config.py' }
        $insert = @'
    # OpenRouter: direct OpenAI-compatible access to the fast multilingual voice/chat model.
    # Chain syntax: openrouter:<model>. The key stays in local .env and is never committed.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
'@
        $t = $t.Replace($anchor, $anchor + "`r`n" + $insert.TrimEnd())
    }
    return $t
}

# 2) Add OpenRouter as a first-class provider without changing existing providers.
Edit-File 'src/jarvis/brain/llm.py' {
    param($t)
    $anchor = '("minimax:", settings.minimax_base_url, settings.minimax_api_key or "missing-minimax-key"),'
    if ($t -notmatch [regex]::Escape('("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),')) {
        if ($t -notmatch [regex]::Escape($anchor)) { throw 'OpenRouter insertion anchor not found in llm.py' }
        $line = '            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),'
        $t = $t.Replace($anchor, $line + "`r`n" + $anchor)
    }
    $old = '``minimax:<model>`` hits MiniMax directly (api.minimax.io — a paid reasoning model, independent of Groq''s quota + the'
    $t = $t.Replace($old, '``openrouter:<model>`` hits OpenRouter directly; ``minimax:<model>`` hits MiniMax directly (api.minimax.io — a paid reasoning model, independent of Groq''s quota + the')
    return $t
}

# 3) Spoken layer: eliminate English acknowledgements/progress/refusals and prevent raw news dumps.
Edit-File 'src/jarvis/brain/agent.py' {
    param($t)
    $replacements = @{
        '"Right away, sir — putting that to the team lead"'='"Сразу займусь — передаю задачу команде"'
        '"Checking your vault"'='"Проверяю хранилище"'
        '"Reading that note"'='"Читаю заметку"'
        '"Saving that to your vault"'='"Сохраняю в хранилище"'
        '"Looking that up"'='"Проверяю информацию"'
        '"Opening the page"'='"Открываю страницу"'
        '"Opening a browser"'='"Открываю браузер"'
        '"Checking your Telegram"'='"Проверяю Telegram"'
        '"Reading that chat"'='"Читаю чат"'
        '"Sending that"'='"Отправляю"'
        '"Pulling that from your playlist"'='"Беру это из вашего плейлиста"'
        '"Cueing it up in your music room"'='"Ставлю это в музыкальной комнате"'
        '"Leaving the music room"'='"Выключаю музыку"'
        '"Finding that song"'='"Ищу эту композицию"'
        '"Stopping the music"'='"Останавливаю музыку"'
        '"Opening that"'='"Открываю"'
        '"Working on your files"'='"Работаю с файлами"'
        '"On it"'='"Занимаюсь"'
        '"Running that"'='"Выполняю команду"'
        '"In the browser"'='"Работаю в браузере"'
        '"Authorizing the protocol"'='"Запускаю протокол"'
        '"Setting that reminder"'='"Ставлю напоминание"'
        '"Pinging your phone"'='"Отправляю уведомление на телефон"'
        '"Getting the time"'='"Уточняю время"'
        '"Checking the weather"'='"Проверяю погоду"'
        '"Checking your calendar"'='"Проверяю календарь"'
        '"Adding that to your calendar"'='"Добавляю в календарь"'
        '"Checking your email"'='"Проверяю почту"'
        '"Sending that email"'='"Отправляю письмо"'
        '"Noting that down"'='"Запоминаю"'
        '"Let me recall"'='"Сейчас вспомню"'
        '"Right away, sir."'='"Сразу, сэр."'
        '"On it, sir."'='"Занимаюсь, сэр."'
        '"Of course, sir."'='"Конечно, сэр."'
        '"Let me take care of that, sir."'='"Сейчас займусь, сэр."'
        '"Consider it done, sir."'='"Считайте, что сделано, сэр."'
        '"Yes, sir."'='"Да, сэр."'
        '"Certainly, sir."'='"Разумеется, сэр."'
        '"One moment, sir."'='"Одну секунду, сэр."'
        '"No, sir — I won''t do that. Wiping that would destroy your system and it can''t be undone, so I''ve refused it. If you meant a specific file or folder, tell me exactly which and I''ll confirm first."'='"Нет, сэр. Я не буду этого делать: команда уничтожит систему без возможности восстановления. Если вы имели в виду конкретный файл или папку, назовите их, и я сначала запрошу подтверждение."'
        '"I wasn''t able to pull that up just now, sir — let me try again in a moment rather than guess."'='"Сейчас не удалось получить эти данные, сэр. Я не буду гадать и попробую снова."'
    }
    foreach ($pair in $replacements.GetEnumerator()) { $t = $t.Replace($pair.Key, $pair.Value) }
    # Tool/news results must go through the LLM re-voicing path; never read raw news text directly.
    $t = $t.Replace('"define_word", "wiki_lookup", "news_brief",', '"define_word", "wiki_lookup",')
    $t = $t.Replace('"news_brief",', '')
    # Make the multi-intent and background prompts explicit about Russian spoken output.
    $t = $t.Replace('Complete EVERY part — use the right tool for each, one after another — and do not give your final reply until all parts are done or you''ve said which part you can''t do and why.', 'Complete EVERY part — use the right tool for each, one after another — and do not give your final reply until all parts are done or you''ve said which part you can''t do and why. Your final spoken answer MUST be in Russian.')
    return $t
}

# 4) Persona: hard rule against English TTS and raw foreign tool output.
Edit-File 'personality/jarvis.md' {
    param($t)
    $anchor = '- {language_line}'
    $rule = @'
- The spoken reply language is STRICTLY the configured reply language (Russian for this deployment). Never speak English filler, acknowledgements, tool output, web/news headlines, URLs, JSON, code, or provider text verbatim.
- If a tool, website, news source, email, or other external source returns another language, silently translate and compress it into a natural Russian spoken answer before speaking. Preserve names, brands, model names, and technical identifiers when translation would make them incorrect.
- Raw tool/web/news output must NEVER be sent directly to TTS. The final text sent to TTS is always your own concise Russian answer.
'@
    if ($t -notmatch 'Raw tool/web/news output must NEVER be sent directly to TTS') {
        if ($t -notmatch [regex]::Escape($anchor)) { throw 'Persona language anchor not found' }
        $t = $t.Replace($anchor, $anchor + "`r`n" + $rule.TrimEnd())
    }
    return $t
}

# 5) Example env documents the new supported deployment; never place a real secret here.
Edit-File '.env.example' {
    param($t)
    $t = $t.Replace('JARVIS_UNDERSTOOD_LANGUAGES=English', 'JARVIS_UNDERSTOOD_LANGUAGES=Russian,English')
    $t = $t.Replace('JARVIS_REPLY_LANGUAGE=English', 'JARVIS_REPLY_LANGUAGE=Russian')
    $t = $t.Replace('JARVIS_DEEPGRAM_LANGUAGE=multi', 'JARVIS_DEEPGRAM_LANGUAGE=ru')
    $t = $t.Replace('JARVIS_WAKE_WORDS=jarvis,alfred,robbin,assist,time to work,wake up,six-one-nine', 'JARVIS_WAKE_WORDS=jarvis')
    $t = $t.Replace('JARVIS_WAKE_WORD_THRESHOLD=0.5', 'JARVIS_WAKE_WORD_THRESHOLD=0.45')
    $t = $t.Replace('JARVIS_FREELLMAPI_API_KEY=', 'JARVIS_FREELLMAPI_API_KEY=')
    if ($t -notmatch 'JARVIS_OPENROUTER_API_KEY=') {
        $anchor = 'JARVIS_FREELLMAPI_API_KEY='
        $t = $t.Replace($anchor, $anchor + "`r`n`r`n# ---- OpenRouter fast multilingual LLM -----------------------------------------------`r`nJARVIS_OPENROUTER_API_KEY=`r`nJARVIS_LLM_PRIMARY_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507`r`nJARVIS_LLM_FAST_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507")
    }
    $t = $t.Replace('JARVIS_LLM_FAST_MODEL=', '# JARVIS_LLM_FAST_MODEL is set above for the fast Russian voice/chat path')
    return $t
}

# 6) Local .env migration: preserve existing secrets. If a generic OPENROUTER_API_KEY exists, copy it
# into the project-scoped variable without printing it. Otherwise only set non-secret runtime switches.
$envPath = '.env'
if (Test-Path $envPath) {
    $envText = Get-Content $envPath -Raw -Encoding UTF8
    $generic = [Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY')
    if ($envText -match '(?m)^JARVIS_OPENROUTER_API_KEY\s*=\s*$' -and $generic) {
        $envText = [regex]::Replace($envText, '(?m)^JARVIS_OPENROUTER_API_KEY\s*=\s*$', 'JARVIS_OPENROUTER_API_KEY=' + $generic, 1)
    }
    if ($envText -notmatch '(?m)^JARVIS_OPENROUTER_API_KEY=') { $envText += "`r`nJARVIS_OPENROUTER_API_KEY=`r`n" }
    $sets = @{
        'JARVIS_REPLY_LANGUAGE'='Russian'; 'JARVIS_UNDERSTOOD_LANGUAGES'='Russian,English';
        'JARVIS_WHISPER_LANGUAGE'='ru'; 'JARVIS_DEEPGRAM_LANGUAGE'='ru'; 'JARVIS_DEEPGRAM_ENDPOINTING_MS'='500';
        'JARVIS_PIPER_VOICE'='ru_RU-ruslan-medium'; 'JARVIS_PRILER_REACTIONS'='true';
        'JARVIS_PRILER_VOICE'='jarvis-remaster'; 'JARVIS_PRILER_LANGUAGE'='ru';
        'JARVIS_WAKE_WORDS'='jarvis'; 'JARVIS_WAKE_WORD_THRESHOLD'='0.45'; 'JARVIS_LISTENING_PULSE'='false';
        'JARVIS_LLM_PRIMARY_MODEL'='openrouter:qwen/qwen3-30b-a3b-instruct-2507';
        'JARVIS_LLM_FAST_MODEL'='openrouter:qwen/qwen3-30b-a3b-instruct-2507';
        'JARVIS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS'='3.0'
    }
    foreach ($kv in $sets.GetEnumerator()) {
        $name = $kv.Key; $value = $kv.Value
        if ($envText -match "(?m)^$([regex]::Escape($name))=") {
            $envText = [regex]::Replace($envText, "(?m)^$([regex]::Escape($name))=.*$", "$name=$value", 1)
        } else { $envText += "`r`n$name=$value" }
    }
    Set-Content $envPath -Value $envText -Encoding UTF8 -NoNewline
    Write-Host 'UPDATED .env (secrets preserved; key value not printed)'
} else {
    Write-Warning '.env not found; source defaults were updated. Create .env from .env.example and add your existing OpenRouter key locally.'
}

Write-Host ''
Write-Host 'Russian runtime patch complete.' -ForegroundColor Green
Write-Host 'Next: uv run python -m unittest discover -s tests -v'
Write-Host 'Then start Jarvis normally and watch for: LLM route ... openrouter:qwen/qwen3-30b-a3b-instruct-2507'
