from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")

def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")

def patch_agent() -> None:
    p = "src/jarvis/brain/agent.py"
    s = read(p)
    affirmation = '''# Confirmation is intentionally deterministic: a Russian "да" must execute the
# exact pending action rather than starting another LLM turn.
_AFFIRM_RE = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"
    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that's right|correct|fine|"
    r"absolutely|yes please|go|right|да|ага|угу|ок|окей|хорошо|конечно|подтверждаю|подтверждено|"
    r"подтверждай|разрешаю|разрешено|делай|делайте|выполняй|выполняйте|выполни|выполнить|"
    r"запускай|запускайте|устанавливай|устанавливайте|установи|установить|продолжай|продолжайте|"
    r"можно|добро|верно|точно|давай|давай делай)[\\s,.!?;:]*$",
    re.IGNORECASE,
)

def _is_affirmation(text: str) -> bool:
    t = re.sub(r"[\\s,.!?;:]+", " ", (text or "").strip().lower()).strip()
    return bool(_AFFIRM_RE.fullmatch(t))'''

    # Replace BOTH the current repaired block and the original legacy English-only block.
    # Callable replacement is mandatory because the replacement itself contains regex backslashes.
    block = re.compile(
        r"(?ms)^# (?:A short affirmation that grants a pending confirmation|Confirmation is intentionally deterministic):.*?"
        r"^def _is_affirmation\(text: str\) -> bool:\n    return .*?(?=\n\n# Pure conversational turns|\n\ndef _is_pure_chat|\Z)"
    )
    s2, n = block.subn(lambda _m: affirmation, s, count=1)
    if n == 0:
        # Last-resort replacement of any _AFFIRM_RE + helper block, regardless of its comment.
        block2 = re.compile(
            r"(?ms)^_AFFIRM_RE = re\.compile\(.*?^def _is_affirmation\(text: str\) -> bool:\n    return .*?(?=\n\n#|\n\ndef )"
        )
        s2, n = block2.subn(lambda _m: affirmation + "\n\n", s, count=1)
    if n == 0:
        raise RuntimeError("repair anchor not found: affirmation helper")
    write(p, s2)

def patch_router() -> None:
    p = "src/jarvis/brain/intent_router.py"
    s = read(p)
    marker = "_ROUTES: list[tuple[re.Pattern[str], list[str]]] = [\n"
    routes = (
        '    (re.compile(r"\\b(?:закрой|закрыть|выключи|выключить|останови|остановить|заверши|завершить)\\b", re.I), ["process_op"]),\n'
        '    (re.compile(r"\\b(?:открой|открыть|запусти|запустить|включи|включить)\\b", re.I), ["open_app"]),\n'
    )
    if marker not in s:
        raise RuntimeError("repair anchor not found: intent route table")
    if "закрой|закрыть" not in s:
        s = s.replace(marker, marker + routes, 1)
    write(p, s)

def patch_llm() -> None:
    p = "src/jarvis/brain/llm.py"
    s = read(p)
    if '("openrouter:", settings.openrouter_base_url' not in s:
        anchors = [
            '            ("ollama:", settings.ollama_base_url, "ollama"),',
            '            ("ollama:", settings.ollama_base_url, "ollama"),  # Ollama ignores the key',
        ]
        anchor = next((a for a in anchors if a in s), None)
        if anchor is None:
            raise RuntimeError("repair anchor not found: OpenRouter resolver")
        s = s.replace(anchor, anchor + '\n            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),', 1)
    write(p, s)

def patch_config() -> None:
    p = "src/jarvis/config.py"
    s = read(p)
    if "openrouter_api_key:" not in s:
        anchors = ['    freellmapi_api_key: str | None = None\n', '    minimax_api_key: str | None = None\n']
        anchor = next((a for a in anchors if a in s), None)
        if anchor is None:
            raise RuntimeError("repair anchor not found: config provider key block")
        addition = anchor + (
            "    # OpenRouter: OpenAI-compatible gateway for the owner's model pool.\n"
            '    openrouter_api_key: str | None = None\n'
            '    openrouter_base_url: str = "https://openrouter.ai/api/v1"\n'
        )
        s = s.replace(anchor, addition, 1)
    s = re.sub(r'llm_first_token_timeout_seconds:\s*float\s*=\s*[^\n]+', 'llm_first_token_timeout_seconds: float = 6.0', s, count=1)
    write(p, s)

def patch_confirm_policy() -> None:
    p = "src/jarvis/brain/proactive.py"
    s = read(p)
    s = s.replace('    "file_op", "process_op", "run_powershell", "browser",\n', '    "file_op", "run_powershell", "browser",\n')
    s = s.replace('        return (args or {}).get("action") in {"kill", "start"}\n', '        return False\n')
    write(p, s)

def patch_pyproject() -> None:
    p = "pyproject.toml"
    s = read(p)
    if "office = [" not in s:
        marker = "[project.optional-dependencies]\n"
        if marker not in s:
            raise RuntimeError("repair anchor not found: optional dependencies")
        s = s.replace(marker, marker + 'office = [\n    "python-docx>=1.1",\n    "openpyxl>=3.1",\n]\n' + 'desktop = [\n    "pyautogui>=0.9.54",\n]\n', 1)
    write(p, s)

def main() -> None:
    patch_config()
    patch_llm()
    patch_agent()
    patch_router()
    patch_confirm_policy()
    patch_pyproject()
    print("runtime v10 repair applied")

if __name__ == "__main__":
    main()
