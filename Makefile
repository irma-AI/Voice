# The one command interface: CI, hooks, loops and agents call only these targets.
# Fill each body for this repo's stack (docs/agents/recipes/). An unfilled target fails,
# so CI never passes while checking nothing. A target that does not apply here becomes
# `@echo "n/a: <reason>"`, which records the choice.
.DEFAULT_GOAL := help
.PHONY: help setup up down eval eval-audio seed merge-check check lint typecheck test test-db guards generate generate-check build

unconfigured = @echo "make $(1): not configured yet. Fill in this target for your stack (docs/agents/recipes/)." >&2; exit 1

help: ## List the targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install dependencies and tools
	uv sync --frozen

up: ## Start the app with its services (agents run it in the background)
	uv run python -m voice.web -t webrtc

down: ## Stop what `make up` started
	pkill -f "[p]ython -m voice.web" || true

eval: ## PAID, ask Petter first (local, or the manual Evals workflow): run the Scenarios (ONLY=<id> for one)
	uv run python -m tests.evals.run $(ONLY)

eval-audio: ## PAID, local only, ask Petter first: render the Caller audio under tests/evals/audio/
	uv run python -m tests.evals.render_audio

seed: ## Load demo data into the local app (never a copy of production)
	@echo "n/a: no demo data yet"

lint: ## Lint and format check
	uv run ruff check .
	uv run ruff format --check .

typecheck: ## Full typecheck, test files included
	uv run pyright

test: ## Unit and integration tests
	uv run pytest

test-db: ## Tests against the real data stores (the target starts and stops them)
	@echo "n/a: no data store yet"

guards: ## Guard scripts, self-tests first (scripts/checks/README.md)
	node scripts/checks/run.js

generate: ## Regenerate every generated file
	@echo "n/a: no generated files yet"

generate-check: ## Fail when a generated file is stale, printing the command that fixes it
	@echo "n/a: no generated files yet"

build: ## Build every configuration this repo ships
	@echo "n/a: no image yet; becomes docker build when the Dokploy step adds the Dockerfile"

merge-check: ## Is this branch low-risk enough for an agent to turn on auto-merge? (scripts/low-risk-paths.json)
	node scripts/merge-check.js

check: lint typecheck test test-db guards generate-check build ## Everything CI runs
