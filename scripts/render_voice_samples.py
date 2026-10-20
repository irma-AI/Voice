"""`make voice-samples`: one short call per voice setup, so Petter can pick the agent's sound by ear (VOI-156).

PAID, ask Petter first: 8 Gemini Live calls, about 1 to 4 SEK, stopped at the per-run cap in tests/evals/caps.json.
Each setup changes one thing against the core today (docs/research/gemini-live-voice-and-language.md § 5) and plays
the two stored Caller lines; the agent's audio goes to the git-ignored eval-runs/voice-samples/<setup>.wav.
Logs setup names, durations and token counts only, never words.

Driven through google-genai directly, not Pipecat: setup C sends no speech config at all, which Pipecat can't express.
The setup mirrors what Pipecat sends for the core (seed, history config, VAD, max output tokens); transcription is off.
"""

import asyncio
import os
import sys
import wave
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from tests.evals.checks import BUSINESS_FILE
from tests.evals.cost import cost_sek
from tests.evals.spend import Caps
from voice.agent import system_instruction
from voice.bargein import VAD
from voice.cost import MODEL
from voice.settings import load_settings

ROOT = Path(__file__).parent.parent
OUT = ROOT / "eval-runs" / "voice-samples"
CALLER = [
    ROOT / "tests" / "evals" / "audio" / f"{n}.wav"
    for n in ("opening_hours_sv", "switch_to_english_en")
]
RATE_OUT = 24000  # Gemini Live always answers in 24 kHz 16-bit mono PCM
CHUNK_S = 0.04  # Google: send 20-40 ms chunks
TURN_TIMEOUT_S = 30
GAP = b"\0\0" * int(
    RATE_OUT * 0.5
)  # half a second between the agent's turns in the clip

# The first demo's tone lines (archive `app/prompts.py`), for setup E only: samples, never the product's prompt.
TONE = """\
You are a friendly assistant on a phone call for the business below.
Talk like a person on the phone: short turns, contractions, the odd "mm" or "okej".
Use informal "du" in Swedish.
"""


def speech(voice: str | None, language: str | None = None) -> types.SpeechConfig:
    prebuilt = types.PrebuiltVoiceConfig(voice_name=voice)
    return types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=prebuilt),
        language_code=language,
    )


# setup -> (speech config, VAD silence ms, prompt prefix). None: not sent.
SETUPS: dict[str, tuple[types.SpeechConfig | None, int | None, str]] = {
    "A": (speech("Charon", "sv-SE"), None, ""),  # the core today
    "B": (speech("Charon"), None, ""),
    "C": (None, None, ""),  # the demo's: the server's default voice
    "D1": (speech("Sulafat"), None, ""),
    "D2": (speech("Achird"), None, ""),
    "D3": (speech("Zubenelgenubi"), None, ""),
    "D4": (speech("Despina"), None, ""),
    "E": (None, 500, TONE),
}


def config(setup: str, instruction: str) -> types.LiveConnectConfig:
    voice, silence_ms, prefix = SETUPS[setup]
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        max_output_tokens=4096,  # Pipecat's default, which the core sends
        speech_config=voice,
        system_instruction=prefix + instruction,
        history_config=types.HistoryConfig(initial_history_in_client_content=True),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=VAD.start_sensitivity,
                end_of_speech_sensitivity=VAD.end_sensitivity,
                prefix_padding_ms=VAD.prefix_padding_ms,
                silence_duration_ms=silence_ms
                if silence_ms is not None
                else VAD.silence_duration_ms,
            )
        ),
    )


def audio_tokens(details: list[types.ModalityTokenCount] | None) -> int:
    return sum(
        d.token_count or 0
        for d in details or []
        if d.modality == types.MediaModality.AUDIO
    )


def usage_event(u: types.UsageMetadata) -> dict[str, Any]:
    """One usage report in the shape tests/evals/cost.py prices."""
    return {
        "prompt_tokens": u.prompt_token_count or 0,
        "completion_tokens": u.response_token_count or 0,
        "input_audio_tokens": audio_tokens(u.prompt_tokens_details),
        "output_audio_tokens": audio_tokens(u.response_tokens_details),
        "reasoning_tokens": u.thoughts_token_count or 0,
    }


