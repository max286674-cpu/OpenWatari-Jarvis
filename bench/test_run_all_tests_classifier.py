"""Regression checks for bench/run_all_tests.py result classification.

Run:
    uv run python bench/test_run_all_tests_classifier.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.run_all_tests import classify_result  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def main() -> int:
    print("[1] regular pass/fail")
    check(
        "exit 0 + required output -> PASS",
        classify_result("offline", 0, "all checks passed", ["checks passed"]) == "PASS",
    )
    check(
        "missing required output -> FAIL",
        classify_result("offline", 0, "partial output", ["checks passed"]) == "FAIL",
    )

    print("\n[2] network skip only for unavailable dependency")
    check(
        "proxy connection refused -> SKIP",
        classify_result(
            "network",
            1,
            "httpx.ConnectError: [WinError 10061] No connection could be made",
            ["fleet sentinel not leaked"],
        )
        == "SKIP",
    )
    check(
        "name resolution failure -> SKIP",
        classify_result(
            "network",
            1,
            "getaddrinfo failed / NameResolutionError",
            ["fleet sentinel not leaked"],
        )
        == "SKIP",
    )

    print("\n[3] runnable model/tool failures stay red")
    check(
        "tool-call validation failure -> FAIL",
        classify_result(
            "network",
            1,
            "APIConnectionError earlier\nError code: 400 - {'error': {'message': "
            "'tool call validation failed', 'type': 'invalid_request_error'}}",
            ["fleet sentinel not leaked"],
        )
        == "FAIL",
    )
    check(
        "provider rate limit -> FAIL",
        classify_result(
            "network",
            1,
            "Error code: 429 - {'error': {'code': 'rate_limit_exceeded'}}",
            ["fleet sentinel not leaked"],
        )
        == "FAIL",
    )

    print("\n[4] whole failover chain exhausted to a connectivity failure -> SKIP (no LLM in this env)")
    check(
        "all models failed + Connection error -> SKIP even with a stray provider 400",
        classify_result(
            "network",
            1,
            "LLM marked 'groq:llama' unhealthy (BadRequestError)\n"
            "RuntimeError: all LLM models failed; last error: Connection error.",
            ["fleet sentinel not leaked"],
        )
        == "SKIP",
    )
    check(
        "but a tool-validation 400 (no chain-exhaustion marker) stays FAIL",
        classify_result(
            "network",
            1,
            "Connection error earlier from one provider\n"
            "Error code: 400 - {'error': {'message': 'tool call validation failed'}}",
            ["fleet sentinel not leaked"],
        )
        == "FAIL",
    )

    print("\n[5] a [network] test that TIMES OUT is a slow/absent LLM dependency -> SKIP")
    check(
        "network + timeout (code 124) -> SKIP",
        classify_result("network", 124, "TIMEOUT after 180s", ["checks passed"]) == "SKIP",
    )
    check(
        "but an OFFLINE test that times out is a real hang -> FAIL",
        classify_result("offline", 124, "TIMEOUT after 180s", ["checks passed"]) == "FAIL",
    )

    print(f"\n=== {PASS}/{PASS + FAIL} checks passed ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
