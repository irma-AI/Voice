"""The M0 spike: a browser call to Gemini Live through Pipecat. `make up` serves it."""

import os

from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport  # pyright: ignore[reportUnknownVariableType]  # untyped dict values upstream
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.workers.runner import WorkerRunner

MODEL = "models/gemini-3.8-live"

# Legal wording approved by Petter 2026-10-12; changing it is his call (CLAUDE.md § Stop and ask).
DISCLOSURE = "Du pratar med en AI-assistent."

# ponytail: the model is asked to say the disclosure first, which it can skip;
# a pre-rendered clip played before any model speech makes it certain (M2 compliance layer).
SYSTEM_INSTRUCTION = f"""\
Start every call by saying exactly: "{DISCLOSURE}"
Speak Swedish. Switch to English only if the caller speaks English.
Max 2 sentences per turn. No lists or formatting: everything is spoken aloud."""


async def bot(runner_args: RunnerArguments) -> None:
    """Entry point the Pipecat runner calls once per browser connection."""
    transport = await create_transport(
        runner_args,
        {
            "webrtc": lambda: TransportParams(
                audio_in_enabled=True, audio_out_enabled=True
            )
        },
    )
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


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
