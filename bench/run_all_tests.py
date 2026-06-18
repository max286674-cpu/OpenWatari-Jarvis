"""One command to verify Jarvis works end-to-end.

    uv run python bench/run_all_tests.py

Runs every check in order and prints a single PASS/FAIL summary. Tests are tagged:

  [offline]  — deterministic, no network (config, VAD, barge-in, wake-word perf)
  [network]  — needs the freellmapi proxy reachable (Jarvis's brain LLM); reported as
               SKIP (not FAIL) if the proxy is unreachable, so an offline run still passes
  [gated]    — the OpenClaw fleet connect, intentionally blocked until a sanctioned path
               is enabled; reported as SKIP

Exit code is non-zero only if a runnable test actually fails.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

# (label, script, tag, success_substrings) — a test passes if exit==0 AND every
# required substring appears in its output (empty list = exit code only).
TESTS = [
    ("config loads + secrets present", "check_config.py", "offline", ["elevenlabs_api_key  : set"]),
    ("Phase 1: VAD + barge-in", "test_phase1_vad_bargein.py", "offline", ["checks passed ==="]),
    ("Phase 3: knowledge & channel tools + ispir-only", "test_phase3_tools.py", "offline",
     ["checks passed ==="]),
    ("Phase 4 + system/browser/protocols", "test_phase4_system_protocols.py", "offline",
     ["checks passed ==="]),
    ("wake word: faster than realtime", "test_wakeword.py", "offline", ["wake word ready"]),
    ("Phase 5: speaker biometrics + TTFW/VAQI", "test_phase5_identity_bench.py", "offline",
     ["checks passed ==="]),
    ("Phase 6: multi-device (edge-lite + device routing)", "test_phase6_multidevice.py", "offline",
     ["checks passed ==="]),
    ("Phase 6: brain WS server (phone/glasses -> shared brain)", "test_phase6_brain_server.py",
     "offline", ["checks passed ==="]),
    ("Phase 9: persistent memory (learned facts + journal)", "test_phase9_memory.py", "offline",
     ["checks passed ==="]),
    ("Phase 9b: L4 hot-cache (in-process + graceful Redis)", "test_phase9b_cache.py", "offline",
     ["checks passed ==="]),
    ("Phase 9c: L5 semantic recall (graceful embedder)", "test_phase9c_semantic.py", "offline",
     ["checks passed ==="]),
    ("Phase 10: proactive engine (budget/quiet-hours/clarify-confirm)", "test_phase10_proactive.py",
     "offline", ["checks passed ==="]),
    ("Phase 11: Gmail/Calendar/Home-Assistant (graceful degradation)",
     "test_phase11_integrations.py", "offline", ["checks passed ==="]),
    ("Phase 11: Notion (read/write/comment, graceful)", "test_phase11_notion.py", "offline",
     ["checks passed ==="]),
    ("Phase 12: utilities belt (weather/crypto/fx/convert/…)", "test_phase12_utility.py",
     "offline", ["checks passed ==="]),
    ("Phase X: audit log + self-health + modes/routines", "test_phasex_audit_health_modes.py",
     "offline", ["checks passed ==="]),
    ("Phase 13: coding tools + git safety + skills", "test_phase13_coding.py",
     "offline", ["checks passed ==="]),
    ("Fine-tuning: lean prompt + per-turn tool surface + fast primary", "test_finetune.py",
     "offline", ["checks passed ==="]),
    ("P0 #1: brain owns the reminder scheduler (fires 24/7)", "test_scheduler_brain.py",
     "offline", ["checks passed ==="]),
    ("P0 #3: edge auto-reconnects to the brain after a restart", "test_edge_reconnect.py",
     "offline", ["checks passed ==="]),
    ("Streaming voice path (respond_stream yields sentences live)", "test_streaming.py",
     "offline", ["checks passed ==="]),
    ("Self-improvement loop (background_review learns facts into L1)", "test_self_improve.py",
     "offline", ["checks passed ==="]),
    ("Companion safety: confirm-gate + durable proactive + smart reset + vault write",
     "test_companion_safety.py", "offline", ["checks passed ==="]),
    ("LLM routing: provider prefix + fast tier + first-token failover + warm-up",
     "test_llm_routing.py", "offline", ["checks passed ==="]),
    ("Background task queue: fire long work, live status, voice completion",
     "test_background_tasks.py", "offline", ["checks passed ==="]),
    ("Local voice: build_tts honours provider (ElevenLabs/Piper/Kokoro)",
     "test_local_voice.py", "offline", ["checks passed ==="]),
    ("Identity layer: one persona template personalises from config (framework)",
     "test_identity.py", "offline", ["checks passed ==="]),
    ("Setup wizard: identity render + profile/persona seeding (no clobber)",
     "test_setup_wizard.py", "offline", ["checks passed ==="]),
    ("P1 #4: resilience under fault injection (LLM/cache/scheduler/tool)", "test_resilience.py",
     "offline", ["checks passed ==="]),
    ("P1 #6: memory hygiene (dedup + cap + journal rotation)", "test_memory_hygiene.py",
     "offline", ["checks passed ==="]),
    ("P1 #7: security hardening (system-delete guard + audit value scrub)",
     "test_security_hardening.py", "offline", ["checks passed ==="]),
    ("Phase 2: brain agent (LLM + tools + memory)", "test_brain_agent.py", "network",
     ["fleet sentinel not leaked"]),
]

# Markers that mean "the proxy/brain wasn't reachable" -> SKIP a [network] test, not FAIL.
NETWORK_DOWN = ("Connection", "ConnectError", "Timeout", "Max retries", "getaddrinfo",
                "Failed to establish", "APIConnectionError", "11001", "actively refused")


def run(script: str, timeout: int) -> tuple[int, str]:
    t0 = time.perf_counter()
    try:
        p = subprocess.run(
            [PY, str(ROOT / "bench" / script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        dt = (time.perf_counter() - t0) * 1000
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "") + f"\n[{dt:.0f}ms]"
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"


def main() -> int:
    print("=" * 60)
    print(" JARVIS — full verification")
    print("=" * 60)
    results: list[tuple[str, str]] = []  # (status, label)

    for label, script, tag, needles in TESTS:
        print(f"\n--- [{tag}] {label}\n    ({script})")
        code, out = run(script, timeout=180)
        tail = "\n".join(line for line in out.splitlines() if line.strip())[-1500:]
        print("    " + tail.replace("\n", "\n    "))

        if tag == "network" and (code != 0 and any(n in out for n in NETWORK_DOWN)):
            status = "SKIP"
            print("    -> SKIP (freellmapi proxy unreachable — start the VPS tunnel to run this)")
        elif code == 0 and all(n in out for n in needles):
            status = "PASS"
        else:
            status = "FAIL"
        results.append((status, label))

    # The gated fleet test is informational only.
    results.append(("SKIP", "OpenClaw fleet connect (gated — awaiting sanctioned path)"))

    print("\n" + "=" * 60)
    print(" SUMMARY")
    print("=" * 60)
    icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "·"}
    for status, label in results:
        print(f"  {icon[status]} {status:4} {label}")

    failed = [lbl for s, lbl in results if s == "FAIL"]
    npass = sum(1 for s, _ in results if s == "PASS")
    nskip = sum(1 for s, _ in results if s == "SKIP")
    print(f"\n  {npass} passed, {len(failed)} failed, {nskip} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