async def call(
    client: genai.Client, setup: str, instruction: str
) -> tuple[bytes, list[dict[str, Any]]]:
    """One call: the disclosure, then each Caller line in real time. Returns the agent's audio and the usage reports."""
    turns: list[bytearray] = [bytearray()]
    usage: list[dict[str, Any]] = []
    done = asyncio.Event()
    async with client.aio.live.connect(
        model=MODEL, config=config(setup, instruction)
    ) as s:

        async def receive() -> None:
            got = True
            while got:  # each receive() is one whole agent turn (it waits out IN_PROGRESS); an empty one: closed
                got = False
                async for m in s.receive():
                    got = True
                    sc = m.server_content
                    for p in (
                        (sc.model_turn.parts or []) if sc and sc.model_turn else []
                    ):
                        if p.inline_data and p.inline_data.data:
                            turns[-1] += p.inline_data.data
                    if m.usage_metadata:
                        usage.append(usage_event(m.usage_metadata))
                done.set()

        async def silence_until_done() -> None:
            # Silence keeps the stream going, so the server's VAD sees the Caller stop.
            quiet = b"\0\0" * int(RATE_OUT * CHUNK_S)
            async with asyncio.timeout(TURN_TIMEOUT_S):
                while not done.is_set():
                    if receiver.done():
                        receiver.result()  # raises what the server said (a refused voice, a closed session)
                        raise RuntimeError(
                            f"setup {setup}: the session closed mid-call"
                        )
                    await send(quiet)

        async def send(pcm: bytes) -> None:
            await s.send_realtime_input(
                audio=types.Blob(data=pcm, mime_type=f"audio/pcm;rate={RATE_OUT}")
            )
            await asyncio.sleep(CHUNK_S)

        receiver = asyncio.create_task(receive())
        try:
            # The core's seed turn, sent the way Pipecat sends it for Gemini 3.
            seed = types.Content(
                role="user", parts=[types.Part(text="The call has just connected.")]
            )
            await s.send_client_content(turns=[seed], turn_complete=True)
            await s.send_realtime_input(text=" ")
            await silence_until_done()
            for line in CALLER:
                done.clear()
                turns.append(bytearray())
                with wave.open(str(line), "rb") as w:
                    assert w.getframerate() == RATE_OUT and w.getsampwidth() == 2
                    pcm = w.readframes(w.getnframes())
                step = int(RATE_OUT * CHUNK_S) * 2
                for i in range(0, len(pcm), step):
                    await send(pcm[i : i + step])
                await silence_until_done()
        finally:
            receiver.cancel()
    return GAP.join(bytes(t) for t in turns if t), usage


async def main(only: list[str]) -> int:
    setups = only or list(SETUPS)
    if unknown := [x for x in setups if x not in SETUPS]:
        print(f"unknown setup {unknown}; known: {list(SETUPS)}", file=sys.stderr)
        return 2
    cap = Caps.load().per_run_sek
    instruction = system_instruction(
        load_settings({"SETTINGS_FILE": str(BUSINESS_FILE), "SETTINGS_URL": ""})
    )
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    OUT.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    for setup in setups:
        # shortcut: checks the per-run cap only, not the eval ledger's loop and day caps; add them if this runs often.
        if spent >= cap:
            print(f"STOPPED by the run cap {cap} SEK before {setup}", file=sys.stderr)
            return 3
        pcm, usage = await call(client, setup, instruction)
        sek = cost_sek(usage)
        spent += sek
        out = OUT / f"{setup}.wav"
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE_OUT)
            w.writeframes(pcm)
        tokens = sum(u["prompt_tokens"] + u["completion_tokens"] for u in usage)
        print(
            f"{setup:<3} {len(pcm) / 2 / RATE_OUT:5.1f}s {tokens:>6} tokens {sek:5.2f} SEK  {out}"
        )
    print(f"spent {spent:.2f} SEK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
