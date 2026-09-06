"""Idempotent runtime repair for the Windows voice client.
Repairs a checkout even if an older runtime patch stopped halfway through. No secrets are printed.
"""
from __future__ import annotations
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p): return (ROOT/p).read_text(encoding="utf-8")
def write(p,s): (ROOT/p).write_text(s,encoding="utf-8")

# config: preserve the existing full Settings schema.
p="src/jarvis/config.py"; s=read(p)
s=re.sub(r'llm_primary_model:\s*str\s*=\s*"[^"]+"','llm_primary_model: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"',s,count=1)
s=re.sub(r'llm_fallback_models:\s*str\s*=\s*\([^)]*\)', 'llm_fallback_models: str = "openrouter:google/gemini-2.5-flash-lite,openrouter:qwen/qwen3-30b-a3b-instruct-2507"',s,count=1,flags=re.S)
s=re.sub(r'llm_first_token_timeout_seconds:\s*float\s*=\s*[^\n]+','llm_first_token_timeout_seconds: float = 6.0',s,count=1)
if 'openrouter_api_key:' not in s:
    anchor='    freellmapi_api_key: str | None = None\n'
    s=s.replace(anchor,anchor+'    openrouter_api_key: str | None = Field(default=None, validation_alias=AliasChoices("JARVIS_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"))\n    openrouter_base_url: str = "https://openrouter.ai/api/v1"\n',1)
if 'from pydantic import AliasChoices, Field' not in s:
    s=s.replace('from enum import Enum\n','from enum import Enum\n\nfrom pydantic import AliasChoices, Field\n',1)
if 'desktop_tools_enabled:' not in s:
    s=s.replace('    pc_control_url: str | None = None\n','    pc_control_url: str | None = None\n    desktop_tools_enabled: bool = True\n',1)
write(p,s)

# llm: OpenRouter must not fall through to freellmapi.
p="src/jarvis/brain/llm.py"; s=read(p)
if '("openrouter:", settings.openrouter_base_url' not in s:
    anchor='            ("ollama:", settings.ollama_base_url, "ollama"),  # Ollama ignores the key\n'
    if anchor not in s: raise RuntimeError('anchor not found: OpenRouter resolver')
    s=s.replace(anchor,anchor+'            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),\n',1)
write(p,s)

# confirmation: only consequential external/destructive actions ask. App/process start/stop is frictionless.
p="src/jarvis/brain/proactive.py"; s=read(p)
s=s.replace('    "file_op", "process_op", "run_powershell", "browser",\n','    "file_op", "run_powershell", "browser",\n',1)
s=s.replace('        return (args or {}).get("action") in {"kill", "start"}\n','        return False\n',1)
write(p,s)

# tool registry.
p="src/jarvis/brain/tools/__init__.py"; s=read(p)
if '    office,\n    desktop,\n' not in s:
    s=s.replace('    activity,\n','    activity,\n    office,\n    desktop,\n',1)
if 'approvals, relationship, office, desktop' not in s:
    s=s.replace('approvals, relationship]  # noqa: E501','approvals, relationship, office, desktop]  # noqa: E501',1)
if '"office": [office]' not in s:
    anchor='    "relationship": [relationship],      # sensitivities / running jokes / how-we-stand\n'
    if anchor not in s: raise RuntimeError('anchor not found: lazy groups')
    s=s.replace(anchor,anchor+'    "office": [office],\n    "desktop": [desktop],\n',1)
if '"база данных"' not in s:
    anchor='    "relationship": ('
    if anchor not in s: raise RuntimeError('anchor not found: group triggers')
    s=s.replace(anchor,'    "office": ("word", "ворд", "excel", "эксель", "таблиц", "таблица", "база данных", "базу данных", "sqlite", "гост", "отчёт", "отчет", "лаборатор", "курсов", "диплом"),\n    "desktop": ("нажми", "нажать", "кликни", "кликнуть", "щелкни", "мышью", "клавиатурой", "экран", "на экране", "компьютером", "управляй компьютером", "сделай на экране"),\n'+anchor,1)
write(p,s)

# deterministic Russian PC intent routing.
p="src/jarvis/brain/intent_router.py"; s=read(p)
if 'закрой|закрыть|выключи|выключить|останови|остановить' not in s:
    anchor='_ROUTES: list[tuple[re.Pattern[str], list[str]]] = [\n'
    if anchor not in s: raise RuntimeError('anchor not found: route table')
    s=s.replace(anchor,anchor+'    (re.compile(r"\\b(закрой|закрыть|выключи|выключить|останови|остановить)\\b[^.?!]{0,50}", re.I), ["process_op"]),\n    (re.compile(r"\\b(открой|открыть|запусти|запустить)\\b[^.?!]{0,50}", re.I), ["open_app"]),\n',1)
write(p,s)

# deterministic Russian confirmation recognition.
p="src/jarvis/brain/agent.py"; s=read(p)
if 'def _is_affirmation(' not in s:
    anchor='def _is_work_intent(user_text: str) -> bool:\n    return bool(_WORK_INTENT_RE.search(user_text or ""))\n'
    if anchor not in s: raise RuntimeError('anchor not found: work intent')
    s=s.replace(anchor,anchor+'\n\n_AFFIRM_RE = re.compile(r"^\\s*(да|ага|угу|подтверждаю|подтверждаю это|делай|выполняй|устанавливай|разрешаю|согласен|конечно|yes|yeah|yep|ok|okay|do it|go ahead|confirm)\\s*[.!?]*\\s*$", re.I)\n\ndef _is_affirmation(text: str) -> bool:\n    return bool(_AFFIRM_RE.fullmatch((text or "").strip()))\n',1)
write(p,s)

# environment template.
p=".env.example"; s=read(p)
if 'JARVIS_OPENROUTER_API_KEY=' not in s:
    s+='\n# Direct OpenRouter\nJARVIS_OPENROUTER_API_KEY=\nJARVIS_LLM_PRIMARY_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507\nJARVIS_LLM_FALLBACK_MODELS=openrouter:google/gemini-2.5-flash-lite,openrouter:qwen/qwen3-30b-a3b-instruct-2507\nJARVIS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS=6\nJARVIS_DESKTOP_TOOLS_ENABLED=true\n'
write(p,s)
print('Runtime v10 applied successfully.')
