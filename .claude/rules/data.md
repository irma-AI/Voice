---
paths:
  - "portal/**/models.py"
  - "portal/**/migrations/*.py"
---

# Data model and migrations

The Portal's system of record is Postgres (`DATABASE_URL`), with no cache or queue beside it. Models are in `portal/<app>/models.py`; migrations are generated into `portal/<app>/migrations/` by `make generate`, and `make generate-check` fails when a model changed without one.

- **Schema changes are new migrations.** A shipped migration is never edited; a fix is the next migration.
- **A migration runs while the previous Portal copy still serves** (Dokploy's update order is start-first, VOI-121), so it must work for the previous code too: add a column or table in one change, drop or rename in a later one. No check yet.
- **The store enforces the rule** (`CLAUDE.md` § Hard rules 1) for every writer, scripts and workers included: a constraint, trigger, schema validation or permission in the migration that introduces it, whose error names the rule it enforces, and the allowed path where one exists ("use X instead"). Application code may check it too, for a friendlier error; the store is what refuses. A real exception is a named, logged path, not a bypass role. In Django: a `UniqueConstraint`, `CheckConstraint` or `OneToOneField`, never only a form or `clean()` check. A constraint's name states the rule (`business_calls_per_day_must_not_be_negative`) so the Postgres error does; a `OneToOneField` keeps Django's generated name.
- **A data-store rule ships with a real-store test** that makes the bad write and asserts the refusal (`.claude/rules/tests.md`). A migration that needs none says `db-test: skip <reason>`.
- **Caches and queues hold nothing that must survive a flush.** A value whose loss breaks a rule belongs in the system of record.

## Enforced by

- `db-test-required` guard (`scripts/checks/db-test-required.json`): a changed migration needs a change under `tests/portal/`, or `db-test: skip <reason>`.
- The refusals themselves: `tests/portal/test_accounts.py` (second Business on an account, duplicate or upper-case email, negative limit, empty name) and `tests/portal/test_business_settings.py` (no language or an unknown one, a setting longer than the contract allows) and `tests/portal/test_call_link.py` (a second Business with the same call link, a call link with a quote, space or angle bracket or under 22 characters, a negative daily budget).
- `tests/portal/test_theme.py`: a logo over 256 KB, one that is not a PNG, WebP or JPEG by its bytes (SVG, GIF, empty), a logo key that is not the logo's hash, and an accent that is not `#` and six lower-case hex digits.
- `tests/portal/test_website_domain.py`: a stored website domain that is upper case, has a scheme, path, port, space or header line, or is not a plain domain.
- `tests/portal/test_modules_page.py`: a Module with no address or two, an address holding a user, password, query or key, a blank or repeated name, too many arguments, or an eleventh per Business.
- `tests/portal/test_access_tokens.py`: an Access token with a scope other than read or full, a hash that is not a lower-case SHA-256 (the secret itself), a repeated hash or a blank label, a change to anything but `last_used_at` and a first `revoked_at`, and a revoked time that is not the database's clock or is set twice.
- `tests/portal/test_call_records.py`: a Call record's update and delete, a Business with records, and a record that breaks a rule (no cost and no reason, an unknown kind, a call id that is words).
- Catalog sweep tests: none yet.
