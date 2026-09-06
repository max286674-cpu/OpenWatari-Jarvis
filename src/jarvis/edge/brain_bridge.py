"""JarvisBrain — voice edge bridge between STT and the real agent."""
from __future__ import annotations

import asyncio
import json
import re

from loguru import logger
from pipecat.frames.frames import Frame, InterruptionFrame, TranscriptionFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from jarvis.brain.agent import JarvisAgent
from jarvis.brain.computer_direct import direct_computer_command

_CANCEL_RE = re.compile(
    r"\b(stop|cancel|abort|abandon|never mind|nevermind|forget it|leave it|drop it|"
    r"shut up|pause|give up|отмена|отмени|стоп|хватит)\b", re.IGNORECASE,
)
_AFFIRM_RE = re.compile(
    r"^\s*(да|ага|угу|ок|окей|хорошо|конечно|подтверждаю|подтверждено|разрешаю|"
    r"делай|выполняй|выполняй это|продолжай|вперёд|вперед|давай|можно|согласен|согласна|"
    r"yes|yeah|yep|sure|okay|ok|go ahead|do it|please do|confirm|confirmed|proceed)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_NEGATE_RE = re.compile(
    r"^\s*(нет|не надо|отмена|отмени|стоп|хватит|не делай|не выполняй|no|cancel|stop)\s*[.!?]*\s*$",
    re.IGNORECASE,
)


class JarvisBrain(FrameProcessor):
    def __init__(self, agent: JarvisAgent | None = None) -> None:
        super().__init__()
        self._agent = agent or JarvisAgent()
        self._busy = False
        self._turn_task: asyncio.Task | None = None

    async def warmup(self) -> None:
        await self._agent.warmup()
        self._start_scheduler()

    def _start_scheduler(self) -> None:
        try:
            from jarvis.brain.scheduler import SCHEDULER
            loop = asyncio.get_running_loop()
            def speak(message: str) -> None:
                loop.create_task(self.push_frame(TTSSpeakFrame(f"Напоминание, сэр: {message}")))
            SCHEDULER.start(on_speak=speak)
        except Exception as e:
            logger.warning(f"scheduler not started: {e}")

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            if self._turn_task and not self._turn_task.done():
                logger.info("brain: interrupted — cancelling current turn")
                self._turn_task.cancel()
            self._busy = False
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TranscriptionFrame):
            text = (getattr(frame, "text", "") or "").strip()
            if text:
                await self._start_or_supersede_turn(text)
            return
        await self.push_frame(frame, direction)

    async def _handle_pending_confirmation(self, text: str) -> bool:
        """Consume one pending confirmation before the normal agent loop.

        The old design stored the pending call but then sent Russian "да" back through the LLM. The
        next turn consequently either forgot the pending call or asked again. Here the exact stored
        tool call is executed once, deterministically, and the pending state is cleared immediately.
        """
        pending = getattr(self._agent, "_pending_confirm", None)
        if not pending:
            return False
        if _NEGATE_RE.match(text):
            self._agent._pending_confirm = None
            self._agent._confirm_granted = False
            await self.push_frame(TTSSpeakFrame("Хорошо, отменяю, сэр."))
            logger.info("pending confirmation cancelled by owner")
            return True
        if not _AFFIRM_RE.match(text):
            # A new command supersedes the stale confirmation instead of causing a repeated question.
            self._agent._pending_confirm = None
            self._agent._confirm_granted = False
            return False

        name = str(pending.get("name") or "")
        args = dict(pending.get("args") or {})
        self._agent._pending_confirm = None
        self._agent._confirm_granted = True
        try:
            calls = [{"id": "confirmed-1", "name": name, "arguments": json.dumps(args, ensure_ascii=False)}]
            outcomes = await self._agent._execute_calls([], calls, "", None)
            outcome = outcomes[0] if outcomes else None
            self._agent._confirm_granted = False
            if outcome and outcome.get("ok"):
                result = str(outcome.get("result") or "Готово, сэр.")
            else:
                result = str((outcome or {}).get("result") or "Не удалось выполнить действие, сэр.")
            logger.info(f"confirmed action executed once: {name}")
            await self.push_frame(TTSSpeakFrame(result))
        except Exception:
            self._agent._confirm_granted = False
            logger.exception("confirmed action failed")
            await self.push_frame(TTSSpeakFrame("Не удалось выполнить подтверждённое действие, сэр."))
        return True

    async def _start_or_supersede_turn(self, text: str) -> None:
        if await self._handle_pending_confirmation(text):
            return
        if self._turn_task and not self._turn_task.done():
            if _CANCEL_RE.search(text):
                logger.info(f"heard while busy: {text!r} — cancelling current task")
                self._turn_task.cancel()
                await self.push_frame(TTSSpeakFrame("Отменяю, сэр."))
                self._busy = False
                return
            logger.info(f"heard while busy: {text!r} — superseding current task")
            self._turn_task.cancel()
        self._turn_task = asyncio.create_task(self._handle(text))

    async def _handle(self, text: str) -> None:
        self._busy = True
        try:
            logger.info(f"heard: {text!r}")
            direct = direct_computer_command(text)
            if direct is not None:
                logger.info(f"DIRECT COMPUTER: {text!r} -> {direct!r}")
                await self.push_frame(TTSSpeakFrame(direct))
                return

            def progress(_note: str) -> None:
                # No spoken generic acknowledgement. The final result is the only normal response.
                return None

            full: list[str] = []
            async for sentence in self._agent.respond_stream(text, on_progress=progress):
                if sentence:
                    full.append(sentence)
                    await self.push_frame(TTSSpeakFrame(sentence))
            if full:
                logger.info(f"reply: {' '.join(full)!r}")
        except asyncio.CancelledError:
            logger.info("brain turn cancelled")
            raise
        except Exception:
            logger.exception("brain turn failed")
            await self.push_frame(TTSSpeakFrame("Извините, сэр, при обработке команды произошла ошибка."))
        finally:
            self._busy = False
