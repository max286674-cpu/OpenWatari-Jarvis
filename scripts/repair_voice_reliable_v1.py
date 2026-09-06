"""Make the desktop voice edge reliably hear commands.

The previous configuration could start successfully while the wake gate rejected Russian
"Джарвис": openWakeWord's built-in model is the English `hey_jarvis`, while arbitrary Russian
phrases are treated as pending custom models. That leaves the pipeline running but deaf to the
expected Russian wake phrase.

This repair deliberately switches the edge to hands-free VAD/STT mode until a real Russian wake
model is installed. The mic remains local; HalfDuplexGate prevents the assistant from hearing its
own playback. No API secrets are touched.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "src" / "jarvis" / "config.py"
ENV = ROOT / ".env"


def replace_default(text: str, field: str, new_line: str) -> str:
    import re
    pat = rf"^\s*{re.escape(field)}\s*:[^\n]*$"
    out, n = re.subn(pat, new_line, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise RuntimeError(f"Could not patch config field: {field}")
    return out


def set_env(text: str, key: str, value: str) -> str:
    import re
    line = f"{key}={value}"
    pat = rf"^\s*{re.escape(key)}\s*=.*$"
    out, n = re.subn(pat, line, text, count=1, flags=re.MULTILINE)
    if n:
        return out
    if out and not out.endswith("\n"):
        out += "\n"
    return out + line + "\n"


def main() -> None:
    s = CONFIG.read_text(encoding="utf-8")
    s = replace_default(s, "wake_word_enabled", "    wake_word_enabled: bool = False")
    s = replace_default(s, "vad_confidence", "    vad_confidence: float = 0.50")
    s = replace_default(s, "vad_min_volume", "    vad_min_volume: float = 0.05")
    ast.parse(s, filename=str(CONFIG))
    CONFIG.write_text(s, encoding="utf-8")

    if ENV.exists():
        e = ENV.read_text(encoding="utf-8")
        e = set_env(e, "JARVIS_WAKE_WORD_ENABLED", "false")
        e = set_env(e, "JARVIS_VAD_CONFIDENCE", "0.50")
        e = set_env(e, "JARVIS_VAD_MIN_VOLUME", "0.05")
        ENV.write_text(e, encoding="utf-8")

    print("Voice repair applied: hands-free VAD/STT mode, Russian-friendly VAD thresholds.")
    print("No secrets changed.")


if __name__ == "__main__":
    main()
