"""C6 — recovery-protocol drills: every protocol is provably invocable + correctly gated, and a drill
NEVER launches the real (stop/restart/reboot) script. Patches subprocess.Popen to assert no launch.
"""
import asyncio

import jarvis.brain.protocols as proto
from jarvis.brain.protocols import ProtocolResult, protocol_names, run_protocol
from jarvis.config import settings

_ok = 0
_fail = 0


def check(cond, label):
    global _ok, _fail
    if cond:
        _ok += 1
    else:
        _fail += 1
        print(f"  FAIL: {label}")


# Guarantee protocols are enabled for the drill regardless of ambient config.
settings.protocols_enabled = True

# Record every Popen so we can prove drills DON'T launch and live runs DO reach the launch path.
# (Return a dummy so the engine's own try/except sees a normal launch, not an error.)
_launched = []


class _DummyProc:
    pid = 999


proto.subprocess.Popen = lambda *a, **k: (_launched.append(a), _DummyProc())[1]


def _password_for(name):
    return getattr(settings, f"protocol_{name}_password")


async def main():
    names = protocol_names()
    check(len(names) >= 4, f"there are recovery protocols to drill ({names})")

    # --- 1) every protocol drills OK with the right password, and launches NOTHING ----------
    for name in names:
        r = run_protocol(name, _password_for(name), drill=True)
        check(r.ok and "Drill OK" in r.message, f"drill '{name}' passes with the correct password")
    check(_launched == [], "no protocol drill ever launched a real script (Popen untouched)")

    # --- 2) the password gate still holds under drill (wrong password refused, nothing runs) --
    r_bad = run_protocol(names[0], "definitely-wrong-password", drill=True)
    check((not r_bad.ok) and "incorrect" in r_bad.message, "a wrong password is refused even in drill mode")

    # --- 3) an unknown protocol is reported, not launched -----------------------------------
    r_unk = run_protocol("no-such-protocol", "x", drill=True)
    check((not r_unk.ok) and "no protocol" in r_unk.message, "unknown protocol reported cleanly")

    # --- 4) the tool surface exposes drill + still gates on the password --------------------
    from jarvis.brain.tools.protocols import run_protocol as tool_run, SCHEMAS
    said = await tool_run({"name": names[0], "drill": True})  # no password
    check("password" in said.lower(), "tool asks for the password before drilling")
    props = SCHEMAS[0]["function"]["parameters"]["properties"]
    check("drill" in props, "run_protocol schema advertises the drill parameter")

    # --- 5) a real (non-drill) run with a good password DOES reach the launch path -----------
    _launched.clear()
    r_live = run_protocol(names[0], _password_for(names[0]), drill=False)
    check(r_live.ok and len(_launched) == 1,
          "a live (non-drill) run launches the script (drill is what suppresses it)")

    print(f"=== {_ok}/{_ok + _fail} checks passed ===")
    import sys
    sys.exit(1 if _fail else 0)


asyncio.run(main())
