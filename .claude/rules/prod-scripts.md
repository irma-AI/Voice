---
paths:
  - "portal/**/management/commands/**"
---

# Scripts that change shared or production data

Every such script follows one contract, whatever its language. In the Portal that is a Django management command (`portal/accounts/management/commands/invite_business.py` is the example).

1. **Dry run by default.** With no flags it changes nothing: it prints the plan, each row or object it would change and how, in a stable order.
2. **Execute only the reviewed plan.** `--execute` refuses to run anything but the plan a person reviewed: the command prints a sha256 of the dry run's plan, and `--execute --approved-hash=<sha256>` runs only if it matches.
3. **Target named explicitly.** `--target` is required and must equal the process's `ENVIRONMENT`; the command prints it first. A local `.env` that points at production is a stop-and-ask (`CLAUDE.md` § Stop and ask).
4. **Leave a record.** After executing, log who ran it, what ran and the counts through the `portal.audit` logger (ids only, no emails or names), which goes to the server log.

## Enforced by

- `tests/portal/test_accounts.py`: the invite command changes nothing without the reviewed hash or with the wrong target. A new command adds its own test.
