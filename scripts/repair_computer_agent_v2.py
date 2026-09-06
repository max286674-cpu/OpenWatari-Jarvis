from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "src/jarvis/brain/agent.py"
PROACTIVE = ROOT / "src/jarvis/brain/proactive.py"

# Patch by stable source markers; never regex-rewrite Python syntax.
s = AGENT.read_text(encoding="utf-8")

IMPORT_MARK = "from jarvis.brain import audit\n"
IMPORT = "from jarvis.brain.computer_control import direct_command\n"
if IMPORT not in s:
    if IMPORT_MARK not in s:
        raise SystemExit("agent.py: stable import marker not found")
    s = s.replace(IMPORT_MARK, IMPORT_MARK + IMPORT, 1)

# Blocking respond path: after catastrophic guard and before the LLM acknowledgement/history.
OLD = """        if _catastrophic(user_text):\n            return self._refuse_catastrophic(user_text)\n        self._immediate_ack(user_text, on_progress)\n"""
NEW = """        if _catastrophic(user_text):\n            return self._refuse_catastrophic(user_text)\n        # Deterministic computer fast-path: basic open/close/find commands are executed locally,\n        # not guessed by an LLM. This prevents a spoken \"done\" when Windows did nothing.\n        direct = await direct_command(user_text)\n        if direct is not None:\n            self._history.append({\"role\": \"user\", \"content\": user_text})\n            self._history.append({\"role\": \"assistant\", \"content\": direct})\n            self._trim()\n            self._spawn_review()\n            return direct\n        self._immediate_ack(user_text, on_progress)\n"""
if OLD not in s:
    raise SystemExit("agent.py: blocking respond marker not found")
s = s.replace(OLD, NEW, 1)

# Streaming path: same fast-path, before any model call.
OLD2 = """        if _catastrophic(user_text):\n            self._refuse_catastrophic(user_text)   # records user + a hard refusal\n            self._stream_done = True\n            yield _CATASTROPHIC_REFUSAL\n            return\n        self._immediate_ack(user_text, on_progress)\n"""
NEW2 = """        if _catastrophic(user_text):\n            self._refuse_catastrophic(user_text)   # records user + a hard refusal\n            self._stream_done = True\n            yield _CATASTROPHIC_REFUSAL\n            return\n        # Same deterministic computer fast-path for the live streaming voice pipeline.\n        direct = await direct_command(user_text)\n        if direct is not None:\n            self._history.append({\"role\": \"user\", \"content\": user_text})\n            self._history.append({\"role\": \"assistant\", \"content\": direct})\n            self._trim()\n            self._spawn_review()\n            self._stream_done = True\n            yield direct\n            return\n        self._immediate_ack(user_text, on_progress)\n"""
if OLD2 not in s:
    raise SystemExit("agent.py: streaming marker not found")
s = s.replace(OLD2, NEW2, 1)

ast.parse(s, filename=str(AGENT))
AGENT.write_text(s, encoding="utf-8")

p = PROACTIVE.read_text(encoding="utf-8")
OLD3 = '    if name == "process_op":\n        return (args or {}).get("action") in {"kill", "start"}\n'
NEW3 = '    if name == "process_op":\n        # Routine local computer control is frictionless. Destructive file deletion, external sends,\n        # PowerShell and other consequential actions remain gated; opening/closing apps must not ask\n        # the owner for a second confirmation every time.\n        return False\n'
if OLD3 not in p:
    raise SystemExit("proactive.py: process confirmation marker not found")
p = p.replace(OLD3, NEW3, 1)
ast.parse(p, filename=str(PROACTIVE))
PROACTIVE.write_text(p, encoding="utf-8")
print("computer agent v2 applied")
