"""Final one-command rebuild entry point.

Run this after `git pull` from the repository root. It applies the local v2 runtime repair and then
forces news/web results through the Russian summarisation pass instead of speaking raw English news.
"""
from __future__ import annotations

import ast
from pathlib import Path

from rebuild_local_v2 import main as rebuild_v2

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "src" / "jarvis" / "brain" / "agent.py"


def main() -> None:
    rebuild_v2()
    text = AGENT.read_text(encoding="utf-8")
    old = '"get_time", "weather", "crypto_price", "stock_price", "fx_rate", "convert",\n    "define_word", "wiki_lookup", "news_brief",'
    new = '"get_time", "weather", "crypto_price", "stock_price", "fx_rate", "convert",\n    "define_word", "wiki_lookup",'
    if old in text:
        text = text.replace(old, new, 1)
    AGENT.write_text(text, encoding="utf-8")
    ast.parse(text, filename=str(AGENT))
    print("Final rebuild: news is no longer spoken raw; it must be re-voiced in Russian.")
    print("Final rebuild: AST validation OK.")
    print("Now run: uv run pytest -q")


if __name__ == "__main__":
    main()
