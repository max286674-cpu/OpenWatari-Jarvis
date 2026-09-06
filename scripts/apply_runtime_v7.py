from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: anchor not found")
    return text.replace(old, new, 1)


def patch_config() -> None:
    p = "src/jarvis/config.py"
    s = read(p)
    if "openrouter_api_key:" not in s:
        anchor = '    minimax_base_url: str = "https://api.minimax.io/v1"\n'
        s = replace_once(s, anchor, anchor + '    openrouter_api_key: str | None = None\n    openrouter_base_url: str = "https://openrouter.ai/api/v1"\n', "OpenRouter config")
    s = re.sub(r'llm_first_token_timeout_seconds:\s*float\s*=\s*[^\n]+', 'llm_first_token_timeout_seconds: float = 6.0', s, count=1)
    write(p, s)


def patch_llm() -> None:
    p = "src/jarvis/brain/llm.py"
    s = read(p)
    if '("openrouter:", settings.openrouter_base_url' not in s:
        anchor = '            ("minimax:", settings.minimax_base_url, settings.minimax_api_key or "missing-minimax-key"),\n'
        s = replace_once(s, anchor, anchor + '            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),\n', "OpenRouter resolver")
    write(p, s)


def patch_system() -> None:
    p = "src/jarvis/brain/tools/system.py"
    s = read(p)
    old = '''async def _open_app_local(args: dict) -> str:\n    if not _enabled():\n        return "System tools are disabled, sir."\n    app = (args.get("app") or "").strip()\n    if not app:\n        return "Which app should I open, sir?"\n    try:\n        if sys.platform == "win32":\n            flags = 0x00000008 | 0x00000200\n            await asyncio.to_thread(\n                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", app], shell=False, creationflags=flags))\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen([app]))\n        return f"Launched {clip(app, 80)}, sir."\n    except Exception as e:\n        return tool_error("open app", e)\n'''
    new = '''async def _open_app_local(args: dict) -> str:\n    if not _enabled():\n        return "Системное управление отключено."\n    app = (args.get("app") or "").strip()\n    if not app:\n        return "Какое приложение открыть?"\n    try:\n        if sys.platform == "win32":\n            import os\n            await asyncio.to_thread(os.startfile, app)\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen([app]))\n        return f"Открыл {clip(app, 80)}."\n    except Exception:\n        try:\n            if sys.platform == "win32":\n                await asyncio.to_thread(subprocess.Popen, [app], creationflags=_NO_WINDOW, startupinfo=_hidden_startupinfo())\n            else:\n                await asyncio.to_thread(lambda: subprocess.Popen([app]))\n            return f"Открыл {clip(app, 80)}."\n        except Exception as e:\n            return tool_error("open app", e)\n'''
    if old in s:
        s = s.replace(old, new, 1)
    old_url = '''        if sys.platform == "win32":\n            flags = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP\n            await asyncio.to_thread(\n                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", url], creationflags=flags))\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen(["xdg-open", url]))\n'''
    new_url = '''        if sys.platform == "win32":\n            import os\n            await asyncio.to_thread(os.startfile, url)\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen(["xdg-open", url]))\n'''
    if old_url in s:
        s = s.replace(old_url, new_url, 1)
    write(p, s)


def patch_bridge() -> None:
    p = "src/jarvis/edge/brain_bridge.py"
    s = read(p)
    s = re.sub(r'\n\s*await self\.push_frame\(TTSSpeakFrame\("Переключаюсь, сэр\."\)\)', '', s)
    s = re.sub(r'\n\s*await self\.push_frame\(TTSSpeakFrame\("Одну секунду, сэр\."\)\)', '', s)
    s = re.sub(r'\n\s*def progress\(note: str\) -> None:\n\s*asyncio\.create_task\(self\.push_frame\(TTSSpeakFrame\(note\)\)\)', '\n        def progress(note: str) -> None:\n            return', s)
    write(p, s)


