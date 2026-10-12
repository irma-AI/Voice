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
[2026-10-12] The web channel uses Pipecat's prebuilt browser page over its SmallWebRTC transport, not our own page over a WebSocket as the opportunity file proposed: no frontend code, and WebRTC handles echo and jitter on a phone browser. Petter chose it 2026-10-12.
[2026-10-12] Pinned pipecat-ai to 1.12.0 exactly: the M0 gate judges one version, and its eval transport and Gemini 3.8 Live support both moved in recent releases.
[2026-10-12] ESCALATED: what `make up` serves, the Gemini and eval spend caps, the AI disclosure wording, and whether E0 is adopted as written -> Petter
[2026-10-12] Spend caps approved by Petter: $30/month on the Gemini test project in AI Studio (he sets it); eval runner caps 10 SEK per run, 30 per loop, 50 per day, read only from evals/caps.yaml, which only he edits.
[2026-10-12] AI disclosure line approved by Petter: "Du pratar med en AI-assistent." (English: "You're talking to an AI assistant."), the first sentence before any model speech.
[2026-10-12] E0 trimmed by Petter to "Lean 12": 12 audio scenarios with code checks on Pipecat's eval transport and the SEK caps; dropped the TTS back-check, per-run recordings, failure re-runs and experiments 4 and 6.
[2026-10-12] RESOLVED 2026-10-12: Pipecat's browser page; caps $30/month and 10/30/50 SEK; disclosure "Du pratar med en AI-assistent."; E0 as Lean 12.
[2026-10-12] The Business's facts are a plain key: value text file read into the system instruction, not YAML or a schema: one synthetic Business, read by the model only; a parser comes with the second Business or the first tool that needs fields.
[2026-10-12] The disclosure is asked of the model as its first sentence, not played as a pre-rendered clip: Petter approved the wording with this stopgap on 2026-10-12; the clip comes with the compliance work, and the eval checks it is said first meanwhile.
[2026-10-12] Kept Scenario in CONTEXT.md on the web call branch although the eval ticket uses it first: Petter settled it in the grilling, and the glossary records terms when they are settled.
[2026-10-12] Gemini Live gets language sv-SE in its speech config, not Pipecat's en-US default: callers speak Swedish by default; switching to English is left to the prompt.
[2026-10-12] Skeptic findings on PET-42 (DEBUG transcripts in logs, blank key, en-US speech config) were fixed without new tests: none sits at an agreed seam (eval channel, check unit tests); the eval channel covers language and disclosure once PET-43 lands.
