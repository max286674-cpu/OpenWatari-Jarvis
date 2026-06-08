"""Find the STT-mute filter API (stops self-hearing while the bot speaks)."""

import inspect

try:
    from pipecat.processors.filters import stt_mute_filter as m
    print("module:", m.__file__)
    print("exports:", [n for n in dir(m) if not n.startswith("_")])
    if hasattr(m, "STTMuteStrategy"):
        print("strategies:", [s.name for s in m.STTMuteStrategy])
    if hasattr(m, "STTMuteConfig"):
        print("STTMuteConfig sig:", str(inspect.signature(m.STTMuteConfig.__init__)))
    if hasattr(m, "STTMuteFilter"):
        print("STTMuteFilter sig:", str(inspect.signature(m.STTMuteFilter.__init__)))
except Exception as e:
    print("import failed:", type(e).__name__, e)
