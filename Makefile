# The one command interface: CI, hooks, loops and agents call only these targets.
# A target that does not apply here is `@echo "n/a: <reason>"`, which records the choice.
.DEFAULT_GOAL := help
.PHONY: help setup up down portal-up portal-down self-host self-host-down eval eval-audio voice-samples seed check lint typecheck test test-db guards workflow-lint archive-decisions linear-room generate generate-check build

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

voice-samples: ## PAID, local only, ask Petter first: one call per voice setup into eval-runs/voice-samples/ (SETUPS="A C" for some)
	uv run python -m scripts.render_voice_samples $(SETUPS)

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

linear-room: ## Archive the oldest closed Linear issues until there is room for ROOM (20) new ones: the free plan refuses new issues past 250 not archived. Run before creating issues
	node scripts/linear-room.js $(ARGS)

archive-decisions: ## Move DECISIONS.md lines older than KEEP_DAYS (7) into docs/decisions/<yyyy-mm>.md; open questions stay
	node scripts/archive-decisions.js

guards: ## Guard scripts, self-tests first (scripts/checks/README.md)
	node scripts/checks/run.js

# zizmor runs online audits when GH_TOKEN is set (CI), offline audits otherwise.
workflow-lint: ## Lint the GitHub workflows, actions and Dependabot config for security holes (zizmor)
	uvx zizmor@1.30.1 --min-severity high .github/workflows .github/actions .github/dependabot.yml

tailwind := npx --no-install @tailwindcss/cli -i portal/static/portal/tailwind.css --minify

# The hash the Call button tag names its script by (subresource integrity, VOI-135); an edit to the file breaks every pasted tag, so a changed script is a new version.
call_button_sri = sha384-$$(openssl dgst -sha384 -binary portal/static/portal/call-button.v$(1).js | openssl base64 -A)

generate: ## Regenerate every generated file (the Portal's migrations, stylesheet and Call button hash)
	ENVIRONMENT=local DEBUG=1 DJANGO_SETTINGS_MODULE=portal.settings uv run python -m django makemigrations
	$(tailwind) -o portal/static/portal/portal.css
	echo "$(call call_button_sri,1)" > portal/call-button.v1.integrity
	echo "$(call call_button_sri,2)" > portal/call-button.v2.integrity

generate-check: ## Fail when a generated file is stale, printing the command that fixes it
	ENVIRONMENT=local DEBUG=1 DJANGO_SETTINGS_MODULE=portal.settings uv run python -m django makemigrations --check --dry-run || { echo "models changed without a migration: run make generate" >&2; exit 1; }
	css=$$(mktemp) && $(tailwind) -o "$$css" && cmp -s "$$css" portal/static/portal/portal.css || { echo "portal.css is stale: run make generate" >&2; exit 1; }
	for v in 1 2; do [ "$$(cat portal/call-button.v$$v.integrity)" = "sha384-$$(openssl dgst -sha384 -binary portal/static/portal/call-button.v$$v.js | openssl base64 -A)" ] || { echo "call-button.v$$v.integrity is stale: run make generate (pasted tags name the old hash, so a changed script belongs in a new version)" >&2; exit 1; }; done

build: ## Build every configuration this repo ships
	docker build -t voice .
	docker build -f Dockerfile.portal -t voice-portal .

check: lint typecheck test test-db guards workflow-lint generate-check build ## Everything CI runs
