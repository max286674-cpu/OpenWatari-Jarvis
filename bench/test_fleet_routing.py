"""Fleet routing memory — repeated delegated domains surface as a system-prompt bias line."""

from __future__ import annotations

from jarvis.brain import fleet, prefs


def test_routing_memory(monkeypatch) -> None:
    store: dict = {}
    monkeypatch.setattr(prefs, "get", lambda k, default=None: store.get(k, default))
    monkeypatch.setattr(prefs, "set", lambda k, v: store.__setitem__(k, v))

    assert fleet.routing_hint() == ""  # nothing learned yet
    fleet._note_success("research the ETF market and write a report")
    assert fleet.routing_hint() == ""  # one success isn't a pattern
    fleet._note_success("compare portfolio ETF options")
    hint = fleet.routing_hint()
    assert "finance/markets" in hint and "delegate" in hint

    # A domain never delegated stays out of the hint.
    assert "real estate" not in hint
