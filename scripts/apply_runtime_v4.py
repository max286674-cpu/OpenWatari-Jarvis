from __future__ import annotations

from pathlib import Path
import re
import py_compile

ROOT = Path(__file__).resolve().parents[1]


def patch(path: Path, transform, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    new = transform(text)
    if new == text:
        print(f"SKIP {label}: already applied")
        return
    path.write_text(new, encoding="utf-8")
    print(f"UPDATED {label}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"anchor not found: {label}")
    return text.replace(old, new, 1)


config = ROOT / "src/jarvis/config.py"
brain = ROOT / "src/jarvis/edge/brain_bridge.py"
wake = ROOT / "src/jarvis/edge/wake_word.py"

# 1) Conversation should remain hot after the wake word. The previous 8-second window is
# exactly what the log showed: VAD saw speech, but the wake gate had already stopped forwarding
# frames to STT. Hot-mic keeps the post-wake conversation open until a long idle period.
def patch_config(text: str) -> str:
    text = re.sub(r'(^\s*wake_listen_window_s:\s*float\s*=\s*)8\.0', r'\g<1>30.0', text, count=1, flags=re.MULTILINE)
    text = re.sub(r'(^\s*hot_mic_after_wake:\s*bool\s*=\s*)False', r'\g<1>True', text, count=1, flags=re.MULTILINE)
    text = re.sub(r'(^\s*hot_mic_idle_minutes:\s*int\s*=\s*)30', r'\g<1>30', text, count=1, flags=re.MULTILINE)
    text = re.sub(r'(^\s*listening_pulse:\s*bool\s*=\s*)True', r'\g<1>False', text, count=1, flags=re.MULTILINE)
    text = re.sub(r'(^\s*reply_language:\s*str\s*=\s*)"English"', r'\g<1>"Russian"', text, count=1, flags=re.MULTILINE)
    return text
patch(config, patch_config, "src/jarvis/config.py")

# 2) Kill the acknowledgement spam. Agent-level progress currently produces lines such as
# "Одну секунду", "Занимаюсь", "Переключаюсь". The final answer is already streamed sentence-by-
# sentence, so these fillers only make the assistant feel broken and can race with STT.
def patch_brain(text: str) -> str:
    old = '''            def progress(note: str) -> None:\n                # Spoken filler so a longer (e.g. fleet) turn isn't dead air.\n                asyncio.create_task(self.push_frame(TTSSpeakFrame(note)))\n'''
    new = '''            def progress(note: str) -> None:\n                # Progress fillers are intentionally silent. They caused repeated "Одну секунду /\n                # Занимаюсь / Переключаюсь" speech and competed with STT. The real answer is\n                # streamed below as soon as the model produces it.\n                return\n'''
    text = replace_once(text, old, new, "brain progress callback")

    old = '''            logger.info(f"heard while busy: {text!r} — superseding current task")\n            self._turn_task.cancel()\n            # Never send framework control text in English. The assistant is configured to reply in Russian.\n            await self.push_frame(TTSSpeakFrame("Переключаюсь, сэр."))\n'''
    new = '''            logger.info(f"heard while busy: {text!r} — superseding current task")\n            self._turn_task.cancel()\n            # Do NOT speak a "switching" filler. The new turn starts immediately.\n'''
    text = replace_once(text, old, new, "busy supersede filler")

    # Bound the entire brain turn. Without a total deadline, a provider can keep an open stream\n    # forever after the first token timeout has already been passed. Cancellation then releases\n    # the pipeline instead of leaving Jarvis permanently deaf.
    old = '''            full: list[str] = []\n            async for sentence in self._agent.respond_stream(text, on_progress=progress):\n                if sentence:\n                    full.append(sentence)\n                    await self.push_frame(TTSSpeakFrame(sentence))\n            if full:\n                logger.info(f"reply: {' '.join(full)!r}")\n'''
    new = '''            full: list[str] = []\n\n            async def consume() -> None:\n                async for sentence in self._agent.respond_stream(text, on_progress=progress):\n                    if sentence:\n                        full.append(sentence)\n                        await self.push_frame(TTSSpeakFrame(sentence))\n\n            # Hard ceiling for one conversational turn. This is a recovery guard, not the normal\n            # latency target: healthy Qwen/DeepSeek turns should finish far sooner.\n            await asyncio.wait_for(consume(), timeout=25.0)\n            if full:\n                logger.info(f"reply: {' '.join(full)!r}")\n'''
    text = replace_once(text, old, new, "brain turn hard timeout")

    old = '''        except asyncio.CancelledError:\n            logger.info("brain turn cancelled")\n            raise\n        except Exception:  # noqa: BLE001\n            logger.exception("brain turn failed")\n            await self.push_frame(TTSSpeakFrame("Извините, сэр, при обработке команды произошла ошибка."))\n'''
    new = '''        except asyncio.CancelledError:\n            logger.info("brain turn cancelled")\n            raise\n        except asyncio.TimeoutError:\n            logger.error("brain turn timeout after 25s — releasing pipeline")\n            await self.push_frame(TTSSpeakFrame("Сэр, ответ занял слишком много времени. Готов продолжить."))\n        except Exception:  # noqa: BLE001\n            logger.exception("brain turn failed")\n            await self.push_frame(TTSSpeakFrame("Извините, сэр, при обработке команды произошла ошибка."))\n'''
    text = replace_once(text, old, new, "brain timeout handling")
    return text
patch(brain, patch_brain, "src/jarvis/edge/brain_bridge.py")

# 3) Never let a stuck TTS speaking flag permanently close the mic. The wake gate already has a
# safety reset; make it a little more forgiving for long generated replies.
def patch_wake(text: str) -> str:
    # Only adjust the default if the field exists; do not touch the Priler playback logic.
    text = re.sub(r'(^\s*self\._max_speak_s\s*=\s*)[0-9.]+', r'\g<1>20.0', text, count=1, flags=re.MULTILINE)
    return text
patch(wake, patch_wake, "src/jarvis/edge/wake_word.py")

# 4) Fail early on syntax errors before the user starts the voice stack.
for p in (config, brain, wake):
    py_compile.compile(str(p), doraise=True)

print("\nRuntime v4 applied.")
print("Post-wake hot mic: ON")
print("Progress filler speech: OFF")
print("Brain turn hard timeout: 25s")
print("Listening pulse: OFF")
print("Python compile check: OK")
print("Restart JARVIS before testing.")
