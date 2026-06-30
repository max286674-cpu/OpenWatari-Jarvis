"""Dump the live tool registry as markdown — single source of truth for the docs site.

Run: .venv/Scripts/python.exe bench/dump_tools.py > website/app/_tools.generated.md
Keeps the docs' tool list from drifting from the code (the registry IS the spec).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jarvis.brain.tools import CORE_MODULES, _LAZY_GROUPS, tool_schemas  # noqa: E402


def main() -> None:
    schemas = tool_schemas()
    core = {m.__name__.split(".")[-1] for m in CORE_MODULES}
    groups = {m.__name__.split(".")[-1]: g for g, mods in _LAZY_GROUPS.items() for m in mods}
    print(f"# Watari tools ({len(schemas)} total)\n")
    print("Generated from the live registry by `bench/dump_tools.py` — do not edit by hand.\n")
    for s in sorted(schemas, key=lambda x: x["function"]["name"]):
        fn = s["function"]
        name, desc = fn["name"], fn.get("description", "").split(".")[0]
        print(f"- **`{name}`** — {desc}.")
    print(f"\n_Core (advertised every turn):_ {', '.join(sorted(core))}.")
    print(f"\n_Lazy groups:_ " + "; ".join(f"**{g}** = {', '.join(sorted(m for m, gg in groups.items() if gg == g))}"
                                          for g in sorted(_LAZY_GROUPS)) + ".")


if __name__ == "__main__":
    main()
