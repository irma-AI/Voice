# Manual actions for Petter

Things only Petter can do: agents can't change GitHub rulesets, click in a dashboard, or make a real phone call. Every thread adds a line here (via the one open draft PR "Manual actions for Petter") when it finds one. Tick a box when done; when the list is clear, merge.

Format: `- [ ] <what to do>, <where>. Needed for: <why>. Added by: <ticket or thread>.`

## Do when at a computer

- [x] GitHub, Settings, Rules, Rulesets, `main`: under "Require a pull request before merging", tick "Require conversation resolution before merging" and "Dismiss stale pull request approvals when new commits are pushed", then Save. Needed for: the live ruleset lacks the two rules `.github/rulesets/main.json` lists, and agents get a 403 on rulesets. Added by: the merge-rules work (PR #25, PR #27). Done 2026-10-18 (Petter says so; the live ruleset is not read back).
- [x] Google Cloud: switch on the Cloud Billing API for the core's Google project and let the core's key call it. Needed for: until then every call's cost is empty with the reason "catalogue unreadable". Added by: VOI-42 (PR #55). Done 2026-10-18 (Petter says so).
- [x] Make one short real call, then tell the thread "VOI-42: cost of each call". Needed for: its tokens and dollars get compared with Google's usage page, which also settles whether the model reports per-turn or running token totals. Do this after the Cloud Billing API is on. Added by: VOI-42 (PR #55). Test calls made 2026-10-18 (Petter says so); the VOI-42 thread still has to read the result.
- [ ] After PR #102 merges: in Google Cloud, create an API key limited to the Cloud Billing API; in Dokploy, add it as `BILLING_API_KEY` on the app "app", then redeploy. Needed for: the core reads Google's price catalogue with this key, so each call gets a cost (the Cloud Billing API itself is already on). Added by: VOI-42 (PR #102).

## Optional

Petter OK'd deleting these on 2026-10-18, but a session's `git push --delete` is refused by the proxy (tried on all three), so they stay yours. Or delete them in one go from github.com/irma-AI/Voice/branches.

- [ ] GitHub, Branches: delete the old `deploy-behind-login` branch. Needed for: tidiness only, it is an old branch nothing uses.
- [ ] GitHub, Branches: delete the scratch branch `claude/project-thread-d56n2t-scratch-base`. Needed for: tidiness only, it was left over from testing and threads can't delete branches. Added by: VOI-36 (PR #37).
- [ ] GitHub, Branches: delete the leftover branch `voi-48-claude-footer-guard`. Needed for: tidiness only, its PR #50 merged on 2026-10-17 and the proxy blocks branch deletes from sessions. Added by: VOI-48 (PR #50).

## Not at a computer

- [ ] Make a real phone call in a noisy place and tell the thread "VOI-19: real phone calls in noise". Needed for: the barge-in settings (start sensitivity low, 300 ms padding) were changed on a guess and never judged on a real noisy call. Added by: VOI-34.

## Waiting for your answer

Not computer steps; each has a thread waiting on you.

- [ ] Should the opening AI-disclosure line be impossible to interrupt? One call had it cut after half a second. It changes what callers hear, so it is your call. Thread: "Assistant interrupts itself on speaker".
- [ ] Rotate the Portal database password? A Dokploy deploy response printed it once in a session's tool result; the database has no outside port. Open as an `ESCALATED` line in `DECISIONS.md`.
