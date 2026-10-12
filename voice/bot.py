"""The web Channel: Pipecat's built-in browser page. `make up` serves it."""

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
            )
        },
    )
    await run_call(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
