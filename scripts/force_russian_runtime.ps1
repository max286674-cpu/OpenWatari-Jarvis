$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Replace-Text([string]$path, [string]$old, [string]$new) {
    $p = Join-Path $root $path
    $s = Get-Content $p -Raw -Encoding UTF8
    if ($s.Contains($new)) { return }
    if (-not $s.Contains($old)) { throw "Patch target not found: $path :: $old" }
    Set-Content $p ($s.Replace($old,$new)) -Encoding UTF8
}

# Existing source defaults are generic, but this personal deployment is Russian.
Replace-Text 'src/jarvis/config.py' 'understood_languages: str = "English"' 'understood_languages: str = "Russian,English"'
Replace-Text 'src/jarvis/config.py' 'reply_language: str = "English"' 'reply_language: str = "Russian"'
Replace-Text 'src/jarvis/config.py' 'wake_words: str = "jarvis,alfred,robbin,assist,time to work,wake up,six-one-nine"' 'wake_words: str = "jarvis"'
Replace-Text 'src/jarvis/config.py' 'wake_word_threshold: float = 0.5' 'wake_word_threshold: float = 0.45'
Replace-Text 'src/jarvis/config.py' 'wake_ack_phrase: str = "Yes, sir?|I''m listening, sir.|Sir?|Go ahead, sir."' 'wake_ack_phrase: str = "Да, сэр.|Слушаю, сэр.|Да, сэр, я слушаю."'
Replace-Text 'src/jarvis/config.py' 'listening_pulse: bool = True' 'listening_pulse: bool = False'
Replace-Text 'src/jarvis/config.py' 'deepgram_endpointing_ms: int = 700' 'deepgram_endpointing_ms: int = 500'
Replace-Text 'src/jarvis/config.py' 'whisper_language: str = "en"' 'whisper_language: str = "ru"'
Replace-Text 'src/jarvis/config.py' 'piper_voice: str = "en_US-ryan-high"' 'piper_voice: str = "ru_RU-ruslan-medium"'

# Replace EVERY hard-coded English progress/ack phrase in the agent with Russian.
$agentPath = Join-Path $root 'src/jarvis/brain/agent.py'
$agent = Get-Content $agentPath -Raw -Encoding UTF8
$replacements = @{
'Right away, sir — putting that to the team lead'='Сейчас, сэр — передаю задачу команде'
'Checking your vault'='Проверяю хранилище'
'Reading that note'='Читаю заметку'
'Saving that to your vault'='Сохраняю в хранилище'
'Looking that up'='Проверяю информацию'
'Opening the page'='Открываю страницу'
'Opening a browser'='Открываю браузер'
'Checking your Telegram'='Проверяю Telegram'
'Reading that chat'='Читаю переписку'
'Sending that'='Отправляю'
'Pulling that from your playlist'='Ищу это в плейлисте'
'Cueing it up in your music room'='Готовлю музыку к воспроизведению'
'Leaving the music room'='Останавливаю музыку'
'Finding that song'='Ищу композицию'
'Stopping the music'='Останавливаю музыку'
'Opening that'='Открываю'
'Working on your files'='Работаю с файлами'
'On it'='Занимаюсь, сэр'
'Running that'='Выполняю команду'
'In the browser'='Работаю в браузере'
'Authorizing the protocol'='Запускаю протокол'
'Setting that reminder'='Устанавливаю напоминание'
'Pinging your phone'='Отправляю уведомление на телефон'
'Getting the time'='Уточняю время'
'Checking the weather'='Проверяю погоду'
'Checking your calendar'='Проверяю календарь'
'Adding that to your calendar'='Добавляю в календарь'
'Checking your email'='Проверяю почту'
'Sending that email'='Отправляю письмо'
'Noting that down'='Записываю'
'Let me recall'='Вспоминаю'
'Checking that device'='Проверяю устройство'
}
foreach ($k in $replacements.Keys) { $agent = $agent.Replace($k,$replacements[$k]) }
$agent = $agent.Replace('("Right away, sir.", "On it, sir.", "Of course, sir.", "Let me take care of that, sir.",','("Сейчас, сэр.", "Уже занимаюсь, сэр.", "Разумеется, сэр.", "Будет сделано, сэр.",')
$agent = $agent.Replace('"Consider it done, sir.")','"Принято, сэр.")')
$agent = $agent.Replace('("Yes, sir.", "Certainly, sir.", "Of course, sir.", "One moment, sir.")','("Да, сэр.", "Разумеется, сэр.", "Конечно, сэр.", "Слушаю, сэр.")')
Set-Content $agentPath $agent -Encoding UTF8

# Local .env is authoritative over config.py. Change only language/voice/latency values; never touch secrets.
$envPath = Join-Path $root '.env'
if (Test-Path $envPath) {
    $env = Get-Content $envPath -Raw -Encoding UTF8
    function Set-Env([string]$name,[string]$value) {
        $pattern = "(?m)^$([regex]::Escape($name))=.*$"
        if ($script:env -match $pattern) { $script:env = [regex]::Replace($script:env,$pattern,"$name=$value") }
        else { $script:env += "`r`n$name=$value" }
    }
    Set-Env 'JARVIS_REPLY_LANGUAGE' 'Russian'
    Set-Env 'JARVIS_UNDERSTOOD_LANGUAGES' 'Russian,English'
    Set-Env 'JARVIS_WHISPER_LANGUAGE' 'ru'
    Set-Env 'JARVIS_DEEPGRAM_LANGUAGE' 'ru'
    Set-Env 'JARVIS_DEEPGRAM_ENDPOINTING_MS' '500'
    Set-Env 'JARVIS_WAKE_WORDS' 'jarvis'
    Set-Env 'JARVIS_WAKE_WORD_THRESHOLD' '0.45'
    Set-Env 'JARVIS_WAKE_ACK_PHRASE' 'Да, сэр.|Слушаю, сэр.|Да, сэр, я слушаю.'
    Set-Env 'JARVIS_LISTENING_PULSE' 'false'
    Set-Env 'JARVIS_PIPER_VOICE' 'ru_RU-ruslan-medium'
    Set-Env 'JARVIS_TTS_FALLBACK_PROVIDER' 'piper'
    Set-Content $envPath $env -Encoding UTF8
}

Write-Host 'Russian runtime patch applied.' -ForegroundColor Green
Write-Host 'ElevenLabs API key and Voice ID were NOT modified.' -ForegroundColor Cyan
Write-Host 'Piper is forced to ru_RU-ruslan-medium whenever local fallback is used.' -ForegroundColor Cyan
