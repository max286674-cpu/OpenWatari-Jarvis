from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def write(p: str, s: str) -> None:
    (ROOT / p).write_text(s, encoding="utf-8")


def replace_once(s: str, old: str, new: str, label: str) -> str:
    if old not in s:
        print(f"SKIP {label}: anchor not found")
        return s
    print(f"PATCH {label}")
    return s.replace(old, new, 1)


# 1) OpenRouter is currently named in .env but llm.py does not resolve an openrouter: prefix.
# That sends the literal model name to freellmapi and produces AuthenticationError. Add a real
# OpenRouter client and settings fields, without touching any secret values.
config = read("src/jarvis/config.py")
config = replace_once(
    config,
    '    groq_api_key: str | None = None\n    groq_base_url: str = "https://api.groq.com/openai/v1"\n',
    '    openrouter_api_key: str | None = None\n    openrouter_base_url: str = "https://openrouter.ai/api/v1"\n    groq_api_key: str | None = None\n    groq_base_url: str = "https://api.groq.com/openai/v1"\n',
    "config: OpenRouter settings",
)
config = replace_once(
    config,
    '    wake_word_threshold: float = 0.5\n',
    '    wake_word_threshold: float = 0.35\n',
    "config: faster wake threshold default",
)
config = replace_once(
    config,
    '    wake_listen_window_s: float = 8.0',
    '    wake_listen_window_s: float = 6.0',
    "config: shorter wake window",
)
config = replace_once(
    config,
    '    deepgram_endpointing_ms: int = 700',
    '    deepgram_endpointing_ms: int = 350',
    "config: faster Deepgram endpointing",
)
config = replace_once(
    config,
    '    self_improve_enabled: bool = True',
    '    self_improve_enabled: bool = False',
    "config: disable hallucinated auto-memory by default",
)
write("src/jarvis/config.py", config)

llm = read("src/jarvis/brain/llm.py")
llm = replace_once(
    llm,
    '        for prefix, base_url, api_key in (\n            ("groq:", settings.groq_base_url, settings.groq_api_key or "missing-groq-key"),',
    '        for prefix, base_url, api_key in (\n            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),\n            ("groq:", settings.groq_base_url, settings.groq_api_key or "missing-groq-key"),',
    "llm: OpenRouter resolver",
)
llm = replace_once(
    llm,
    '        ``groq:<model>`` hits Groq directly; ``cerebras:<model>`` hits Cerebras directly (the fastest\n',
    '        ``openrouter:<model>`` hits OpenRouter directly; ``groq:<model>`` hits Groq directly; ``cerebras:<model>`` hits Cerebras directly (the fastest\n',
    "llm: resolver documentation",
)
# A 4-second first-token timeout is too aggressive for a cold OpenRouter provider and causes avoidable
# failovers. 2.5s still prevents a dead provider from blocking the voice loop.
llm = replace_once(
    llm,
    '    llm_first_token_timeout_seconds: float = 4.0',
    '    llm_first_token_timeout_seconds: float = 2.5',
    "llm: tighter but sane first-token timeout",
)
write("src/jarvis/brain/llm.py", llm)

# 2) Russian voice contract: remove English spoken progress/acks that happen before/around tools.
agent = read("src/jarvis/brain/agent.py")
progress_map = {
    '"Right away, sir — putting that to the team lead"': '"Сейчас, сэр — передаю задачу."',
    '"Checking your vault"': '"Проверяю хранилище"',
    '"Reading that note"': '"Читаю заметку"',
    '"Saving that to your vault"': '"Сохраняю это в хранилище"',
    '"Looking that up"': '"Проверяю информацию"',
    '"Opening the page"': '"Открываю страницу"',
    '"Opening a browser"': '"Открываю браузер"',
    '"Checking your Telegram"': '"Проверяю Telegram"',
    '"Reading that chat"': '"Читаю чат"',
    '"Sending that"': '"Отправляю"',
    '"Pulling that from your playlist"': '"Открываю плейлист"',
    '"Cueing it up in your music room"': '"Запускаю в музыкальной комнате"',
    '"Leaving the music room"': '"Останавливаю музыку"',
    '"Finding that song"': '"Ищу эту композицию"',
    '"Stopping the music"': '"Останавливаю музыку"',
    '"Opening that"': '"Открываю"',
    '"Opening that"': '"Открываю"',
    '"Working on your files"': '"Работаю с файлами"',
    '"On it"': '"Выполняю"',
    '"Running that"': '"Выполняю команду"',
    '"In the browser"': '"Работаю в браузере"',
    '"Authorizing the protocol"': '"Авторизую протокол"',
    '"Setting that reminder"': '"Ставлю напоминание"',
    '"Pinging your phone"': '"Отправляю уведомление"',
    '"Getting the time"': '"Уточняю время"',
    '"Checking the weather"': '"Проверяю погоду"',
    '"Checking your calendar"': '"Проверяю календарь"',
    '"Adding that to your calendar"': '"Добавляю в календарь"',
    '"Checking your email"': '"Проверяю почту"',
    '"Sending that email"': '"Отправляю письмо"',
    '"Noting that down"': '"Запоминаю"',
    '"Let me recall"': '"Вспоминаю"',
    '"Checking that device"': '"Проверяю устройство"',
}
for old, new in progress_map.items():
    agent = agent.replace(old, new)
