# Manual actions for Petter

Things only a person at a computer can do: agents can't change GitHub rulesets or click in a dashboard. Every thread adds a line here (via the one open draft PR "Manual actions for Petter") when it finds one. Tick a box when done; when the list is clear, merge.

Format: `- [ ] <what to do>, <where>. Needed for: <why>. Added by: <ticket or thread>.`

## Do when at a computer

- [ ] GitHub, Settings, Rules, Rulesets, `main`: under "Require a pull request before merging", tick "Require conversation resolution before merging" and "Dismiss stale pull request approvals when new commits are pushed", then Save. Needed for: the live ruleset lacks the two rules `.github/rulesets/main.json` lists, and agents get a 403 on rulesets. Added by: the merge-rules work (PR #25, PR #27).

## Optional

- [ ] GitHub, Branches: delete the old `deploy-behind-login` branch. Needed for: tidiness only, it sits on the pre-rewrite history.
- [ ] GitHub, Branches: delete the scratch branch `claude/project-thread-d56n2t-scratch-base`. Needed for: tidiness only, it was left over from testing and threads can't delete branches. Added by: VOI-36 (PR #37).

## Not on this list

Phone calls and other tests Petter does by hand (the noisy phone call, VOI-34): they are tickets, not computer work.
