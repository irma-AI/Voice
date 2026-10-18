# Pausing near the usage limit, and resuming

A thread **pauses** when the account's usage reaches the stop line (95% of the five-hour or the weekly limit, spec VOI-100): it hands its work over as a WIP draft PR and schedules its own restart. Whoever **resumes** treats the PR as a snapshot and checks what moved first.

## Pausing

Run these in order and end the turn:

1. Commit everything on the branch and push it.
2. Open the PR as a draft, or turn off auto-merge on an open one and set it back to draft, and put the **Paused** block (below) at the top of its body. A draft keeps auto-merge off, so half-done work never merges.
3. Comment the PR link on the ticket: `linearis issues discuss VOI-<n> --body "<PR link>"` (`docs/agents/issue-tracker.md`).
4. Schedule this thread's own restart for the reset time plus five minutes, with the block's **Resume** line as its text. When the reset is further away than the scheduler allows, skip it: the Paused block alone carries the resume.
5. Reply in the thread in one line: which limit, and when the work continues by itself (Stockholm time).

Done when the branch head on GitHub is your last commit, the PR is a draft whose body starts with the Paused block, the ticket links it, and the restart is scheduled or the **Continues** line says why not.

## The Paused block

```markdown
## Paused

- **Why**: <five-hour | weekly> usage at <n>%, paused at <YYYY-MM-DD HH:MM> Stockholm time
- **Continues**: after the reset at <YYYY-MM-DD HH:MM> Stockholm time; <restart scheduled | no restart scheduled, because ...>
- **Snapshot**: branch head `<sha>`, last merged with main at `<sha>`
- **Done**: <what is finished and pushed>
- **Next**: <the next step, concrete enough to start without this thread>
- **Open decisions**: <cards or questions still waiting, or none>
- **Resume**: follow docs/agents/usage-pause.md § Resuming, then `/next-step VOI-<n>`
```

The block also marks the work as unclaimed: whoever resumes removes it first.

## Resuming

The work may have moved during the pause, and so may main. Run these in order:

1. **Ownership.** Read the PR and the ticket. Stand down, and say so in one line, when the Paused block is gone, the PR is no longer a draft, it was merged or closed, or the ticket is done: someone else holds the work.
2. **Claim.** Remove the Paused block from the PR body, keeping the rest of the body.
3. **Branch.** Fetch the PR head and read the PR and ticket comments since the pause. When the head differs from the snapshot's branch head, read the new commits too. Work out the next step from what you read; the block's **Next** line is a hint.
4. **Main.** Merge main into the branch with a merge commit, so everyone else's checkout of the branch stays valid, and run `make check` before pushing.
5. **Continue** with `/next-step VOI-<n>`.

Done when the PR body has no Paused block, the branch holds main's head, `make check` passed, and `/next-step` has picked up the ticket.
