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
    s = replace_once(
        s,
        r'_AFFIRM_RE\s*=\s*re\.compile\(.*?\n\)\n\n\ndef _is_affirmation\(text: str\) -> bool:\n    return bool\(_AFFIRM_RE\.match\(text or ""\)\)',
        '''_AFFIRM_RE = re.compile(
    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"
    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"
    r"correct|fine|absolutely|yes please|go|right|"
    r"да|ага|угу|конечно|подтверждаю|подтверждено|подтверждай|разрешаю|разрешено|"
    r"делай|делайте|выполняй|выполняйте|выполни|выполнить|запускай|запускайте|"
    r"устанавливай|устанавливайте|установи|установить|продолжай|продолжайте|можно|добро|"
    r"верно|точно|давай|давай делай)\\b",
    re.IGNORECASE,
)


def _is_affirmation(text: str) -> bool:
    t = re.sub(r"[\\s,.!?;:]+", " ", (text or "").strip().lower()).strip()
    if not t:
        return False
    return bool(_AFFIRM_RE.match(t))''',
        "Russian affirmation regex",
        re.DOTALL,
    )
    # Prerecorded Priler acknowledgement is the wake acknowledgement. Do not inject another generic
    # acknowledgement from the brain layer, which creates duplicate speech/filler.
    s = s.replace('    "news_brief",\n', '')
    s = s.replace('    "get_time", "weather", "crypto_price", "stock_price", "fx_rate", "convert",\n    "define_word", "wiki_lookup", "news_brief",\n',
                  '    "get_time", "weather", "crypto_price", "stock_price", "fx_rate", "convert",\n    "define_word", "wiki_lookup",\n')
    write(p, s)


def patch_router() -> None:
    p = "src/jarvis/brain/intent_router.py"
    s = read(p)
    marker = '    # -- writes / commands (outward ones stay confirm-gated downstream; forcing only picks the tool) --\n'
    if marker not in s:
        raise RuntimeError("repair anchor not found: intent route section")
    routes = '''    # -- Russian Windows/desktop commands --\n    # These are deterministic high-confidence intents: do not make the LLM guess whether the owner\n    # meant opening or closing an application. The tool layer still validates the actual target.\n    (re.compile(r"\\b(открой|открыть|запусти|запустить|включи|включить)\\b[^.?!]{0,60}"\n                r"\\b(telegram|телеграм|chrome|хром|google chrome|firefox|discord|дискорд|spotify|спотифай|steam|стим|notepad|блокнот|calculator|калькулятор|edge|word|excel|vscode|visual studio)\\b", re.I), ["open_app"]),\n    (re.compile(r"\\b(закрой|закрыть|выключи|выключить|останови|остановить|заверши|завершить)\\b[^.?!]{0,60}"\n                r"\\b(telegram|телеграм|chrome|хром|google chrome|firefox|discord|дискорд|spotify|спотифай|steam|стим|notepad|блокнот|calculator|калькулятор|edge|word|excel|vscode|visual studio)\\b", re.I), ["process_op"]),\n'''
    s = s.replace(marker, marker + routes, 1)
    write(p, s)


def patch_llm() -> None:
    p = "src/jarvis/brain/llm.py"
    s = read(p)
    old = '("minimax:", settings.minimax_base_url, settings.minimax_api_key or "missing-minimax-key"),\n            ("ollama:", settings.ollama_base_url, "ollama"),'
    new = '("minimax:", settings.minimax_base_url, settings.minimax_api_key or "missing-minimax-key"),\n            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),\n            ("ollama:", settings.ollama_base_url, "ollama"),'
    if old in s and new not in s:
        s = s.replace(old, new, 1)
    elif new not in s:
        raise RuntimeError("repair anchor not found: LLM provider resolver")
    write(p, s)


def patch_config() -> None:
    p = "src/jarvis/config.py"
    s = read(p)
    if "openrouter_api_key:" not in s:
        anchor = '    minimax_base_url: str = "https://api.minimax.io/v1"\n'
        if anchor not in s:
            raise RuntimeError("repair anchor not found: config provider block")
        addition = anchor + '    # OpenRouter: OpenAI-compatible gateway for the owner's model pool.\n    openrouter_api_key: str | None = None\n    openrouter_base_url: str = "https://openrouter.ai/api/v1"\n'
        s = s.replace(anchor, addition, 1)
    if "llm_first_token_timeout_seconds" in s:
        s = re.sub(r'llm_first_token_timeout_seconds: float = [0-9.]+',
                   'llm_first_token_timeout_seconds: float = 6.0', s, count=1)
    write(p, s)


def patch_confirm_policy() -> None:
    p = "src/jarvis/brain/proactive.py"
    s = read(p)
    # Normal desktop/browser actions are owner-directed and reversible; only genuinely consequential
    # actions should interrupt the flow with a confirmation prompt.
    s = s.replace('    "file_op", "process_op", "run_powershell", "browser",\n',
                  '    "file_op", "run_powershell",\n')
    write(p, s)


def patch_pyproject() -> None:
    p = "pyproject.toml"
    s = read(p)
    if "office = [" not in s:
        marker = '[project.optional-dependencies]\n'
        if marker not in s:
            raise RuntimeError("repair anchor not found: optional dependencies")
        s = s.replace(marker, marker + 'office = [\n    "python-docx>=1.1",\n    "openpyxl>=3.1",\n]\ndesktop = [\n    "pyautogui>=0.9.54",\n]\n', 1)
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