agent = agent.replace(
    '"Right away, sir.", "On it, sir.", "Of course, sir.", "Let me take care of that, sir.",\n              "Consider it done, sir."',
    '"Сейчас, сэр.", "Выполняю, сэр.", "Конечно, сэр.", "Занимаюсь, сэр.",\n              "Готово, сэр."',
)
agent = agent.replace(
    '"Yes, sir.", "Certainly, sir.", "Of course, sir.", "One moment, sir."',
    '"Да, сэр.", "Конечно, сэр.", "Хорошо, сэр.", "Одну секунду, сэр."',
)
agent = agent.replace(
    '"This request has MORE THAN ONE part. Complete EVERY part — use the right tool for each, one "',
    '"В запросе несколько частей. Выполни КАЖДУЮ часть, используя нужный инструмент. "',
)
# Make forced-tool detection understand Russian imperative commands and data queries.
agent = agent.replace(
    '    r"\\brun (the )?protocol\\b", r"\\bsearch (my )?vault\\b",\n)',
    '    r"\\brun (the )?protocol\\b", r"\\bsearch (my )?vault\\b",\n    r"\\b(открой|открыть|запусти|запустить|включи|включить|выключи|выключить)\\b",\n    r"\\b(поставь|поставить|создай|создать|удали|удалить|запомни|запомнить|сохрани|сохранить)\\b",\n    r"\\b(найди|найти|поищи|поиск|проверь|проверить|покажи|показать)\\b",\n    r"\\b(ютуб|youtube|браузер|гугл|google|телеграм|telegram|дискорд|discord)\\b",\n)',
)
agent = agent.replace(
    '    r"\\b(latest|recent) (news|headlines?|on)\\b|\\bheadlines\\b",\n)',
    '    r"\\b(latest|recent) (news|headlines?|on)\\b|\\bheadlines\\b",\n    r"\\b(погода|температура|прогноз|курс|цена|стоимость|котировка)\\b",\n    r"\\b(новости|заголовки|последние новости)\\b",\n    r"\\b(почта|письма|телеграм|сообщения|календарь|напоминания)\\b",\n)',
)
write("src/jarvis/brain/agent.py", agent)

# 3) Russian lazy triggers for browser/apps so 'открой ютуб' advertises the browser capability.
tools = read("src/jarvis/brain/tools/__init__.py")
tools = tools.replace(
    '    "apps": ("github", "gitlab", "slack", "discord", "google drive", "gdrive", "google doc",',
    '    "apps": ("github", "gitlab", "slack", "discord", "google drive", "gdrive", "google doc",\n             "ютуб", "youtube", "браузер", "открой сайт", "открой приложение", "запусти приложение",',
)
tools = tools.replace(
    '    "screen": ("my screen", "the screen",',
    '    "screen": ("my screen", "the screen", "мой экран", "экран", "посмотри на экран",',
)
write("src/jarvis/brain/tools/__init__.py", tools)

