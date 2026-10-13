"""The web Channel: Pipecat's built-in browser page. `make up` serves it."""

import os
import sys
from pathlib import Path

from pipecat.evals.transport import EvalTransport, EvalTransportParams
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport  # pyright: ignore[reportUnknownVariableType]  # untyped dict values upstream
from pipecat.transports.base_transport import TransportParams

from voice.agent import run_call


async def bot(runner_args: RunnerArguments) -> None:
    """Entry point the Pipecat runner calls once per browser connection."""
    transport = await create_transport(
        runner_args,
        {
            "webrtc": lambda: TransportParams(
                audio_in_enabled=True, audio_out_enabled=True
            ),
            "eval": lambda: EvalTransportParams(
                audio_in_enabled=True, audio_out_enabled=True
            ),
        },
    )
    log = os.environ.get("VOICE_CALL_LOG")
    await run_call(
        transport,
        record_to=Path(log) if log and isinstance(transport, EvalTransport) else None,
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        handle_sigint=runner_args.handle_sigint,
    )


if __name__ == "__main__":
    from pipecat.runner.run import main  # importing it loads .env

    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        sys.exit("GOOGLE_API_KEY is not set: put it in .env (see .env.example).")

    main()
