# The one command interface: CI, hooks, loops and agents call only these targets.
# Fill each body for this repo's stack (docs/agents/recipes/). An unfilled target fails,
# so CI never passes while checking nothing. A target that does not apply here becomes
# `@echo "n/a: <reason>"`, which records the choice.
.DEFAULT_GOAL := help
.PHONY: help setup up down portal-up portal-down self-host self-host-down eval eval-audio seed merge-check check lint typecheck test test-db guards generate generate-check build

unconfigured = @echo "make $(1): not configured yet. Fill in this target for your stack (docs/agents/recipes/)." >&2; exit 1

help: ## List the targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install dependencies and tools
	uv sync --frozen
	npm ci --ignore-scripts

up: ## Start the app with its services (agents run it in the background)
	uv run python -m voice.serve

down: ## Stop what `make up` started
	pkill -f "[p]ython -m voice.serve" || true

portal := DJANGO_SETTINGS_MODULE=portal.settings uv run --env-file .env.example --env-file .env python -m django

portal-up: ## Start the Portal at http://localhost:8000 with its Postgres and migrations applied (agents run it in the background)
	scripts/ensure-docker.sh
	[ -f .env ] || touch .env
	docker compose up -d --wait
	$(portal) migrate
	$(portal) runserver 0.0.0.0:8000

portal-down: ## Stop the Portal's Postgres (its data stays in a Docker volume)
	docker compose down

self-host: ## Start the core, the Portal and Postgres together on this machine (README § Self-host)
	scripts/ensure-docker.sh
	docker compose -f compose.self-host.yml up --build

self-host-down: ## Stop what `make self-host` started (the Portal's data stays in a Docker volume)
	docker compose -f compose.self-host.yml down

eval: ## PAID, ask Petter first (local, or the manual Evals workflow): run the Scenarios (ONLY=<id> for one); a full pass writes eval-receipt.json
	uv run python -m tests.evals.run $(ONLY)
	$(if $(ONLY),,node scripts/eval-receipt.js write)

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
	uv run pytest -m "not db"

test-db: ## Tests against the real data stores (the target starts and stops them)
	scripts/ensure-docker.sh
	docker compose -f compose.test.yml -p voice-test up -d --wait
	DATABASE_URL=postgres://postgres:test@127.0.0.1:55432/portal_test uv run pytest -m db; status=$$?; \
	  docker compose -f compose.test.yml -p voice-test down -v; exit $$status

guards: ## Guard scripts, self-tests first (scripts/checks/README.md)
	node scripts/checks/run.js

tailwind := npx --no-install @tailwindcss/cli -i portal/static/portal/tailwind.css --minify

generate: ## Regenerate every generated file (the Portal's migrations and stylesheet)
	ENVIRONMENT=local DEBUG=1 DJANGO_SETTINGS_MODULE=portal.settings uv run python -m django makemigrations
	$(tailwind) -o portal/static/portal/portal.css

generate-check: ## Fail when a generated file is stale, printing the command that fixes it
	ENVIRONMENT=local DEBUG=1 DJANGO_SETTINGS_MODULE=portal.settings uv run python -m django makemigrations --check --dry-run || { echo "models changed without a migration: run make generate" >&2; exit 1; }
	css=$$(mktemp) && $(tailwind) -o "$$css" && cmp -s "$$css" portal/static/portal/portal.css || { echo "portal.css is stale: run make generate" >&2; exit 1; }

build: ## Build every configuration this repo ships
	docker build -t voice .
	docker build --target portal -t voice-portal .

merge-check: ## Is this branch low-risk enough for an agent to turn on auto-merge? (scripts/low-risk-paths.json)
	node scripts/merge-check.js

check: lint typecheck test test-db guards generate-check build ## Everything CI runs
