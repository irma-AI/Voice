---
paths:
  - "portal/**/management/commands/**"
---

# Scripts that change shared or production data

Every such script follows one contract, whatever its language. In the Portal that is a Django management command (`portal/accounts/management/commands/invite_business.py` is the example). The commands: `invite_business` (a new Business and its Account) and `offboard_business` (the one way a Business's personal data leaves: it empties the Business, revokes its Access tokens (cancelling the changes they asked for that still wait) and blanks their labels, and closes its Account, keeping the Business row and its Call records under its number; VOI-126, VOI-167). `expire_call_logs` deletes the Call logs past their 30 days (VOI-157), run daily by a Dokploy schedule. Steps 2 and 3 live in `portal/accounts/prod_script.py` (`check_target`, `reviewed_digest`): a new command calls them instead of copying them.

1. **Dry run by default.** With no flags it changes nothing: it prints the plan, each row or object it would change and how, in a stable order.
2. **Execute only the reviewed plan.** `--execute` refuses to run anything but the plan a person reviewed: the command prints a sha256 of the dry run's plan, and `--execute --approved-hash=<sha256>` runs only if it matches. The one exemption is `expire_call_logs`, which a schedule runs with `--execute` alone: the database's trigger refuses to delete a log younger than 30 days whoever asks, so a reviewed hash would add no safety (Petter, 2026-10-21).
3. **Target named explicitly.** `--target` is required and must equal the process's `ENVIRONMENT`; the command prints it first. A local `.env` that points at production is a stop-and-ask (`CLAUDE.md` § Stop and ask).
4. **Leave a record.** After executing, log who ran it, what ran and the counts through the `portal.audit` logger (ids only, no emails or names), which goes to the server log.

## Enforced by

- `tests/portal/test_accounts.py`: the invite command changes nothing without the reviewed hash or with the wrong target. A new command adds its own test.
- `tests/portal/test_call_logs.py`: the expiry command changes nothing without `--execute` or with the wrong target, and deletes only the logs past their expiry.
- `tests/portal/test_offboard.py`: the same for the offboarding command, and afterwards every column of the Account and the Business is emptied or listed as holding nothing about a person.
