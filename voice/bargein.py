"""Barge-in: the detector settings and a timings-only record of every barge-in.

Gemini's own sound detector decides when the Caller has started to speak and cuts the agent off;
Pipecat only hears about it afterwards. This module holds the settings we send to that detector and
writes one event per barge-in. The recorder is the only writer of these events, and no event holds
the Caller's words or audio (.claude/rules/security.md).
"""

import json
import math
import time
from array import array
from collections import deque
from pathlib import Path

from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.google.gemini_live.llm import GeminiVADParams

# Nothing set means Gemini's own defaults, which is what a call has used so far; tuning is a later
# change. Edit here: it is an eval-required path (scripts/eval-required.json).
VAD = GeminiVADParams()

LOUDNESS_WINDOW_S = 0.5
SILENCE_DBFS = -100.0  # what digital silence reads as, instead of minus infinity


def _dbfs(level: float) -> float:
    """A 16-bit sample level (0 to 32768) as dB below full scale."""
    return round(
        max(SILENCE_DBFS, 20 * math.log10(level / 32768)) if level else SILENCE_DBFS, 1
    )


class BargeInRecorder(FrameProcessor):
    """Passes every frame on and writes the barge-in events: INFO log lines, and the eval file if given.

    Sits just before the model, where it sees the Caller's audio going in and, coming back
    upstream, the model's interrupted signal, the output transport's speaking frames and the
    Caller's transcript (of which only the word count is kept).
    """

    def __init__(self, call_id: str, path: Path | None = None) -> None:
        super().__init__()  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs upstream
        self._call_id = call_id
        self._path = path
        self._t0 = time.monotonic()
        # (arrival time, peak, sum of squares, samples) of recent Caller audio frames
        self._audio: deque[tuple[float, int, int, int]] = deque()
        self._bot_since: float | None = None
        self._barge_in_at: float | None = None  # waiting for the Caller's words
        self._resume_after: float | None = None  # waiting for the agent to speak again
        self._ended = False
        self._write(
            e="config",
            vad=VAD.model_dump(mode="json", exclude_none=True),
        )

    def _write(self, **event: object) -> None:
        line = {
            "t": round(time.monotonic() - self._t0, 3),
            "call": self._call_id,
            **event,
        }
        text = json.dumps(line)
        logger.info(f"barge-in {text}")
        if self._path:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")

    def _loudness(self, now: float) -> tuple[float, float]:
        """Peak and average level of the Caller's last half second, in dBFS."""
        while self._audio and self._audio[0][0] < now - LOUDNESS_WINDOW_S:
            self._audio.popleft()
        peak = max((a[1] for a in self._audio), default=0)
        n = sum(a[3] for a in self._audio)
        rms = math.sqrt(sum(a[2] for a in self._audio) / n) if n else 0
        return _dbfs(peak), _dbfs(rms)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        now = time.monotonic()
        if isinstance(frame, InputAudioRawFrame):
            # ponytail: 16-bit mono PCM, little-endian as the transports send it; a Channel with
            # another format needs converting first.
            samples = array("h", frame.audio[: len(frame.audio) // 2 * 2])
            if samples:
                self._audio.append(
                    (
                        now,
                        max(abs(s) for s in samples),
                        sum(s * s for s in samples),
                        len(samples),
                    )
                )
        elif direction == FrameDirection.UPSTREAM:
            if isinstance(frame, BotStartedSpeakingFrame):
                self._bot_since = now
                self._write(e="bot_speech", phase="start")
                if self._resume_after is not None:
                    self._write(
                        e="resumed",
                        after_barge_in_ms=round((now - self._resume_after) * 1000),
                    )
                    self._resume_after = None
            elif isinstance(frame, BotStoppedSpeakingFrame):
                played = round((now - self._bot_since) * 1000) if self._bot_since else 0
                self._bot_since = None
                self._write(e="bot_speech", phase="stop", played_ms=played)
            elif isinstance(frame, InterruptionFrame):
                peak, rms = self._loudness(now)
                since = self._bot_since
                self._write(
                    e="barge_in",
                    bot_speaking=since is not None,
                    bot_ms=round((now - since) * 1000)
                    if since is not None
                    else 0,  # this stretch of speech
                    peak_dbfs=peak,
                    rms_dbfs=rms,
                    src="gemini",
                )
                self._barge_in_at = now
                self._resume_after = now if since is not None else None
            elif isinstance(frame, TranscriptionFrame):
                words = len(frame.text.split())
                cut = self._barge_in_at
                if words and cut is not None:  # only the first words after a barge-in
                    self._write(
                        e="caller_words",
                        words=words,
                        after_barge_in_ms=round((now - cut) * 1000),
                    )
                    self._barge_in_at = None
        elif isinstance(frame, (EndFrame, CancelFrame)) and not self._ended:
            self._ended = True
            self._write(
                e="end",
                reason="cancel" if isinstance(frame, CancelFrame) else "end",
                secs=round(now - self._t0, 1),
            )
        await self.push_frame(frame, direction)
