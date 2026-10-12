"""The agent: one place builds it, and every Channel only hands it a transport."""

import os
from pathlib import Path

from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.runner.types import RunnerArguments
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.workers.runner import WorkerRunner

MODEL = "models/gemini-3.8-live"

# Legal wording approved by Petter 2026-10-12; changing it is his call (CLAUDE.md § Stop and ask).
DISCLOSURE = "Du pratar med en AI-assistent."

BUSINESS = (Path(__file__).parent / "business.txt").read_text(encoding="utf-8")

# ponytail: the model is asked to say the disclosure first, which it can skip;
# a pre-rendered clip played before any model speech makes it certain (compliance work).
SYSTEM_INSTRUCTION = f"""\
Start every call by saying exactly: "{DISCLOSURE}"
Speak Swedish. Switch to English only if the caller speaks English.
Max 2 sentences per turn. No lists or formatting: everything is spoken aloud.
Answer only from the business facts below. Not in the facts: say you don't know.
Never state a price that is not in the facts.

Business facts:
{BUSINESS}"""


async def run_call(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Runs one call on any Channel's transport until the Caller leaves."""
    llm = GeminiLiveLLMService(
        api_key=os.environ["GOOGLE_API_KEY"],
        settings=GeminiLiveLLMService.Settings(
            model=MODEL, system_instruction=SYSTEM_INSTRUCTION
        ),
    )
    user, assistant = LLMContextAggregatorPair(LLMContext())
    pipeline = Pipeline([transport.input(), user, llm, transport.output(), assistant])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def _greet(*_: object) -> None:  # pyright: ignore[reportUnusedFunction]
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def _hang_up(*_: object) -> None:  # pyright: ignore[reportUnusedFunction]
        await runner.cancel()

    await runner.run()
