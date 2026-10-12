# Decisions

One line per non-obvious choice, newest at the bottom: `[YYYY-MM-DD] <decision>: <why>`, at most 300 characters. A parked question: `[YYYY-MM-DD] ESCALATED: <question> -> <who>`, then `[YYYY-MM-DD] RESOLVED <escalated date>: <answer>`. What goes here and what becomes an ADR: `CLAUDE.md` § Decisions.

[2026-10-12] Python 3.13 for the whole core, one language throughout: Pipecat and Google's SDK are Python-first; a TypeScript relay was rejected as a second language.
[2026-10-12] Pipecat as the runtime, judged at the M0 gate; the fallback if it fails is decided then, not now.
[2026-10-12] Tooling is uv, ruff, pyright and pytest: uv was already in use; pyright over mypy for stricter, faster checks on agent-written code.
[2026-10-12] Pipecat's transports are the channel seam and its LLM services the model seam, with no wrappers of our own; only records (config, tools, call and usage records) stay ours and vendor-neutral.
[2026-10-12] Kept the unused rule skeletons (api, data, prod-scripts) unfilled instead of deleting them: they never load until their globs are filled, and refilling beats recopying.
[2026-10-12] Code goes in a flat voice/ package with uv in app mode (package = false): nothing is published, so no src/ layout or build backend.
[2026-10-12] pyright runs in strict mode from day one: an empty package has nothing to baseline, and strict is cheapest to adopt before code exists.
[2026-10-12] make test accepts pytest's "no tests collected" (exit 5) until the first test lands; marked ponytail in the Makefile so it gets dropped then.
[2026-10-12] ruff skips .claude/, docs/ and the guard fixtures: vendored skills are never edited, template docs carry Django examples, and fixtures break rules on purpose.
[2026-10-12] The evals/ fence is a guard that fails any PR touching evals/ unless Petter added the evals-approved label; it is built with the eval MVP, together with the folder it protects.
[2026-10-12] Kept the template's low-risk paths (docs/** and DECISIONS.md, never docs/agents/**); evals/** and agent prompts join "never" when they exist.
[2026-10-12] Accepted that the cloud Dokploy token reaches every Dokploy project, not just Voice: agents keep to read-only on Voice by rule (docs/agents/agent-access.md); a gap against hard rule 6 until a narrower token exists.
[2026-10-12] Left Dokploy auto-deploy on for main although every deploy fails until a Dockerfile exists: failed deploys are harmless for now.
[2026-10-12] Left write-domain-skill and product-agents.md in docs/agents/optional/: the domain skill waits for the compliance work, the product-agents rule for the first tool code.
[2026-10-12] Going public through a fresh repo with one squashed commit, not a force-push: GitHub keeps every old PR and its commits reachable, so only a new repo drops the demo history; the old one stays private as Voice-archive.
[2026-10-12] Vendored skills ship with their sources' licence and notice files in .claude/vendor-licenses/, written by vendor-skills.sh: MIT and Apache-2.0 ask for them once the repo is public.
[2026-10-12] vendor-skills.sh strips disable-model-invocation from the flow skills next-step runs (grill-with-docs, to-spec, to-tickets, implement and others), so the agent runs them; next-step's gates replace typing them as the human stop. wait-what and setup stay user-only.
[2026-10-12] Dropped the push and open-PR gates from next-step: the merge is the one hard stop that matters, and a PR is cheap to close.
