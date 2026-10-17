# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Voice is the voice core: it connects a phone or browser call to a live AI voice model and runs the call. `portal/` is the Portal, the Django web app where a Business logs in (ADR 0002). Glossary: `CONTEXT.md`. Decisions: `docs/adr/` and `DECISIONS.md`.

## Hard rules

1. **The data store enforces what must never break about stored data**: a constraint, trigger, schema validation or permission, with no exception for admin roles. A rule with no store behind it gets a type or a guard. A cache or queue never holds such a rule.
2. **One way in per dangerous action** (deletion, permission changes, anything sent outside): one function or endpoint, and a guard or constraint refuses every other path.
3. **Fail closed**: when a check that decides access or correctness can't run, refuse and say why. Failing open needs a visible trace.
4. **Closed sets are exhaustive**: a new value fails the typecheck, or a test that enumerates the set, until every place handles it.
5. **A fact lives in one place**: a second copy is generated from it (`make generate`), or a parity test reads both and names the side to edit.
6. **Secrets stay out of the repo**: none in code, committed settings or `.env` files (only `.env.example`), and cloud environments hold only low-risk, tightly scoped tokens. Enforced by the `no-committed-secrets` guard.
7. **Seen to hold before claimed**: a setting, check or doc line protects nothing until it has been seen to hold once (a required reviewer that actually pauses a run); until then say "not checked".

Rules 1 to 5 and 7 are soft: no check yet. Promote a soft rule to a check once it has been skipped.

## Stop and ask

Stop and ask; do not guess. How agents reach tickets, logs, errors and metrics, and what they may not touch there: `docs/agents/agent-access.md`. Petter decides each of these:

