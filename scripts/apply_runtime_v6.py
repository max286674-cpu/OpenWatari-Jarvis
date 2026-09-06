from pathlib import Path
import os, py_compile, re

ROOT = Path(__file__).resolve().parents[1]

def replace(path, old, new):
    p=ROOT/path; s=p.read_text(encoding='utf-8')
    if old not in s: raise SystemExit(f'ANCHOR NOT FOUND: {path}: {old[:90]!r}')
    p.write_text(s.replace(old,new,1), encoding='utf-8'); print('UPDATED',path)

replace('src/jarvis/config.py','    hot_mic_after_wake: bool = False','    hot_mic_after_wake: bool = True')
replace('src/jarvis/config.py','    wake_word_threshold: float = 0.5','    wake_word_threshold: float = 0.35')
replace('src/jarvis/config.py','    deepgram_endpointing_ms: int = 700','    deepgram_endpointing_ms: int = 350')
replace('src/jarvis/config.py','    llm_first_token_timeout_seconds: float = 4.0','    llm_first_token_timeout_seconds: float = 2.5')
replace('src/jarvis/config.py','    tts_affect_enabled: bool = True','    tts_affect_enabled: bool = False')
replace('src/jarvis/config.py','    reply_language: str = "English"','    reply_language: str = "Russian"')
replace('src/jarvis/config.py','    understood_languages: str = "English"','    understood_languages: str = "Russian,English"')
replace('src/jarvis/config.py','    deepgram_language: str = "multi"','    deepgram_language: str = "ru"')
replace('src/jarvis/config.py','    freellmapi_api_key: str | None = None','    freellmapi_api_key: str | None = None\n    openrouter_api_key: str | None = None\n    openrouter_base_url: str = "https://openrouter.ai/api/v1"')
replace('src/jarvis/brain/llm.py','''            ("ollama:", settings.ollama_base_url, "ollama"),  # Ollama ignores the key
        ):''','''            ("ollama:", settings.ollama_base_url, "ollama"),  # Ollama ignores the key
            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),
        ):''')

env=ROOT/'.env'
if env.exists():
    lines=env.read_text(encoding='utf-8').splitlines(); vals={}
    for line in lines:
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1); vals[k.strip()]=v.strip()
    key=vals.get('JARVIS_OPENROUTER_API_KEY') or vals.get('OPENROUTER_API_KEY') or os.environ.get('OPENROUTER_API_KEY')
    updates={'JARVIS_REPLY_LANGUAGE':'Russian','JARVIS_UNDERSTOOD_LANGUAGES':'Russian,English','JARVIS_DEEPGRAM_LANGUAGE':'ru','JARVIS_HOT_MIC_AFTER_WAKE':'true','JARVIS_WAKE_WORD_THRESHOLD':'0.35','JARVIS_DEEPGRAM_ENDPOINTING_MS':'350','JARVIS_TTS_AFFECT_ENABLED':'false','JARVIS_LLM_PRIMARY_MODEL':'openrouter:qwen/qwen3-30b-a3b-instruct-2507','JARVIS_LLM_FAST_MODEL':'','JARVIS_LLM_FALLBACK_MODELS':'openrouter:google/gemini-2.5-flash-lite,openrouter:qwen/qwen3-30b-a3b-instruct-2507','JARVIS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS':'2.5','JARVIS_SYSTEM_TOOLS_ENABLED':'true','JARVIS_BROWSER_TOOLS_ENABLED':'true'}
    if key: updates['JARVIS_OPENROUTER_API_KEY']=key
    existing={}; out=[]
    for line in lines:
        if '=' in line and not line.lstrip().startswith('#'):
            k=line.split('=',1)[0].strip(); existing[k]=len(out)
        out.append(line)
    for k,v in updates.items():
        if k in existing: out[existing[k]]=f'{k}={v}'
        else: out.append(f'{k}={v}')
    env.write_text('\n'.join(out)+'\n',encoding='utf-8'); print('UPDATED .env (key preserved, not printed)')
else: print('WARNING: .env not found; OpenRouter key must be configured locally')

