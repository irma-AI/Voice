# The Portal is a Django app next to the core; they are separate services

Businesses configure their Modules and settings in a Portal (Django, Tailwind, htmx, Postgres) that lives in this repo and ships in both the open code and the hosted service. The core runs as its own service and asks the Portal for a Business's settings when a call starts, so a Portal restart or a heavy page never cuts a live call. Postgres is the only data store, hosted or self-hosted, so there is one path to test and the database enforces what must never break.

## Considered Options

- Calls inside the Django app: one thing to deploy, but live calls would share a process with web pages.
- Postgres for hosted and a single file for self-hosters: easier to start, two setups to keep working.
- A separate Portal repo: cleaner split, but rules, checks and the settings shape would be kept twice.
