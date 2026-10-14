# Did lowering the barge-in sensitivity help on a real noisy call?

Written 2026-10-14 for VOI-19. **Not checked yet.** No noisy phone call has been made since the change went live, so this note has no numbers and says so.

## What is known

- Live since 2026-10-14 (Swedish time) at 09:52: Gemini start sensitivity LOW and 300 ms of speech before a start counts (`voice/bargein.py`, VOI-18). The setting is logged in each call's `config` event.
- The noise Scenario passed on Gemini's old defaults too, so the eval cannot show the change helps (DECISIONS.md, VOI-18).
- The only real call logged so far was a quiet-room AirPods call before the change: two real speech barge-ins, average -23 to -26 dBFS, Caller words about 1.8 to 1.9 s after each. That is not a noisy "before". The old container's log is also gone after the deploy, so the numbers above are the only record.
- A noisy "before" is no longer possible without redeploying the old settings, which is Petter's call.

## What to do now

Stop here: build no gate and no noise filter. Nothing shows a problem is left, and a gate's thresholds would be guesses without a noisy call's log (research: `barge-in-and-call-metrics.md`). That is a default, not a finding.

## What would settle it

One real call from Petter's phone, in the noisy place, 2 to 3 minutes: two long answers left to finish, one talk-over. Read its `barge-in` lines in the Dokploy log (timings only, no words or audio) and count barge-ins per minute, how many had no Caller words within 5 s, how loud, and how long the agent had played. A few false barge-ins per call and the next step is a gate; none and nothing more is needed. Tracked as VOI-34.
