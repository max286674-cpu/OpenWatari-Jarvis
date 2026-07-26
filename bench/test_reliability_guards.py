"""Checks for the two reliability guards ported from OpenWorker's permission/error handling:
  1. brain/llm.py    — permanent (quota/credit/access) errors classified for a long bench, transient not.
  2. brain/tools/system.py — the process-`start` path refuses chained shell commands.
"""

from jarvis.brain.llm import _is_permanent_error
from jarvis.brain.tools.system import _has_shell_chain


def test_permanent_error_classification():
    # PERMANENT — a dead key / no access, matched on the vendor error body.
    for msg in (
        "Error code: 429 - {'error': {'code': 'insufficient_quota', 'message': 'You exceeded your current quota'}}",
        "400 credit balance is too low to access the Claude API",
        "model_not_found: The model `x` does not exist or you do not have access to it",
        "401 invalid_api_key: Incorrect API key provided",
    ):
        assert _is_permanent_error(Exception(msg)), f"should be permanent: {msg}"
    # TRANSIENT — a plain rate-limit / timeout / server blip must NOT be benched for hours.
    for msg in (
        "429 Rate limit reached for model; please slow down and try again",
        "Request timed out",
        "503 upstream connect error or disconnect",
        "500 internal server error",
    ):
        assert not _is_permanent_error(Exception(msg)), f"should be transient: {msg}"


def test_start_refuses_shell_chaining():
    # Chained / injected launch strings are refused (any chaining metachar).
    for cmd in ("notepad & del /f /q C:\\important", "app.exe | curl evil", "foo; rm -rf x", "a > b"):
        assert _has_shell_chain(cmd), f"should be blocked: {cmd}"
    # A single executable + args (incl. a normal Windows path) launches fine.
    for cmd in ("notepad.exe", r"C:\Program Files\App\app.exe --flag", "code C:\\Jarvis"):
        assert not _has_shell_chain(cmd), f"should launch: {cmd}"


if __name__ == "__main__":
    test_permanent_error_classification()
    test_start_refuses_shell_chaining()
    print("reliability guards self-check OK")