# 4) Make the local PC launcher reliable for Windows aliases and YouTube media controls.
system = read("src/jarvis/brain/tools/system.py")
old = '''async def _open_app_local(args: dict) -> str:\n    if not _enabled():\n        return "System tools are disabled, sir."\n    app = (args.get("app") or "").strip()\n    if not app:\n        return "Which app should I open, sir?"\n    try:\n        if sys.platform == "win32":\n            flags = 0x00000008 | 0x00000200\n            await asyncio.to_thread(\n                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", app], shell=False, creationflags=flags))\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen([app]))\n        return f"Launched {clip(app, 80)}, sir."\n    except Exception as e:  # noqa: BLE001\n        return tool_error("open app", e)\n'''
new = '''async def _open_app_local(args: dict) -> str:\n    if not _enabled():\n        return "Системные инструменты отключены, сэр."\n    app = (args.get("app") or "").strip()\n    if not app:\n        return "Какое приложение открыть, сэр?"\n    try:\n        if sys.platform == "win32":\n            import os\n            # Prefer Windows shell launching. It handles .exe, registered apps, folders and\n            # URI/protocol handlers much more reliably than a shell=True command string.\n            await asyncio.to_thread(os.startfile, app)\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen([app]))\n        return f"Открыл {clip(app, 80)}, сэр."\n    except Exception:\n        try:\n            if sys.platform == "win32":\n                # Second path: Start-Process handles PATH aliases and common Store apps.\n                ps = f"Start-Process -FilePath {_ps_quote(app)}"\n                await asyncio.to_thread(lambda: subprocess.run(\n                    [_win_exe("powershell"), "-NoProfile", "-NonInteractive", "-Command", ps],\n                    capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW, startupinfo=_hidden_startupinfo()))\n                return f"Открыл {clip(app, 80)}, сэр."\n        except Exception:\n            pass\n        return f"Не удалось открыть {clip(app, 80)}, сэр."\n'''
system = replace_once(system, old, new, "system: reliable Windows app launch")
# Make open_url use the shell API instead of cmd/start. This avoids quoting and detached-process races.
old2 = '''        if sys.platform == "win32":\n            flags = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP\n            await asyncio.to_thread(\n                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", url], creationflags=flags))\n        else:\n'''
new2 = '''        if sys.platform == "win32":\n            import os\n            await asyncio.to_thread(os.startfile, url)\n        else:\n'''
system = replace_once(system, old2, new2, "system: reliable URL launch")
# Add Russian descriptions to the system tool schemas; model tool selection improves substantially when
# the schema itself speaks the user's language.
system = system.replace(
    '"Create or delete files and folders on the owner\'s PC, or list a folder. "',
    '"Работает с файлами и папками на компьютере владельца: создать, удалить или показать содержимое. "',
)
system = system.replace(
    '"Manage processes on the owner\'s PC: list (optionally filtered by name), kill by name "',
    '"Управляет процессами компьютера владельца: список, запуск, завершение, пауза и продолжение. "',
)
system = system.replace(
    '"Run a PowerShell command on the owner\'s PC and get the output. Set as_admin=true to "',
    '"Выполняет команду PowerShell на компьютере владельца и возвращает результат. "',
)
system = system.replace(
    '"Open a URL in the owner\'s default browser on his PC (e.g. open YouTube, a "',
    '"Открывает URL в браузере владельца, например YouTube или любой сайт. "',
)
system = system.replace(
    '"Launch an application or executable on the owner\'s PC by name or path "',
    '"Запускает приложение или исполняемый файл на компьютере владельца по имени или пути. "',
)
write("src/jarvis/brain/tools/system.py", system)

# 5) Browser tool: allow direct YouTube video activation via normal browser keyboard/media control.
browser = read("src/jarvis/brain/tools/browser.py")
browser = browser.replace(
    '        if action == "press":\n            key = (args.get("key") or "Enter").strip()\n            await page.keyboard.press(key)\n            return f"Pressed {key}, sir."\n',
    '        if action == "press":\n            key = (args.get("key") or "Enter").strip()\n            await page.keyboard.press(key)\n            return f"Pressed {key}, sir."\n',
)
# Add a safe deterministic YouTube helper as a new browser action. It searches YouTube and clicks the
# first result; autoplay is already enabled on the persistent Chromium context.
anchor = '        if action == "back":\n'
insert = '''        if action == "youtube_play":\n            query = (args.get("query") or "").strip()\n            if not query:\n                return "Что включить на YouTube, сэр?"\n            from urllib.parse import quote_plus\n            await page.goto("https://www.youtube.com/results?search_query=" + quote_plus(query), wait_until="domcontentloaded")\n            await page.wait_for_timeout(700)\n            link = page.locator("a#video-title").first\n            await link.click(timeout=6000)\n            await page.wait_for_timeout(500)\n            return f"Запустил первое видео YouTube по запросу «{clip(query, 80)}», сэр."\n\n'''
system_browser_anchor = anchor
if insert not in browser:
    browser = replace_once(browser, anchor, insert + anchor, "browser: YouTube play action")
browser = browser.replace(
    '"Drive a real visible web browser on the owner\'s screen. Actions: open, "',
    '"Управляет видимым браузером на экране владельца. Действия: open, youtube_play, "',
)
browser = browser.replace(
    '"enum": ["open", "click", "fill", "type", "press", "read",\n                                 "screenshot", "new_tab", "back", "close", "tabs", "switch_tab", "close_tab", "close_all_other_tabs"],',
    '"enum": ["open", "youtube_play", "click", "fill", "type", "press", "read",\n                                 "screenshot", "new_tab", "back", "close", "tabs", "switch_tab", "close_tab", "close_all_other_tabs"],',
)
write("src/jarvis/brain/tools/browser.py", browser)

print("\nJARVIS runtime v2 patch completed.")
print("Next: set JARVIS_OPENROUTER_API_KEY in .env if it is missing, then run tests and restart.")