p=ROOT/'src/jarvis/brain/agent.py'; s=p.read_text(encoding='utf-8')
start=s.index('    def _immediate_ack('); end=s.index('\n    async def respond_stream(',start)
s=s[:start]+'''    def _immediate_ack(self, user_text: str, on_progress: Callable | None) -> None:\n        # No synthetic filler: speak only useful results.\n        return\n'''+s[end:]
old='''            if on_progress:\n                on_progress(_ack_for(name, args))\n            runnable.append((idx, name, args))'''
if old not in s: raise SystemExit('tool ack anchor missing')
s=s.replace(old,'            runnable.append((idx, name, args))',1)
ws=s.index('    async def _await_with_progress('); we=s.index('\n    def _immediate_ack(',ws)
watch='''    async def _await_with_progress(self, coro, on_progress: Callable | None, name: str = ""):\n        task = asyncio.ensure_future(coro)\n        timeout = max(8.0, min(30.0, float(settings.tool_slow_warn_seconds) * 3.0))\n        try:\n            return await asyncio.wait_for(task, timeout=timeout)\n        except asyncio.TimeoutError:\n            task.cancel()\n            try: await task\n            except asyncio.CancelledError: pass\n            raise TimeoutError(f"tool {name} exceeded {timeout:.0f}s timeout")\n'''
s=s[:ws]+watch+s[we:]
anchor='    async def _respond_stream_impl(self, user_text: str, on_progress: Callable | None = None):\n'
helper=r'''    async def _direct_pc_command(self, text: str):
        t=(text or '').strip().lower()
        from jarvis.brain.tools.system import open_app, open_url, media_pause
        apps={'блокнот':'notepad.exe','нотпад':'notepad.exe','калькулятор':'calc.exe','проводник':'explorer.exe','хром':'chrome.exe','chrome':'chrome.exe','гугл хром':'chrome.exe','firefox':'firefox.exe','фаерфокс':'firefox.exe','дискорд':'discord.exe','телеграм':'telegram.exe','telegram':'telegram.exe','спотифай':'spotify.exe','spotify':'spotify.exe','стим':'steam.exe','steam':'steam.exe','код':'code.exe','vs code':'code.exe','вс код':'code.exe'}
        m=re.match(r'^(?:джарвис[,.]?\s*)?(?:открой|запусти|включи)\s+(.+?)\s*$',t)
        if m:
            target=m.group(1).strip().strip('"')
            if target in ('ютуб','youtube','ютаб'): return await open_url({'url':'https://www.youtube.com'})
            if target in apps: return await open_app({'app':apps[target]})
            if target.startswith(('http://','https://','www.')) or '.com' in target or '.ru' in target: return await open_url({'url':target})
        if re.match(r'^(?:джарвис[,.]?\s*)?(?:пауза|поставь.*паузу)(?:\s+видео|\s+музыку)?$',t): return await media_pause({})
        if re.match(r'^(?:джарвис[,.]?\s*)?(?:продолжи|возобнови)(?:\s+видео|\s+музыку)?$',t): return await media_pause({})
        return None

'''
if anchor not in s: raise SystemExit('stream anchor missing')
s=s.replace(anchor,helper+anchor,1)
needle='''        self._immediate_ack(user_text, on_progress)\n        self._history.append({"role": "user", "content": user_text})'''
repl='''        self._immediate_ack(user_text, on_progress)\n        direct = await self._direct_pc_command(user_text)\n        if direct is not None:\n            clean = _clean_reply(direct) or "Готово, сэр."\n            self._history.append({"role":"user","content":user_text})\n            self._history.append({"role":"assistant","content":clean})\n            self._trim(); self._stream_done=True\n            yield clean\n            return\n        self._history.append({"role": "user", "content": user_text})'''
if needle not in s: raise SystemExit('direct command insertion anchor missing')
s=s.replace(needle,repl,1)
p.write_text(s,encoding='utf-8'); print('UPDATED agent.py')

p=ROOT/'src/jarvis/brain/tools/system.py'; s=p.read_text(encoding='utf-8')
old='''async def _open_app_local(args: dict) -> str:\n    if not _enabled():\n        return "System tools are disabled, sir."\n    app = (args.get("app") or "").strip()\n    if not app:\n        return "Which app should I open, sir?"\n    try:\n        if sys.platform == "win32":\n            flags = 0x00000008 | 0x00000200\n            await asyncio.to_thread(\n                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", app], shell=False, creationflags=flags))\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen([app]))\n        return f"Launched {clip(app, 80)}, sir."\n    except Exception as e:  # noqa: BLE001\n        return tool_error("open app", e)\n'''
new='''async def _open_app_local(args: dict) -> str:\n    if not _enabled(): return "Системное управление отключено."\n    app=(args.get("app") or "").strip().strip('"')\n    if not app: return "Не указано приложение."\n    try:\n        if sys.platform == "win32":\n            import os\n            await asyncio.to_thread(os.startfile, app)\n        else: await asyncio.to_thread(lambda: subprocess.Popen([app]))\n        return f"Запустил {clip(app,80)}."\n    except Exception:\n        if sys.platform == "win32":\n            try:\n                await asyncio.to_thread(subprocess.Popen,[_win_exe("powershell"),"-NoProfile","-NonInteractive","-Command","Start-Process -FilePath "+_ps_quote(app)],creationflags=_NO_WINDOW,startupinfo=_hidden_startupinfo())\n                return f"Запустил {clip(app,80)}."\n            except Exception as e: return tool_error("open app",e)\n        return tool_error("open app",Exception("unsupported platform"))\n'''
if old not in s: raise SystemExit('open_app anchor missing')
s=s.replace(old,new,1); p.write_text(s,encoding='utf-8'); print('UPDATED system.py')

for rel in ['src/jarvis/config.py','src/jarvis/brain/llm.py','src/jarvis/brain/agent.py','src/jarvis/brain/tools/system.py']:
    py_compile.compile(str(ROOT/rel),doraise=True)
print('PY_COMPILE_OK')
print('Runtime v6 applied. Run: uv run pytest -q')
