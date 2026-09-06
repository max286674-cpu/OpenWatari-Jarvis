from __future__ import annotations


def test_priler_voice_defaults_to_current_remaster(monkeypatch):
    monkeypatch.delenv("JARVIS_PRILER_VOICE", raising=False)
    monkeypatch.delenv("JARVIS_PRILER_LANGUAGE", raising=False)
    from jarvis.edge import priler_reactions

    assert priler_reactions.voice() == "jarvis-remaster"
    assert priler_reactions.language() == "ru"


def test_priler_voice_rejects_unknown_pack(monkeypatch):
    monkeypatch.setenv("JARVIS_PRILER_VOICE", "not-a-voice")
    from jarvis.edge import priler_reactions

    assert priler_reactions.voice() == "jarvis-remaster"


def test_priler_reaction_path_blocks_path_traversal(monkeypatch):
    from jarvis.edge import priler_reactions

    monkeypatch.setenv("JARVIS_PRILER_VOICE", "jarvis-remaster")
    monkeypatch.setenv("JARVIS_PRILER_LANGUAGE", "ru")
    try:
        priler_reactions._path("../reply1.mp3")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal must be rejected")


def test_priler_reaction_is_optional(monkeypatch):
    from jarvis.edge import priler_reactions

    monkeypatch.setenv("JARVIS_PRILER_REACTIONS", "false")
    assert priler_reactions.enabled() is False
    monkeypatch.setenv("JARVIS_PRILER_REACTIONS", "true")
    assert priler_reactions.enabled() is True
