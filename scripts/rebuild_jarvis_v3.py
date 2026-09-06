"""One-shot local rebuild for the Windows voice runtime.

Reuses mature project components and the official Pipecat Whisper implementation instead of keeping
custom speech plumbing on the critical voice path. Also repairs confirmation friction and local app
launch/close policy.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "jarvis"
KNOWN_GOOD_PROACTIVE = "273770dc4558258aae818be9f227ccde83e5ffe3"


def run(*args: str) -> str:
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def restore_proactive() -> None:
    run("git", "checkout", KNOWN_GOOD_PROACTIVE, "--", "src/jarvis/brain/proactive.py")
    p = SRC / "brain" / "proactive.py"
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        '    "send_telegram", "send_email", "send_push",\n    "file_op", "process_op", "run_powershell", "browser",\n    "run_protocol", "ha_call",\n    "create_event",',
        '    "send_telegram", "send_email", "send_push",\n    "file_op", "run_powershell",\n    "run_protocol", "ha_call",',
    )
    text = text.replace(
        '    if name == "process_op":\n        return (args or {}).get("action") in {"kill", "start"}\n',
        '',
    )
    text = text.replace(
        '_PRONOUN_ONLY = {"it", "that", "this", "them", "those", "these", "him", "her", "they"}',
        '_PRONOUN_ONLY = {"it", "that", "this", "them", "those", "these", "him", "her", "they", "это", "то", "его", "её", "ее", "их"}',
    )
    p.write_text(text, encoding="utf-8")


def patch_agent() -> None:
    p = SRC / "brain" / "agent.py"
    text = p.read_text(encoding="utf-8")
    new = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(да|ага|угу|ок|окей|хорошо|конечно|подтверждаю|подтверждено|разрешаю|"\n    r"делай|выполняй|продолжай|вперёд|вперед|давай|можно|согласен|согласна|"\n    r"yes|yeah|yep|sure|ok|okay|go ahead|do it|please do|confirm|confirmed|proceed)\\s*[.!?]*$",\n    re.IGNORECASE,\n)'''
    text, n = re.subn(r'_AFFIRM_RE = re\.compile\(.*?\n\)\n\n\ndef _is_affirmation', new + '\n\n\ndef _is_affirmation', text, count=1, flags=re.S)
    if n != 1:
        raise RuntimeError("Could not locate _AFFIRM_RE in agent.py")
    p.write_text(text, encoding="utf-8")


def patch_stt() -> None:
    """Replace the custom Whisper subclass with the official Pipecat service.

    Current Pipecat's WhisperSTTService already consumes raw 16-bit PCM, uses Faster-Whisper,
    emits TranscriptionFrame, and supports Russian. The old custom subclass duplicated that plumbing
    and made failures silent. The official implementation is the safer critical-path choice.
    """
    p = SRC / "edge" / "stt.py"
    text = p.read_text(encoding="utf-8")
    start = text.index("def _auto_whisper(model: str):")
    end = text.index("\n\ndef _build_whisper():", start)
    replacement = '''def _auto_whisper(model: str):\n    """Use Pipecat's maintained Faster-Whisper service for Russian speech."""\n    from pipecat.services.whisper.stt import WhisperSTTService\n    from pipecat.transcriptions.language import Language\n\n    hot = ""\n    try:\n        from jarvis.edge.proper_nouns import hotwords_str\n        hot = hotwords_str() or ""\n    except Exception:\n        pass\n    logger.info(f"STT: official Pipecat Whisper ({model}, Russian, CPU int8)")\n    try:\n        stt = WhisperSTTService(\n            model=model,\n            language=Language.RU,\n            device="cpu",\n            compute_type="int8",\n            no_speech_prob=0.30,\n            settings=WhisperSTTService.Settings(hotwords=hot or None),\n        )\n    except TypeError:\n        # Compatibility with older Pipecat versions that don't accept the Settings hotwords field.\n        stt = WhisperSTTService(\n            model=model, language=Language.RU, device="cpu", compute_type="int8", no_speech_prob=0.30\n        )\n    logger.info("STT: official Whisper service ready")\n    return stt\n'''
    text = text[:start] + replacement + text[end:]
    text = text.replace(
        'Either way the brain always **replies in English** (see ``personality/jarvis.md``); STT only\ndecides which spoken languages Jarvis can *understand*.',
        'The voice brain replies in Russian by default; STT is configured for Russian on the primary path.',
    )
    p.write_text(text, encoding="utf-8")


def validate() -> None:
    files = [
        SRC / "brain" / "agent.py",
        SRC / "brain" / "proactive.py",
        SRC / "brain" / "computer_direct.py",
        SRC / "brain" / "tools" / "computer_use.py",
        SRC / "edge" / "brain_bridge.py",
        SRC / "edge" / "stt.py",
        SRC / "config.py",
    ]
    for p in files:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    from jarvis.brain.agent import _is_affirmation
    for word in ("да", "ага", "подтверждаю", "разрешаю", "делай", "выполняй"):
        assert _is_affirmation(word), word
    from jarvis.brain.proactive import confirm_required
    assert confirm_required("process_op", {"action": "kill"}) is False
    assert confirm_required("process_op", {"action": "start"}) is False
    assert confirm_required("browser", {}) is False
    assert confirm_required("create_event", {}) is False
    assert confirm_required("file_op", {"action": "delete_file"}) is True
    assert confirm_required("file_op", {"action": "create_file"}) is False
    print("AST + Russian confirmation + friction policy validation: OK")


def main() -> None:
    restore_proactive()
    patch_agent()
    patch_stt()
    validate()
    print("JARVIS rebuild v3 applied.")
    print("Run: uv run pytest -q")
    print("Then: uv run python -m jarvis.edge.assistant")


if __name__ == "__main__":
    main()