def patch_intent_router() -> None:
    p = "src/jarvis/brain/intent_router.py"
    s = read(p)
    marker = '    # -- reads: the fabrication / wrong-tool zone the benchmark punished --\n'
    if 'закрой|закрыть' not in s:
        route = '''    # -- Windows PC control: close/stop commands are deterministic and go to process_op.\n    # The downstream confirmation gate still protects the actual kill operation.\n    (re.compile(r"\\b(закрой|закрыть|выключи|выключить|останови|остановить)\\b[^.?!]{0,35}\\b(приложение|программу|окно|браузер|chrome|хром|firefox|фаерфокс|telegram|телеграм|discord|дискорд|spotify|спотифай|steam|стим|notepad|блокнот|калькулятор|calculator|vscode|vs code)\\b|\\b(close|shut down|stop|terminate|kill)\\b[^.?!]{0,35}\\b(app|application|program|window|chrome|firefox|telegram|discord|spotify|steam|notepad|calculator)\\b", re.I), ["process_op"]),\n    (re.compile(r"\\b(открой|открыть|запусти|запустить)\\b[^.?!]{0,35}\\b(приложение|программу|chrome|хром|firefox|фаерфокс|telegram|телеграм|discord|дискорд|spotify|спотифай|steam|стим|notepad|блокнот|калькулятор)\\b", re.I), ["open_app"]),\n'''
        s = replace_once(s, marker, route + marker, "Russian PC routes")
    write(p, s)


