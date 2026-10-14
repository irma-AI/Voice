# The Portal is a Django app next to the core; they are separate services

Businesses configure their Modules and settings in a Portal (Django, Tailwind, htmx, Postgres) that lives in this repo and ships in both the open code and the hosted service. The core runs as its own service and asks the Portal for a Business's settings when a call starts, so a Portal restart or a heavy page never cuts a live call. Postgres is the only data store, hosted or self-hosted, so there is one path to test and the database enforces what must never break.

## Considered Options

- Calls inside the Django app: one thing to deploy, but live calls would share a process with web pages.
- Postgres for hosted and a single file for self-hosters: easier to start, two setups to keep working.
- A separate Portal repo: cleaner split, but rules, checks and the settings shape would be kept twice.

## Update 2026-10-14: the Portal is optional for the core

The core loads a Business's settings through one loader with two sources: the Portal's settings address, or a file in the same shape (`contract/business-settings.schema.json`). With no Portal address configured, the core runs standalone from the file and logs that it does. With an address configured and the Portal unreachable, the call is refused with a spoken reason: a fallback would serve another Business's facts, or a Business that was switched off. Reports back to the Portal, such as call records, never block a call. Modules depend on neither.