- **Spend and billing**: raising a spend cap; adding eval runs, scenarios or call length; changing an API key, project or billing tier; every `make eval` and `make eval-audio` run (both spend Gemini credit, so ask before each; never on push or PR. `make eval` also runs from the manual Evals workflow, where Petter's Approve click is the go).
- **Legal wording**: the AI disclosure line, caller notice text, anything else that informs callers.
- **Real calls and people**: calling a number we don't own, recording a real person, putting personal data anywhere.
- **Vendors and deploys**: adding a vendor or sub-processor (model, carrier, hosting), a new app, host or deploy setting. A merge to the default branch is the routine deploy and needs no go.

None of these is ticket-only: the PR is opened and waits for the answer, unmerged.

## Commands

`make help` lists the targets, and `make check` runs what CI runs. CI, hooks and loops call only make targets, so a target's body is the one place a command lives.

`make up` serves the browser call page at http://localhost:7860 (run it in the background; it needs `GOOGLE_API_KEY` and `CORE_SECRET` in `.env`, a call opens only from a link the Portal made (`make portal-up`, then the test call button), and every call spends Gemini credit). `make portal-up` serves the Portal at http://localhost:8000 with its own Postgres in Docker (invite a Business: `DJANGO_SETTINGS_MODULE=portal.settings python -m django invite_business <email> <name> --target local`, see `.claude/rules/prod-scripts.md`). `make self-host` starts the core, the Portal and Postgres together for someone running their own copy (README § Self-host). `make seed` prints n/a: no demo data yet. `make eval` (`ONLY=<id>` for one Scenario) plays the Scenarios against the real agent under the caps in `tests/evals/caps.json`; a full pass writes `eval-receipt.json`, and the `eval-required` guard fails a change to the prompt, the Business's facts or the Pipecat pin (`scripts/eval-required.json`) without a matching receipt; `make eval-audio` renders the Caller audio once.

## Architecture

Layers, dependency direction and the one interface per cross-cutting concern: `ARCHITECTURE.md`, enforced by the `layers` guard from `scripts/checks/layers.json`.

## Tests

Three seams:

- **Eval channel** (`make eval`, paid; on Petter's PC or the manual Evals workflow, never automatic): a whole Scenario against the real agent, through Pipecat's eval transport with stored Caller audio. Aims at the prompt, the Business's facts, the disclosure and the barge-in settings; ten Scenarios, one per behaviour (the noise call and its speech twin read the barge-in events; `module_hours` has the agent use the example Module's Action). `tests/evals/run.py`.
- **Portal** (`make test-db`, free, in CI): the Portal through Django's test client against a real Postgres, in `tests/portal/`: login, invite, password reset, and each rule the database must refuse. `tests/portal/test_routes.py` (no database, runs under `make test`) sweeps every page for a login gate.
- **Checks** (`make test`, free, in CI): each check is a pure function on a stored synthetic call record, with a passing and a failing example. `tests/test_checks.py`, which also reads stored barge-in event records (`tests/calls/barge_in_*.json`); the spend rule, cost sum, login rule, web audio converter, price catalogue (`tests/test_cost_catalogue.py`, a real local server standing in for Google and a stored sample reply), settings port (`tests/test_settings_port.py`, a real local server standing in for the Portal) and Modules port (`tests/test_modules.py`, the example Module and dead sockets standing in for Modules) sit beside them.

Don't mock our own modules or add tests at other seams. A new seam needs this section updated through `/grill-with-docs` first.

A change to the eval checks or Scenarios gets a second read before Petter adds the `evals-approved` label: a session that did not write it reads it and reports (a `skeptic-pass`, or a note in `docs/research/` or the PR).

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
- `.claude/rules/api.md` (Portal pages), `.claude/rules/data.md` (Portal models and migrations), `.claude/rules/prod-scripts.md` (Portal management commands).

## Workflow

- Branches: `<linear-id>-<slug>`, or `<slug>` without an issue.
- Research goes in `docs/research/<topic>.md`; prefer the official docs and source code of the tools we use (`pyproject.toml`, `package.json`, Dokploy, browser and WebRTC specs) over other write-ups, and cite each with its link and the date read.
- No Claude attribution in PRs or commits: no "Generated with Claude Code" footer, no claude.ai session link, no `Co-Authored-By` or `Claude-Session` trailers. The GitHub tool appends that footer and a session link to every PR body it opens, so re-read the body after opening a PR and delete them (keep the "Requested by" block), and never add them to a PR comment. The `no-claude-identity` guard fails a PR whose commits are authored by Claude or carry those, or whose title or body does, and a PreToolUse hook (`scripts/claude-attribution-gate.js`) refuses a GitHub tool write whose text does, comments included; sessions commit as Petter (`scripts/git-identity.sh`, run at session start), because GitHub's squash merge adds a `Co-authored-by` line for every other commit author. When merging, pass your own title and message.
- Every merge to the default branch auto-deploys to Dokploy (project `Voice`, app `app`, from `Dockerfile`); the Portal is app `portal`, from `Dockerfile.portal`, with Postgres `portal-db`.

- Shared agent setup lives in the repo: settings, hooks, skills, rules and plans. A method the team relies on gets committed as one of those; personal settings stay in `.claude/settings.local.json`.
- Merging: once the PR is ready (not draft) and no § Stop and ask area applies, turn on auto-merge (`gh pr merge --auto --squash`, or the GitHub MCP `enable_pr_auto_merge`) right after opening it; GitHub merges once `ci-summary` passes, so end the turn instead of waiting on CI; if checks already passed, GitHub refuses auto-merge, so merge directly (squash). No "merge" word from the user is needed. A PR in a Stop and ask area waits for that answer; the `evals-approved` label and the Approve on the Evals run are separate gates that CI and GitHub enforce.
- Tickets: an edit outside the `no_ticket` paths of `scripts/low-risk-paths.json` needs a ready Linear ticket (label `ready-for-agent`) that `/next-step` records; a hook is meant to deny the edit (not checked: not yet seen to deny in a real session), a pre-commit hook (`scripts/git-hooks`, installed at session start) refuses a commit of files written any other way, and the `ticket-required` guard fails a PR that closes no ready ticket (`scripts/ticket-check.js`).
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

Linear, team `VOI`, project `Voice`, through `linearis`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context. See `docs/agents/domain.md`.