def patch_agent() -> None:
    p = "src/jarvis/brain/agent.py"
    s = read(p)
    if '\nimport sys\n' not in s:
        s = s.replace('import re\n', 'import re\nimport subprocess\nimport sys\n', 1)
    # Russian confirmation is the main bug: the old regex accepted only English affirmations.\n    old_aff = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right)\\b",\n    re.IGNORECASE,\n)'''
    new_aff = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(да|ага|угу|точно|конечно|подтверждаю|подтверждено|подтвержден|"\n    r"делай|сделай|выполняй|выполни|запускай|запусти|устанавливай|установи|"\n    r"отправляй|отправь|удаляй|удали|закрывай|закрой|давай|можно|разрешаю|"\n    r"yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|"\n    r"confirm|confirmed|affirmative|sounds good|go for it|proceed|send it|do that|"\n    r"that'?s right|correct|fine|absolutely|yes please|go|right)\\b",\n    re.IGNORECASE,\n)'''
    if old_aff in s:
        s = s.replace(old_aff, new_aff, 1)
    # Prevent raw news/tool English from bypassing Russian rephrasing.
    s = s.replace('    "define_word", "wiki_lookup", "news_brief",\n', '    "define_word", "wiki_lookup",\n', 1)
    # A model failure must degrade to a controlled reply instead of killing the whole turn.\n    s = s.replace('''                except RuntimeError:\n                    if attempt == "auto":\n                        raise\n                    continue  # forced tool_choice rejected by every model — retry on auto\n''', '''                except RuntimeError:\n                    if attempt == "auto":\n                        logger.warning("LLM stream failed after fallback; ending turn gracefully")\n                        break\n                    continue  # forced tool_choice rejected — retry on auto\n''', 1)
    # Same protection for blocking path.\n    s = s.replace('''            except RuntimeError:\n                # A model in the chain may reject forced tool_choice — retry this pass on "auto".\n                if choice == "auto":\n                    raise\n                msg = await self._llm.complete(messages, tools=turn_tools, tool_choice="auto",\n                                               skip_primary=prefer_fb)\n''', '''            except RuntimeError:\n                # Never crash the voice loop because every model timed out.\n                if choice == "auto":\n                    self._history.append({"role": "assistant", "content": "Не смог получить ответ от модели. Попробую ещё раз."})\n                    self._trim()\n                    return "Не смог получить ответ от модели. Попробую ещё раз."\n                try:\n                    msg = await self._llm.complete(messages, tools=turn_tools, tool_choice="auto",\n                                                   skip_primary=prefer_fb)\n                except RuntimeError:\n                    self._history.append({"role": "assistant", "content": "Модель сейчас не отвечает. Попробую ещё раз."})\n                    self._trim()\n                    return "Модель сейчас не отвечает. Попробую ещё раз."\n''', 1)
    # Deterministic pending-confirm execution: the owner's "да" executes the EXACT held action; it never\n    # goes back to the LLM to regenerate the same request and ask again.\n    marker = '        messages = [self._system, *self._history]\n'
    block = '''        if self._confirm_granted and self._pending_confirm:\n            pending = dict(self._pending_confirm)\n            call = {"id": "confirmed-pending", "name": pending["name"],\n                    "arguments": json.dumps(pending["args"], ensure_ascii=False)}\n            outcomes = await self._execute_calls(messages, [call], "", on_progress)\n            result = _clean_reply(outcomes[0]["result"]) if outcomes else ""\n            if not result:\n                result = "Действие выполнено." if outcomes and outcomes[0]["ok"] else "Не удалось выполнить действие."\n            self._history.append({"role": "assistant", "content": result})\n            self._trim()\n            self._spawn_review()\n            self._confirm_granted = False\n            self._pending_confirm = None\n            return result\n'''
    # Apply in both blocking and streaming paths separately.\n    if 'call = {"id": "confirmed-pending"' not in s:\n        # First occurrence is blocking respond.\n        s = replace_once(s, marker, marker + block, "blocking confirmation dispatch")\n        # Streaming has same marker after _respond_stream_impl; locate remaining occurrence.\n        stream_block = block.replace('            return result\n', '            self._stream_done = True\n            yield result\n            return\n')\n        s = replace_once(s, marker, marker + stream_block, "stream confirmation dispatch")\n    # Disable generic English immediate filler; Priler is the acknowledgement layer.\n    s = re.sub(r'(?ms)^    def _immediate_ack\(self, user_text: str, on_progress: Callable \| None\) -> None:\n.*?(?=^    async def respond_stream)', '    def _immediate_ack(self, user_text: str, on_progress: Callable | None) -> None:\n        return\n\n', s, count=1)
    s = s.replace('                logger.exception(f"tool {name} raised")\n', '                logger.error(f"tool {name} failed: {type(e).__name__}")\n', 1)
    write(p, s)


def patch_env() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    s = p.read_text(encoding="utf-8")
    values = {
        "JARVIS_LLM_PRIMARY_MODEL": "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
        "JARVIS_LLM_FAST_MODEL": "",
        "JARVIS_LLM_FALLBACK_MODELS": "openrouter:google/gemini-2.5-flash-lite,openrouter:qwen/qwen3-30b-a3b-instruct-2507",
        "JARVIS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS": "6",
        "JARVIS_SYSTEM_TOOLS_ENABLED": "true",
        "JARVIS_BROWSER_TOOLS_ENABLED": "true",
        "JARVIS_HOT_MIC_AFTER_WAKE": "true",
        "JARVIS_WAKE_WORD_THRESHOLD": "0.35",
        "JARVIS_DEEPGRAM_ENDPOINTING_MS": "350",
    }
    for key, value in values.items():
        if re.search(rf"(?m)^{re.escape(key)}=", s):
            s = re.sub(rf"(?m)^{re.escape(key)}=.*$", f"{key}={value}", s)
        else:
            s += f"\n{key}={value}\n"
    if "JARVIS_OPENROUTER_API_KEY=" not in s:
        key = os.environ.get("JARVIS_OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
        if key:
            s += f"\nJARVIS_OPENROUTER_API_KEY={key}\n"
    p.write_text(s, encoding="utf-8")


def main() -> None:
    patch_config(); patch_llm(); patch_system(); patch_bridge(); patch_intent_router(); patch_agent(); patch_env()
    import py_compile
    for rel in ("src/jarvis/config.py", "src/jarvis/brain/llm.py", "src/jarvis/brain/agent.py", "src/jarvis/brain/tools/system.py", "src/jarvis/brain/intent_router.py", "src/jarvis/edge/brain_bridge.py"):
        py_compile.compile(str(ROOT / rel), doraise=True)
    print("Runtime v8 applied: confirmation, Russian routing, close/open control, LLM graceful failure, syntax OK.")
    print("Run: uv run pytest -q")


if __name__ == "__main__":
    main()
