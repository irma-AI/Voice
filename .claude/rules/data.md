---
paths:
  - "portal/**/models.py"
  - "portal/**/migrations/*.py"
---

# Data model and migrations

The Portal's system of record is Postgres (`DATABASE_URL`), with no cache or queue beside it. Models are in `portal/<app>/models.py`; migrations are generated into `portal/<app>/migrations/` by `make generate`, and `make generate-check` fails when a model changed without one.

- **Schema changes are new migrations.** A shipped migration is never edited; a fix is the next migration.
- **A migration runs while the previous Portal copy still serves** (Dokploy's update order is start-first, VOI-121), so it must work for the previous code too: add a column or table in one change, drop or rename in a later one. No check yet.
- **The store enforces the rule** (`CLAUDE.md` § Hard rules 1) for every writer, scripts and workers included: a constraint, trigger, schema validation or permission in the migration that introduces it, whose error names the rule it enforces, and the allowed path where one exists ("use X instead"). Application code may check it too, for a friendlier error; the store is what refuses. A real exception is a named, logged path, not a bypass role. In Django: a `UniqueConstraint`, `CheckConstraint` or `OneToOneField`, never only a form or `clean()` check. A constraint's name states the rule (`business_daily_budget_must_not_be_negative`) so the Postgres error does; a `OneToOneField` keeps Django's generated name.
- **A data-store rule ships with a real-store test** that makes the bad write and asserts the refusal (`.claude/rules/tests.md`). A migration that needs none says `db-test: skip <reason>`.
- **Caches and queues hold nothing that must survive a flush.** A value whose loss breaks a rule belongs in the system of record.

## Enforced by

- `db-test-required` guard (`scripts/checks/db-test-required.json`): a changed migration needs a change under `tests/portal/`, or `db-test: skip <reason>`.
- The refusals themselves: `tests/portal/test_accounts.py` (second Business on an account, duplicate or upper-case email, empty name) and `tests/portal/test_business_settings.py` (no language or an unknown one, a setting longer than the contract allows) and `tests/portal/test_call_link.py` (a second Business with the same call link, a call link with a quote, space or angle bracket or under 22 characters, a negative daily budget).
- `tests/portal/test_theme.py`: a logo over 256 KB, one that is not a PNG, WebP or JPEG by its bytes (SVG, GIF, empty), a logo key that is not the logo's hash, and an accent that is not `#` and six lower-case hex digits.
- `tests/portal/test_website_domain.py`: a stored website domain that is upper case, has a scheme, path, port, space or header line, or is not a plain domain.
- `tests/portal/test_privacy_url.py`: a stored privacy notice address that is not https, has no scheme, nothing after the scheme, a space or a header line.
- `tests/portal/test_modules_page.py`: a Module with no address or two, an address holding a user, password, query or key, a blank or repeated name, too many arguments, an eleventh per Business, or a delete outside `Module.remove` (a plain DELETE, a Business's cascade).
- `tests/portal/test_access_tokens.py`: an Access token with a scope other than read or full, a hash that is not a lower-case SHA-256 (the secret itself), a repeated hash or a blank label, a change to anything but `last_used_at` and a first `revoked_at`, and a revoked time that is not the database's clock or is set twice; a label change other than offboarding's blanking of a revoked token; and any delete of a token, a Business's cascade included (revoke it instead).
- `tests/portal/test_call_records.py`: a Call record's update and delete, a Business with records, and a record that breaks a rule (no cost and no reason, an unknown kind, a call id that is words, a start more than an hour ahead; the Call record address stores that one at the database's clock instead).
- `tests/portal/test_call_logs.py`: a Call log's update, its delete before 30 days after the call's start, a Business with logs, and a log that breaks a rule (an unknown kind, a call id that is words, an event field the security rule does not list, a value with a space, a level trace holding anything but at most 20 numbers, a user-agent string where the browser family goes, a start in the future).
- `tests/portal/test_agent_endpoint.py`: a Command record's update or delete, a result outside the known set and a command that is not a Command name.
- `tests/portal/test_pending_changes.py`: a Pending change staged decided or at another time than the database's, a decision outside `changes.decide`, a second decision, an approval after 7 days, a cancel other than its token's revoke, a change staged by a revoked token, an unknown kind, any other change to it and its delete. `tests/portal/test_agent_settings.py`: a Business name on more than one line, a change to staged values, their delete while the change waits, and staged values added to a change that no longer waits.
- `tests/portal/test_lock_races.py` (VOI-246): a chat approval against a revoke of its token, offboarding and a page approval, and staging against offboarding, each on two real connections: no deadlock, decided once.
- Catalog sweep tests: none yet.
