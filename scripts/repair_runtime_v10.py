from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text: str, pattern: str, replacement: str, label: str, flags: int = 0) -> str:
    out, n = re.subn(pattern, replacement, text, count=1, flags=flags)
    if n != 1:
        raise RuntimeError(f"repair anchor not found: {label}")
    return out


def patch_agent() -> None:
    p = "src/jarvis/brain/agent.py"
    s = read(p)

    affirmation = r'''_AFFIRM_RE = re.compile(
    r"^\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"
    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"
    r"correct|fine|absolutely|yes please|go|right|"
    r"да|ага|угу|конечно|подтверждаю|подтверждено|подтверждай|разрешаю|разрешено|"
    r"делай|делайте|выполняй|выполняйте|выполни|выполнить|запускай|запускайте|"
    r"устанавливай|устанавливайте|установи|установить|продолжай|продолжайте|можно|добро|"
    r"верно|точно|давай|давай делай)\b",
    re.IGNORECASE,
)


def _is_affirmation(text: str) -> bool:
    t = re.sub(r"[\s,.!?;:]+", " ", (text or "").strip().lower()).strip()
    if not t:
        return False
    return bool(_AFFIRM_RE.match(t))'''

    pattern = r'_AFFIRM_RE\s*=\s*re\.compile\(.*?\n\)\s*\n\s*\ndef _is_affirmation\(text: str\) -> bool:\s*\n\s*return bool\(_AFFIRM_RE\.match\(text or ""\)\)'
    if re.search(pattern, s, flags=re.DOTALL):
        s = replace_once(s, pattern, affirmation, "Russian affirmation regex", re.DOTALL)
    elif "def _is_affirmation(text: str) -> bool:" not in s:
        # Fallback for an older checkout that has no affirmation helper yet.
        marker = "def _is_work_intent(user_text: str) -> bool:\n"
        if marker not in s:
            raise RuntimeError("repair anchor not found: agent affirmation insertion")
        pos = s.index(marker)
        s = s[:pos] + affirmation + "\n\n" + s[pos:]

    # News must go through the Russian re-voicing layer rather than raw tool output -> TTS.
    s = s.replace('    "news_brief",\n', '')
    s = s.replace(
        '    "get_time", "weather", "crypto_price", "stock_price", "fx_rate", "convert",\n'
        '    "define_word", "wiki_lookup", "news_brief",\n',
        '    "get_time", "weather", "crypto_price", "stock_price", "fx_rate", "convert",\n'
        '    "define_word", "wiki_lookup",\n',
    )
    write(p, s)


def patch_router() -> None:
    p = "src/jarvis/brain/intent_router.py"
    s = read(p)
    marker = "_ROUTES: list[tuple[re.Pattern[str], list[str]]] = [\n"
    if marker not in s:
        raise RuntimeError("repair anchor not found: intent route table")

    # Keep the routes deterministic and high-confidence. App/process target extraction remains in
    # the actual tools; the router only chooses which tool is allowed to run.
    routes = r'''    # -- Russian Windows/desktop commands --
    (re.compile(r"\b(закрой|закрыть|выключи|выключить|останови|остановить|заверши|завершить)\b", re.I), ["process_op"]),
    (re.compile(r"\b(открой|открыть|запусти|запустить|включи|включить)\b", re.I), ["open_app"]),
'''
    if '"process_op"]' not in s:
        s = s.replace(marker, marker + routes, 1)
    elif 'r"\\b(открой|открыть|запусти|запустить' not in s:
        s = s.replace(marker, marker + routes, 1)
    write(p, s)


def patch_llm() -> None:
    p = "src/jarvis/brain/llm.py"
    s = read(p)
    if '("openrouter:", settings.openrouter_base_url' not in s:
        candidates = [
            '            ("ollama:", settings.ollama_base_url, "ollama"),',
            '            ("ollama:", settings.ollama_base_url, "ollama"),  # Ollama ignores the key',
        ]
        for anchor in candidates:
            if anchor in s:
                s = s.replace(
                    anchor,
                    anchor + '\n            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),',
                    1,
                )
                break
        else:
            raise RuntimeError("repair anchor not found: OpenRouter resolver")
    write(p, s)


def patch_config() -> None:
    p = "src/jarvis/config.py"
    s = read(p)

    if "openrouter_api_key:" not in s:
        # Preserve the existing Settings schema. Insert next to the existing provider keys.
        anchors = [
            '    freellmapi_api_key: str | None = None\n',
            '    minimax_api_key: str | None = None\n',
        ]
        anchor = next((a for a in anchors if a in s), None)
        if anchor is None:
            raise RuntimeError("repair anchor not found: config provider key block")
        addition = anchor + (
            '    # OpenRouter: OpenAI-compatible gateway for the owner\'s model pool.\n'
            '    openrouter_api_key: str | None = None\n'
            '    openrouter_base_url: str = "https://openrouter.ai/api/v1"\n'
        )
        s = s.replace(anchor, addition, 1)

    if "llm_first_token_timeout_seconds" in s:
        s = re.sub(
            r'llm_first_token_timeout_seconds:\s*float\s*=\s*[^\n]+',
            'llm_first_token_timeout_seconds: float = 6.0',
            s,
            count=1,
        )
    write(p, s)


def patch_confirm_policy() -> None:
    p = "src/jarvis/brain/proactive.py"
    s = read(p)
    s = s.replace(
        '    "file_op", "process_op", "run_powershell", "browser",\n',
        '    "file_op", "run_powershell", "browser",\n',
    )
    s = s.replace(
        '        return (args or {}).get("action") in {"kill", "start"}\n',
        '        return False\n',
    )
    write(p, s)


def patch_pyproject() -> None:
    p = "pyproject.toml"
    s = read(p)
    if "office = [" not in s:
        marker = "[project.optional-dependencies]\n"
        if marker not in s:
            raise RuntimeError("repair anchor not found: optional dependencies")
        s = s.replace(
            marker,
            marker
            + 'office = [\n    "python-docx>=1.1",\n    "openpyxl>=3.1",\n]\n'
            + 'desktop = [\n    "pyautogui>=0.9.54",\n]\n',
            1,
        )
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
