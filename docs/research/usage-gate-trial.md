# Usage gate trial (VOI-103)

A supervised trial of the usage gate (`scripts/usage-gate.js`, VOI-102) in a real Projects cloud thread, 2026-10-18. All times are Stockholm time. Everything below was seen in this thread's own transcript (session `session_014Rbvn1eMuKUVu25ttNcm9J`). Sources: the gate's own deny and context messages, and the session's `rate_limit_event` entries read with `list_events`.

## Set-up

- The trial ran in the thread that built the gate. A Claude Code session reloads `.claude/settings.json` and the hook scripts from its working tree as they change, so this thread ran under whatever gate its checkout held.
- In the first part (13:25 to 13:37), main's lines were in force (warn 90%, stop 95%), while the five-hour window really climbed from 86% to 94%.
- For the stop and the resume (17:36 to 17:41), the PR branch held a trial stop line of 7% and a warn line of 6%, below the real readings. This had to be a branch commit, because the numbers live only in the gate.

## What was seen

| Time | Step | Seen |
|---|---|---|
| 13:25 | No reading yet | Denied a Bash call that chained `cat` after `record`, with the refresh instructions. `record` alone ran. |
| 13:31 | Warn line (91%) | Every tool call allowed with the added context "five-hour usage at 91% … Finish the current step and prepare the handoff". The prompt hook added the same. |
| 13:34 | Stale reading (159 s) | Denied `ReadNotifications` until `list_events` and `record` had run. Both were allowed while stale. |
| 17:36 | Stop line (trial 7%, weekly 50%) | Denied `Write` with the pause instructions. Allowed the handoff: `git add`, `git commit` and `git push` chained with `&&`, draft PR create, `send_later`, reply, status and the ticket comment. |
| 17:37 | Handoff complete | Draft PR #112 opened with the Paused block, ticket VOI-103 commented, restart scheduled for 17:41, one-line reply posted. |
| 17:38 | Resume | Simulated reset (below). Ownership checked (Paused block present, draft, ticket open), block removed, head equal to the snapshot, main unmoved. |
| 17:41 | Restart reminder | Scheduled at 17:37 with `send_later`; firing not yet seen when this note was written. |

**Simulated reset.** The real windows were days away from resetting, so the reset was simulated: the thread recorded the real utilization with both reset times set in the past. `record` is always allowed, so a thread can always do this. It is also how a thread could lie its way out of a pause. That is the self-reported reading risk the spec names, now seen to be easy.

## What did not hold

1. **The quiet end of a turn is blocked while paused.** `no_reply_needed` and `ReadNotifications` are in neither allow-list. A paused thread therefore cannot end a turn quietly, while the Stop hook demands that tool or a reply, so every wake costs Petter a notifying reply. `ReadNotifications` is also blocked while the reading is stale. Fix: add both to the always-allowed tools (VOI-109).
2. **A redirect breaks an allowed command.** `linearis issues discuss … > /dev/null` was denied because `>` is not allowed. The doc's form, with no redirect, passed. This holds as designed, so there is nothing to fix.
3. **Stopped means stuck on the branch.** While stopped, `git checkout` and edits are denied, so a thread that lowers the line on its own branch cannot raise it back. It can only hand off and wait, or record a new reading. This holds as designed for the real line. For a trial, plan the exit before lowering the line.

## Also noted

- The first model call after the 4-hour idle gap moved the five-hour window from 4% to 15% within about two minutes (17:35 to 17:38). The context was about 100k tokens. This fits re-reading a long context after the cache expired, but that cause is inferred. A thread resuming after a reset can spend a tenth of a window before doing anything.
- Readings follow model calls, as in research §7b. During the trial the newest entry was never more than about 1 minute old while the thread worked.
