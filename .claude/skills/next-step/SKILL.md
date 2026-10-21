---
name: next-step
description: Picks and runs the flow of this repo's skills for a piece of work, in order, with gates. Use when starting a feature, a bug fix, a new page, component or visual change, when resuming a tracker issue, or when asked what to do next. Not for one-off edits or questions.
---

# Next step

Routes a situation to a **flow** (an ordered checklist of this repo's skills) and runs it. Typed as `/next-step [situation | <issue-id>]`, or loaded by the agent when a request matches its description. With no situation or issue given, read the conversation so far, or resume from the tracker (§ Tickets and resuming).

Repo specifics live in `CLAUDE.md` and `docs/agents/`; this skill names the sections it needs. A section missing → ask the user for the fact, and suggest adding it there.

## Running a flow

1. Pick the flow from § Pick a flow and name it with one line on why. Nothing fits → say so and suggest working without a skill.
2. Copy the flow's checklist into your reply. Tick steps off as they finish and repost it at every gate.
3. Run each skill step through the Skill tool yourself, so its hooks fire. The user never has to type a flow's skill: the ones upstream marks user-only are made agent-callable by `scripts/vendor-skills.sh`, and the gates below are the human stop.
4. Go from step to step without asking, except at a gate ⏸.
5. Only the user can type `/clear` and `/compact`. Where a flow needs one, stop and end with the exact next command, e.g. "Type `/clear`, then `/next-step <issue-id>`."

## Gates ⏸

Stop and wait for the user. Pushing, opening a PR and merging a green one are not gates (`CLAUDE.md` § Workflow):

- after picking the flow: show its checklist and wait for the go before the first step, unless the user already asked for this flow or gave `/next-step <issue-id>`
- during an interview or a question a skill asks (`grill-with-docs`, `impeccable shape`, `impeccable critique`'s closing question, `impeccable` choices such as the decision page or `quieter`'s questions, `triage`, `wayfinder`)
- at a Design review's pick (which findings to fix) and its ship-or-iterate on the after screenshots
- at `to-spec`'s and `tdd`'s seam checks, unless the spec already agreed the seams
- after `to-tickets`: the user approves the tickets
- when a step fails twice, or a skill or `CLAUDE.md` says to ask first (`CLAUDE.md` § Stop and ask)
- when you park a choice for a person: its `ESCALATED` line goes in `DECISIONS.md` first (`CLAUDE.md` § Decisions)

## Shared steps

The flows below name these:

- **branch**: before the first edit, if on the default branch, branch from it up to date, named by `CLAUDE.md` § Workflow's convention (the spec's or issue's id where there is one). Never commit to the default branch.
- **ticket**: before the first edit outside the `no_ticket` paths of `scripts/low-risk-paths.json`, the work needs a ready ticket (label `ready-for-agent`), because a hook denies the edit and a CI guard fails the PR without one. A Small change or Bug with none gets one now: create it with `linearis` (`docs/agents/issue-tracker.md`) and label it ready once the user's go for the flow is given. Then record it for the hook: `echo <issue-id> > "$(git rev-parse --git-path next-step-ticket)"`. The record lasts one session: a fresh start clears it (a resume, `/clear` or `/compact` keeps it), so a new session runs `/next-step <issue-id>` again. The PR body says `Closes <issue-id>`.
- **implement**: follow `implement`, with two overrides: its `/code-review` is the **review** step below, and its commit is the **commit** step.
- **review**: `code-review` against `git merge-base origin/<default branch> HEAD`. Diff the working tree against the merge base (`git diff <merge-base>`), which covers commits and uncommitted changes, not `...HEAD`. Give it the ticket or spec as the spec, and `CLAUDE.md`, every `.claude/rules/` file whose `paths:` match the diff (plus `DESIGN.md` if the repo has one) as the standards. Fix what it finds that holds up; list anything you disagree with for the user, and log each finding you decline (`CLAUDE.md` § Decisions).
- **commit**: commit on the branch as often as the work needs, never on the default branch.
- **skeptic**: when the change touches a path in the `skeptic_pass` list or a `CLAUDE.md` § Stop and ask area (`CLAUDE.md` § Workflow holds the rule and the guard), run `skeptic-pass` on the frozen head and put its SHA and result in the PR body's `## Skeptic pass` section; otherwise skip it.
- **pr**: walk `CLAUDE.md` § Definition of Done item by item; every item holds, or you name the one that doesn't and why. Then push and open the PR without asking, and `pr` writes the body, filling every section of `.github/pull_request_template.md`: the three first-principles answers and what is not live yet. The PR names every ticket it closes, with the tracker's closing keyword (`docs/agents/issue-tracker.md`).
- **merge**: unless a `CLAUDE.md` § Stop and ask area applies, mark the PR ready and turn on auto-merge (`gh pr merge --auto --squash`, or the GitHub MCP `enable_pr_auto_merge`); once `ci-summary` passes, the merge queue retests the PR on top of main and merges it (`CLAUDE.md` § Workflow), so end the turn instead of waiting on CI or updating the branch. If checks already passed, `gh pr merge --squash` without `--auto` queues it. A PR in a Stop and ask area waits for the user's answer. Resolve open review threads first if the ruleset requires it. Linear closes the parent spec itself once its last ticket is Done (team setting, on since 2026-10-20; not checked: not yet seen to fire), so the merge of the last ticket's PR closes the spec with no step here.
- **screenshot**: the one home for when agents use `playwright-cli`, a design and verification tool; tests stay at the seams in `CLAUDE.md` § Tests (Petter decided against a browser test seam, 2026-10-17), so a `playwright-cli` run never becomes a test. Start `make up` (core call page) or `make portal-up` (Portal) in the background (`make seed` first if the page needs data; the URLs are in `CLAUDE.md` § Commands), then use it for:
  - **before and after** screenshots while iterating on UI, at the widths the change can reach (390px phone, 1280px desktop; a change scoped to one breakpoint needs only that width)
  - driving a Portal flow end to end (login, settings, Modules) to see it work
  - checking widths and layout: no horizontal scroll at 390px, nothing clipped at 1280px
  - reading console errors and failed network requests while developing

  Save any login state only as `.playwright-cli/<name>.json`.

## Tickets and resuming

A flow's state lives in the tracker (`docs/agents/issue-tracker.md`) and git, never in the session. Tracker not reachable → stop.

- **`/next-step <issue-id>`**: work on that issue only. Read it, its comments, parent, sub-issues and blockers, then:
  - a spec (it has sub-issues) → list its open tickets with their blockers and ask which
  - a ticket with a parent spec → Feature, at the per-ticket step
  - `ready-for-agent` with no parent → Small change from implement, or Bug if it's labelled a bug (`docs/agents/triage-labels.md`)
  - `needs-triage` or `needs-info` → Incoming issue
  - `ready-for-human` → say it's marked for a human; don't build it
  - an open blocker → ask: proceed anyway, or the blocker first? A blocker in review counts as done only if its commits are on the current branch.
- **Bare `/next-step` in a fresh session**: find an issue id in the branch name and recent commits, list the parent spec's open tickets with their blockers, suggest an order and ask which. Never start one unasked.
- **Status**: when implement starts, assign yourself and move the issue to in progress; after its PR opens, to in review, if the tracker has those states. Merging the PR that names a ticket closes it.
- Each ticket ships as its own PR; the spec is done when its last ticket's PR merges.

## Pick a flow

| Situation | Flow |
|---|---|
| New feature or behaviour needing more than one session | Feature |
| A change that fits one session | Small change |
| Something broken | Bug |
| A raw tracker issue you didn't write | Incoming issue |
| A new page or screen | New view |
| A new part inside an existing page | New component |
| Spacing, type, colour, motion or copy | Visual tweak |
| Reviewing an existing page or surface as a whole | Design review |
| Tidying structure or finding what to delete | Code health |
| Changing a guard, baseline, CI workflow or ruleset | Guardrail change |
| Too big or foggy to plan in one session | Huge effort |
| Mid-merge or mid-rebase; a question to research; editing a skill, `CLAUDE.md` or a rule file | One-skill flows |

The UI flows (New view, New component, Visual tweak) apply only to repos with a UI.

## Flows

### Feature

```
- [ ] grill-with-docs ⏸
- [ ] research, only for an unverified external fact (an API, a third-party behaviour); wait for its file before the grilling closes
- [ ] to-spec (seam check ⏸)
- [ ] to-tickets ⏸
- [ ] per ticket: /clear, /next-step <issue-id> → branch → ticket → implement → review → commit → skeptic → pr → merge → in review
```

### Small change

```
- [ ] grill-with-docs ⏸ (skip when the ask is already precise)
- [ ] branch → ticket → implement → review, in this session
- [ ] commit → skeptic → pr → merge
```

### Bug

```
- [ ] branch → ticket
- [ ] diagnosing-bugs: one command that goes red on this bug, before any theory
- [ ] tdd: regression test at the seam the bug shows through (CLAUDE.md § Tests)
- [ ] fix → full suite green
- [ ] guardrail-from-incident, when the mechanism can recur; otherwise say in one line why not
- [ ] review → commit → skeptic → pr → merge
```

No seam to pin the bug to → stop and propose Code health instead of patching around it.

### Incoming issue

```
- [ ] triage ⏸ → ready-for-agent
- [ ] /clear, /next-step <issue-id>
```

Triage only issues you didn't create; `to-tickets` output is already agent-ready.

### New view

Impeccable's full sequence: shape, then new-work for a whole surface in the established world, through its finish.

```
- [ ] branch
- [ ] grill-with-docs ⏸: what the page shows, and why
- [ ] impeccable shape ⏸: its interview, then the brief you confirm
- [ ] impeccable new-work §1-5 ⏸: the dealt structures; you lock one on the decision page
- [ ] tdd at the rendering seam (CLAUDE.md § Tests): what the page renders (the data, not the look)
- [ ] impeccable new-work §6: build it
- [ ] impeccable new-work §7: screenshot round (screenshot step), finish reviewer, documenter
- [ ] review → commit → pr → merge
```

In a cloud session you can't open a page served in the container: present the decision page's choices in chat.

### New component

```
- [ ] branch
- [ ] impeccable shape ⏸ (skip for a variant of an existing part)
- [ ] tdd at the rendering seam, if it changes what renders
- [ ] impeccable: build it inside the existing surface (new-work "Extend an existing surface")
- [ ] impeccable audit → impeccable polish
- [ ] screenshot
- [ ] review → commit
```

### Visual tweak

```
- [ ] branch
- [ ] screenshot: "before"
- [ ] the one impeccable command that fits (layout, typeset, colorize, quieter, bolder, clarify, animate…); its questions ⏸
- [ ] screenshot: "after"; show both
- [ ] commit
```

No tickets, and no new test unless the rendered content changes.

### Design review

Impeccable's Evaluate commands judge a surface that exists, then one fix command per finding, and a ponytail-review reads the result, so a design that grew by patches gets one look as a whole. The ship-or-iterate comes last, so the go covers the page that merges.

```
- [ ] impeccable critique <surface> ⏸: its two isolated assessments, its report, its closing question
- [ ] impeccable audit <surface>: the scored technical report; it fixes nothing
- [ ] pick ⏸: the findings to fix, in order; none picked ends the review here, with no branch or PR
- [ ] branch → ticket
- [ ] screenshot: "before"
- [ ] per finding, the one command that fits: too much → distill · unclear words → clarify · real data and errors → harden · spacing, type, colour → layout, typeset, colorize · phone → adapt · loud or flat → quieter, bolder
- [ ] impeccable polish
- [ ] ponytail-review over the whole design the work touched, the page and the code behind it, not only the diff
- [ ] review
- [ ] screenshot: "after" at 390px and 1280px, once both reviews' fixes are in; show both, ship or iterate ⏸ (iterate → back to the fix commands)
- [ ] commit → pr → merge
```

### Code health

```
- [ ] improve-codebase-architecture (structure), ponytail-audit (what to delete), guardrail-from-incident (a defect pattern across the codebase), add-baseline (a rule that keeps being broken) or claim-sweep (agent docs that no longer match the code)
- [ ] pick one ⏸
- [ ] a deepening pick is grilled inside improve-codebase-architecture itself → to-spec (Feature) or branch → implement (Small change); a deletion → Small change
```

### Guardrail change

```
- [ ] branch
- [ ] add-baseline (a new guard), or the edit to a guard, CI workflow or ruleset
- [ ] a baseline only shrinks; a raise gets a DECISIONS.md line with the reason ⏸
- [ ] review → commit → pr → merge (code-owner review: not enforced, solo maintainer, see .github/CODEOWNERS)
```

### Huge effort

```
- [ ] wayfinder ⏸: resolve the map's decision tickets one at a time
- [ ] map clear: read the map issue and its done tickets into the session (to-spec works from the conversation)
- [ ] Feature, from to-spec
```

Never go from the map straight to implement unless the effort turned out small. `/prototype` isn't installed: build a `wayfinder:prototype` ticket's throwaway by hand on a `prototype/<name>` branch.

### One-skill flows

- Mid-merge or mid-rebase → no skill (upstream dropped `resolving-merge-conflicts`): resolve each conflict by intent, never `--abort`, run `make check`, then finish the merge or rebase.
- A question to answer from primary sources → `research`; where the file goes is in CLAUDE.md § Workflow.
- Writing or editing a skill, `CLAUDE.md`, a `.claude/rules/` file or another agent doc → `writing-for-agents`, keeping each rule in one home (`CLAUDE.md` § Rules); vendored skills are never edited (CLAUDE.md § Where the skills come from).

## Between steps

- Keep a Feature flow up to `to-tickets` in one unbroken session, so the grilling, spec and tickets share the same reasoning. Each ticket's implement then starts fresh after `/clear`.
- Near the smart zone (about 150k tokens) before that, `/compact` at the nearest phase boundary, never mid-step.
- At a phase boundary the first that fits wins: **continue** (the next step needs this context verbatim and there's room) → **`/clear`** (nothing here matters next) → **`/handoff`** (a new directory, harness or colleague, or forking a side task) → **subagent** (runs without steering, e.g. a review) → **`/compact`** with an instruction on what to keep.
- `/wait-what` whenever a message didn't land.

## Guide the user on ponytail

Ponytail's one quirk: **before a `/clear`**, if the session's ponytail level isn't the default (the `PONYTAIL MODE ACTIVE — level:` line), the level resets to the default (`/compact` keeps it). Add to the instruction: "then `/ponytail <level>` again, or `/ponytail default <level>` to keep it for every session".

## All skills

- **Planning**: `grill-with-docs` (interview that records terms in `GLOSSARY.md` and ADRs in `docs/adr/`), `grilling` (the bare interview), `to-spec` (spec as a tracker issue), `to-tickets` (tracer-bullet tickets with blocking edges), `wayfinder` (map of decision tickets), `triage` (raw issues to agent-ready ones).
- **Building**: `implement` (per ticket, test-first, closes with review), `tdd` (red-green at the agreed seams), `code-review` (Standards and Spec axes against a fixed point), `skeptic-pass` (independent agents try to refute a frozen head), `pr` (the PR body).
- **Debugging**: `diagnosing-bugs` (feedback loop first, then a regression test), `guardrail-from-incident` (every sibling of a fixed bug, and a guard for the whole class).
- **UI**: `impeccable` (the design workflow, briefed by `PRODUCT.md` from `impeccable init` and `DESIGN.md` from `impeccable document` or new-work; `live` is local-only), `playwright-cli` (when to use it: the screenshot step above; not a test seam).
- **Code health**: `improve-codebase-architecture` (deepening opportunities), `codebase-design` (deep-module vocabulary), `domain-modeling` (sharpen a `GLOSSARY.md` term or record an ADR), `add-baseline` (adopt a strict rule with a baseline that only shrinks), `claim-sweep` (test agent docs' claims against the code), `ponytail-review` (over-engineering in a diff), `ponytail-audit` (in the whole repo), `ponytail-debt` (every `shortcut:` and older `ponytail:` comment), `ponytail`, `ponytail-help`, `ponytail-gain` (the always-on lazy mode, its command card, its benchmarks).
- **Research and writing**: `research` (cited Markdown from primary sources), `writing-for-agents` (skills, `CLAUDE.md`, agent docs).
- **Session**: `wait-what` (re-explain the last message), `handoff` (a handoff document for another agent or directory).
- **Setup**: `setup-matt-pocock-skills` (tracker, triage labels, doc layout into `docs/agents/`; run once when adopting this template).
