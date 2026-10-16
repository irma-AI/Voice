"""Writes what happened on a call to a JSONL file, for the eval Channel to read afterwards."""

import json
import time
from pathlib import Path

from pipecat.frames.frames import (
    Frame,
    FunctionCallInProgressFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    MetricsFrame,
    TranscriptionFrame,
    TTSTextFrame,
)
from pipecat.metrics.metrics import LLMUsageMetricsData, TTFBMetricsData
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class CallRecorder(FrameProcessor):
    """Passes every frame on and appends one line per transcript piece, usage report or delay.

    Gemini Live sends the Caller's transcript upstream and everything else downstream, so the
    pipeline holds two of these around the model; each writes only what travels its way.
    """

    def __init__(self, path: Path) -> None:
        super().__init__()  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs upstream
        self._path = path
        self._t0 = time.monotonic()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()  # a log that exists means the call got as far as the pipeline

    def _write(self, **event: object) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps({"t": round(time.monotonic() - self._t0, 3), **event}) + "\n"
            )

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            if direction == FrameDirection.UPSTREAM:
                self._write(e="caller", text=frame.text)
        elif isinstance(frame, FunctionCallInProgressFrame):
            if (
                direction == FrameDirection.DOWNSTREAM
            ):  # the service broadcasts it both ways
                self._write(
                    e="tool_call", name=frame.function_name
                )  # never the arguments
        elif isinstance(frame, LLMFullResponseStartFrame):
            self._write(e="agent_start")
        elif isinstance(frame, TTSTextFrame):
            self._write(e="agent_tts", text=frame.text)
        elif isinstance(frame, LLMTextFrame):
            self._write(e="agent_llm", text=frame.text)
        elif isinstance(frame, MetricsFrame):
            for d in frame.data:
                if isinstance(d, LLMUsageMetricsData):
                    self._write(e="usage", **d.value.model_dump(exclude_none=True))
                elif isinstance(d, TTFBMetricsData):
                    self._write(e="ttfb", seconds=d.value)
        await self.push_frame(frame, direction)
