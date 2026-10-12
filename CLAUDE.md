# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Voice is the voice core: it connects a phone or browser call to a live AI voice model and runs the call. Glossary: `CONTEXT.md`. Decisions: `docs/adr/` and `DECISIONS.md`.

## Hard rules

1. **The data store enforces what must never break about stored data**: a constraint, trigger, schema validation or permission, with no exception for admin roles. A rule with no store behind it gets a type or a guard. A cache or queue never holds such a rule.
2. **One way in per dangerous action** (deletion, permission changes, anything sent outside): one function or endpoint, and a guard or constraint refuses every other path.
3. **Fail closed**: when a check that decides access or correctness can't run, refuse and say why. Failing open needs a visible trace.
4. **Closed sets are exhaustive**: a new value fails the typecheck, or a test that enumerates the set, until every place handles it.
5. **A fact lives in one place**: a second copy is generated from it (`make generate`), or a parity test reads both and names the side to edit.
6. **Secrets stay out of the repo**: none in code, committed settings or `.env` files (only `.env.example`), and cloud environments hold only low-risk, tightly scoped tokens. Enforced by the `no-committed-secrets` guard.

Rules 1 to 5 are soft: no check yet. Promote a soft rule to a check once it has been skipped.

## Stop and ask

Stop and ask; do not guess. How agents reach tickets, logs, errors and metrics, and what they may not touch there: `docs/agents/agent-access.md`. Petter decides each of these:

- **Spend and billing**: raising a spend cap; adding eval runs, scenarios or call length; changing an API key, project or billing tier.
- **Legal wording**: the AI disclosure line, caller notice text, anything else that informs callers.
- **Real calls and people**: calling a number we don't own, recording a real person, putting personal data anywhere.
- **Vendors and deploys**: adding a vendor or sub-processor (model, carrier, hosting), deploying anything.

None of these is ticket-only: the PR is opened and waits for the answer.

## Commands

`make help` lists the targets, and `make check` runs what CI runs. CI, hooks and loops call only make targets, so a target's body is the one place a command lives.

<!-- Commands make doesn't cover, from the repo root: how to run one test while iterating. -->
`make up` serves the browser call page at http://localhost:7860 (run it in the background; it needs `GOOGLE_API_KEY` in `.env`, and every call spends Gemini credit). `make seed` prints n/a: no demo data yet.

## Architecture

Layers, dependency direction and the one interface per cross-cutting concern: `ARCHITECTURE.md`, enforced by the `layers` guard once `scripts/checks/layers.json` exists.

<!-- The big picture an agent can't get from one file: the main modules, how data flows between them, where state lives. -->

## Tests

<!-- The seams tests go through (e.g. "HTTP request → rendered response"), one line each with its test file. /tdd, /to-spec and /next-step's Bug flow test only at these; name which seam covers rendered output. -->

Don't mock our own modules or add tests at other seams. A new seam needs this section updated through `/grill-with-docs` first.

## Fix from first principles

A reported problem usually arrives with a proposed fix. Treat that fix as evidence about the pain, not the plan: before implementing, answer the three questions under First principles in `.github/pull_request_template.md`. The answers go in the PR body.

## Definition of Done

A change is done when all of these hold; iterate until they do:

1. `make check` passes.
2. New or changed behaviour has tests at the seams in § Tests.
3. Every rule, guard and agent doc the change made stale is updated in the same change.
4. Each non-obvious choice has its line in `DECISIONS.md` (§ Decisions).
5. Switched on: confirmed live in its target environment (migration applied, scheduled job seen firing, script run, feature reachable), or the PR's Not live yet section names what isn't and who turns it on.

## Decisions

- **ADR** (`docs/adr/`, via `/domain-modeling`): a choice that is hard to reverse, surprising without context and a real trade-off.
- **`DECISIONS.md` line** (format in its header; the `decisions-format` guard checks it) for every other non-obvious choice: picked A over B, declined a dependency or a review finding, stopped because a rule forbade something, diverged from the issue's proposal. The detail goes in the PR body.

Grep both before reopening a past choice. A question parked for a person gets an `ESCALATED` line, and a `RESOLVED` line once answered; `grep ESCALATED DECISIONS.md` shows what is waiting.

## Rules

This file holds what every session needs; keep it under about 120 lines. A rule for part of the tree lives in `.claude/rules/<area>.md`, loaded when a file matching its `paths:` header is touched. Each rule has one home, here or in one rule file; `AGENTS.md` and other docs link to it. A rule that must always hold gets a guard (`add-baseline` skill).

- `.claude/rules/security.md`: secrets and personal data (Python files, `.env.example`).
- `.claude/rules/tests.md`: test layers (the tests folder and `test_*.py` files).
- `.claude/rules/api.md`, `.claude/rules/data.md`, `.claude/rules/prod-scripts.md`: not active yet; fill in their globs when the admin API, a data store or ops scripts arrive.

## Workflow

- Branches: `<linear-id>-<slug>`, or `<slug>` without an issue.
- Research goes in `docs/research/<topic>.md`.
- Every merge to the default branch auto-deploys to Dokploy (project `Voice`, app `app`, from `Dockerfile`); it fails until a Dockerfile exists.

- Shared agent setup lives in the repo: settings, hooks, skills, rules and plans. A method the team relies on gets committed as one of those; personal settings stay in `.claude/settings.local.json`.
- Merging: turn on auto-merge only when `make merge-check` says `LOW-RISK`; any other merge waits for the user's go-ahead for that PR. Nothing enforces this, since agents act as the user on GitHub.
- Scheduled agents (loops) follow `.claude/loops.md`: they propose, and merge only under the rule above. When its registry has rows, run its § Checking loops at session start.
- Guardrail work outranks ponytail: a test, check, rule update or `DECISIONS.md` line that the Definition of Done, a rule or a guard requires is part of the change. Ponytail decides how much product code to write.
- Mark deliberate shortcuts with a `ponytail:` comment naming the limit and the upgrade path.
- When a skill (e.g. `/tdd`'s seam check, the grilling skills) or the org's rules say to ask first, ask: that outranks ponytail's "never stall on an answer you can default".
- Ponytail's "one runnable check" here is one test at one of the seams (§ Tests), run by the repo's test runner: no `demo()`, `__main__` or stray test files.
- Output a loaded skill or `/next-step` flow asks for (a checklist, a ranked list, a command and its output) counts as explicitly requested, so ponytail's three-line limit doesn't apply to it.
- A design-it-twice brief (`codebase-design`) outranks ponytail for that subagent: its job is to explore a different shape.

## Where the skills come from

Everything under `.claude/skills/`, `.claude/vendor-licenses/`, `.claude/agents/impeccable-*` and `.claude/hooks/ponytail-*` is vendored by `scripts/vendor-skills.sh` (see `skills-lock.json`); never edit those files, since a re-run replaces them. The hand-written skills are the folders `skills-lock.json` doesn't list, among them `next-step` (model-invoked on purpose so the agent can pick a flow itself); a re-vendor leaves them alone.

<!-- UI repos: "UI work follows DESIGN.md and PRODUCT.md", once Impeccable has written them. -->

## Agent skills

### Issue tracker

Linear, team `PET`, project `Voice`, through `linearis`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context. See `docs/agents/domain.md`.
