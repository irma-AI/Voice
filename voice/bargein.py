"""Barge-in: the detector settings and a timings-only record of every barge-in.

Gemini's own sound detector decides when the Caller has started to speak and cuts the agent off;
Pipecat only hears about it afterwards. This module holds the settings we send to that detector and
writes one event per barge-in. The recorder is the only writer of these events, and no event holds
the Caller's or the agent's words or audio (.claude/rules/security.md): levels, timings and scores only.
"""

import json
import math
import re
import time
from array import array
from collections import deque
from pathlib import Path

from google.genai.types import StartSensitivity
from loguru import logger
from pipecat.frames.frames import (
    AudioRawFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    TTSTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.google.gemini_live.llm import GeminiVADParams

# Lower start sensitivity, and 300 ms of speech before a start counts (Gemini's default is more eager):
# a short noise should no longer cut the agent off. First guess: the noise Scenario passed on the old
# settings, so no run has shown these values to be better; VOI-19 compares real calls.
# Edit here: it is an eval-required path (scripts/eval-required.json).
VAD = GeminiVADParams(
    start_sensitivity=StartSensitivity.START_SENSITIVITY_LOW, prefix_padding_ms=300
)

LOUDNESS_WINDOW_S = 0.5
SILENCE_DBFS = -100.0  # what digital silence reads as, instead of minus infinity
# The echo signature: the Caller's envelope in the half second before a cut against the agent's
# output envelope, in 20 ms steps, shifted back 0 to 500 ms in 10 ms steps (out of the speaker, through
# the room, back in).
ENVELOPE_STEP_S = 0.02
ECHO_LAG_STEP_S = 0.01
ECHO_MAX_LAG_S = 0.5
# The level trace: both sides in 100 ms steps from half a second before a cut to half a second after.
TRACE_STEP_S = 0.1
TRACE_HALF_S = 0.5
# How much audio level history is kept, and how many of the agent's last words (in memory only, for the score).
KEEP_S = LOUDNESS_WINDOW_S + ECHO_MAX_LAG_S + TRACE_HALF_S
AGENT_WORDS = 30

# (arrival time, length in seconds, peak, mean square) of one audio frame, in 16-bit sample levels
Level = tuple[float, float, int, float]


def _dbfs(level: float) -> float:
    """A 16-bit sample level (0 to 32768) as dB below full scale."""
    return round(
        max(SILENCE_DBFS, 20 * math.log10(level / 32768)) if level else SILENCE_DBFS, 1
    )


def _level(frame: AudioRawFrame, now: float) -> Level | None:
    # ponytail: 16-bit mono PCM, little-endian as the transports send it; a Channel with
    # another format needs converting first.
    samples = array("h", frame.audio[: len(frame.audio) // 2 * 2])
    if not samples:
        return None
    return (
        now,
        len(samples) / frame.sample_rate,
        max(abs(s) for s in samples),
        sum(s * s for s in samples) / len(samples),
    )


def _keep(levels: deque[Level], level: Level | None, now: float) -> None:
    if level:
        levels.append(level)
    while levels and levels[0][0] < now - KEEP_S:
        levels.popleft()


def _envelope(
    levels: deque[Level], start: float, steps: int, step: float
) -> list[float]:
    """The RMS level of each step from `start`, each frame spread over the time it lasted (it ends on arrival)."""
    power = [0.0] * steps
    for end, length, _, mean_square in levels:
        begin = end - length
        first = max(0, math.floor((begin - start) / step))
        for i in range(first, min(steps, math.ceil((end - start) / step))):
            lo = start + i * step
            overlap = min(end, lo + step) - max(begin, lo)
            if overlap > 0:
                power[i] += mean_square * overlap / step
    return [math.sqrt(p) for p in power]


def _correlation(a: list[float], b: list[float]) -> float:
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    return cov / math.sqrt(va * vb) if va and vb else 0.0


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _similarity(heard: list[str], said: list[str]) -> float:
    """The share of the heard word pairs (one word: words) that the agent said in that order.

    Pairs, so that common words the Caller shares with the agent ("en", "det") do not count as echo.
    """
    n = min(2, len(heard))
    pairs = [tuple(heard[i : i + n]) for i in range(len(heard) - n + 1)]
    known = {tuple(said[i : i + n]) for i in range(len(said) - n + 1)}
    return round(sum(p in known for p in pairs) / len(pairs), 2) if pairs else 0.0


class BargeInRecorder(FrameProcessor):
    """Passes every frame on and writes the barge-in events: INFO log lines, and the eval file if given.

    Sits just before the model, where it sees the Caller's audio going in and, coming back
    upstream, the model's interrupted signal, the output transport's speaking frames and the
    Caller's transcript (of which only the word count and a similarity score are kept). Its
    `output_side` sits just after the output transport and hands it the agent's audio as played
    and the agent's words (held in memory for the score, never written).
    """

    def __init__(self, call_id: str, path: Path | None = None) -> None:
        super().__init__()  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs upstream
        self._call_id = call_id
        self._path = path
        self._t0 = time.monotonic()
        self._caller: deque[Level] = deque()
        self._agent: deque[Level] = deque()
        self._agent_words: deque[str] = deque(maxlen=AGENT_WORDS)
        self.output_side = _OutputSide(self)
        self._bot_since: float | None = None
        self._barge_in_at: float | None = None  # waiting for the Caller's words
        self._resume_after: float | None = None  # waiting for the agent to speak again
        self._trace_at: float | None = None  # waiting for the half second after a cut
        self._barge_ins = 0
        self._no_words = 0
        self._stretches = 0  # stretches of agent speech
        self._cut = 0  # of which a barge-in cut short
        self._this_stretch_cut = False
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

    def agent_audio(self, frame: OutputAudioRawFrame) -> None:
        now = time.monotonic()
        _keep(self._agent, _level(frame, now), now)

    def agent_words(self, text: str) -> None:
        self._agent_words.extend(_words(text))

    def _loudness(self, now: float) -> tuple[float, float]:
        """Peak and average level of the Caller's last half second, in dBFS."""
        recent = [a for a in self._caller if a[0] >= now - LOUDNESS_WINDOW_S]
        peak = max((a[2] for a in recent), default=0)
        n = sum(a[1] for a in recent)
        rms = math.sqrt(sum(a[3] * a[1] for a in recent) / n) if n else 0
        return _dbfs(peak), _dbfs(rms)

    def _echo(self, now: float) -> tuple[float, int]:
        """How closely the Caller's last half second follows the agent's output, and at what delay."""
        steps = round(LOUDNESS_WINDOW_S / ENVELOPE_STEP_S)
        start = now - LOUDNESS_WINDOW_S
        caller = _envelope(self._caller, start, steps, ENVELOPE_STEP_S)
        best, lag = 0.0, 0
        for shift in range(round(ECHO_MAX_LAG_S / ECHO_LAG_STEP_S) + 1):
            back = shift * ECHO_LAG_STEP_S
            agent = _envelope(self._agent, start - back, steps, ENVELOPE_STEP_S)
            if (fit := _correlation(caller, agent)) > best:
                best, lag = fit, round(back * 1000)
        return round(best, 2), lag

    def _write_trace(self) -> None:
        cut, self._trace_at = self._trace_at, None
        if cut is None:
            return
        steps = round(2 * TRACE_HALF_S / TRACE_STEP_S)
        start = cut - TRACE_HALF_S
        self._write(
            e="levels",
            caller_dbfs=[
                _dbfs(x) for x in _envelope(self._caller, start, steps, TRACE_STEP_S)
            ],
            bot_dbfs=[
                _dbfs(x) for x in _envelope(self._agent, start, steps, TRACE_STEP_S)
            ],
        )

    def _barge_in(self, now: float, src: str) -> None:
        self._write_trace()
        if self._barge_in_at is not None:
            self._no_words += 1
        self._barge_ins += 1
        peak, rms = self._loudness(now)
        corr, lag = self._echo(now)
        since = self._bot_since
        if since is not None and not self._this_stretch_cut:
            self._this_stretch_cut = True
            self._cut += 1
        self._write(
            e="barge_in",
            bot_speaking=since is not None,
            bot_ms=round((now - since) * 1000)
            if since is not None
            else 0,  # this stretch of speech
            peak_dbfs=peak,
            rms_dbfs=rms,
            src=src,
            echo_corr=corr,
            echo_lag_ms=lag,
        )
        self._barge_in_at = now
        self._resume_after = now if since is not None else None
        self._trace_at = now

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        now = time.monotonic()
        if self._trace_at is not None and now >= self._trace_at + TRACE_HALF_S:
            self._write_trace()
        if isinstance(frame, InputAudioRawFrame):
            _keep(self._caller, _level(frame, now), now)
        elif isinstance(frame, InterruptionFrame):
            # Upstream it can only come from the model (Gemini's interrupted signal); downstream from
            # what sits before the recorder (Pipecat's own turn handling or the worker).
            self._barge_in(
                now, "gemini" if direction == FrameDirection.UPSTREAM else "pipecat"
            )
        elif direction == FrameDirection.UPSTREAM:
            if isinstance(frame, BotStartedSpeakingFrame):
                self._bot_since = now
                self._stretches += 1
                self._this_stretch_cut = False
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
            elif isinstance(frame, TranscriptionFrame):
                words = _words(frame.text)
                cut = self._barge_in_at
                if words and cut is not None:  # only the first words after a barge-in
                    self._write(
                        e="caller_words",
                        words=len(words),
                        after_barge_in_ms=round((now - cut) * 1000),
                        # compared here in memory; neither side's words are written
                        similarity=_similarity(words, list(self._agent_words)),
                    )
                    self._barge_in_at = None
        elif isinstance(frame, (EndFrame, CancelFrame)) and not self._ended:
            self._ended = True
            self._write_trace()
            if self._barge_in_at is not None:
                self._no_words += 1
            self._write(
                e="end",
                reason="cancel" if isinstance(frame, CancelFrame) else "end",
                secs=round(now - self._t0, 1),
                barge_ins=self._barge_ins,
                no_words=self._no_words,
                cut_share=round(self._cut / self._stretches, 2)
                if self._stretches
                else 0.0,
            )
        await self.push_frame(frame, direction)


class _OutputSide(FrameProcessor):
    """After the output transport: the agent's audio as it is played, and its words for the score."""

    def __init__(self, recorder: BargeInRecorder) -> None:
        super().__init__()  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs upstream
        self._recorder = recorder

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, OutputAudioRawFrame):
            self._recorder.agent_audio(frame)
        elif isinstance(frame, TTSTextFrame):
            self._recorder.agent_words(frame.text)
        await self.push_frame(frame, direction)
