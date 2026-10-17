# The Portal is a Django app next to the core; they are separate services

Businesses configure their Modules and settings in a Portal (Django, Tailwind, htmx, Postgres) that lives in this repo and ships in both the open code and the hosted service. The core runs as its own service and asks the Portal for a Business's settings when a call starts, so a Portal restart or a heavy page never cuts a live call. Postgres is the only data store, hosted or self-hosted, so there is one path to test and the database enforces what must never break.

## Considered Options

- Calls inside the Django app: one thing to deploy, but live calls would share a process with web pages.
- Postgres for hosted and a single file for self-hosters: easier to start, two setups to keep working.
- A separate Portal repo: cleaner split, but rules, checks and the settings shape would be kept twice.

## Update 2026-10-14: the core is a hub with ports, not tied to the Portal

The core runs on its own as a process, but does nothing useful alone: it is a hub with lines in, each a port with one interface, and adapters that plug into them. The Portal is one adapter (the Business's settings, later call records), Modules are another (Actions), and the web, eval and later phone Channels are others. Pipecat's transports and model services already serve as the Channel and model ports (`DECISIONS.md`, 2026-10-12); the core adds its own only for settings, Actions and call reports. A new line in is a new adapter behind an existing port, not a change to the call logic.

With no settings source configured the core starts, says so in the log and refuses calls with a spoken reason. A file source in the same shape (`contract/business-settings.schema.json`) is chosen explicitly for evals, whose Channel names no Business; the Portal serves only a call that names its Business. With a Portal configured but unreachable, the call is refused too: a fallback would serve another Business's facts, or one that was switched off. Reports back to the Portal never block a call. Modules depend on neither. MVP: one adapter per port, chosen by one setting, with no plugin registry.

## Update 2026-10-17: a Call record is logged before it is sent

The core writes each finished call's Call record (`contract/call-record.schema.json`) to its server log as one line, then sends it to the Portal in the background for up to a minute (VOI-42: the call is priced from Google's price catalogue first, in the same background step, so the log line carries the cost), and logs a give-up line if every try fails. This narrows "reports back to the Portal never block a call" above: they still never block or cut a call, but they are no longer fire-and-forget, because the log line is the copy that survives a Portal that stays down or a restart in the middle of the retries. Nothing re-sends from the log yet.
