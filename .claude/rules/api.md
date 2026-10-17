---
paths:
  - "portal/urls.py"
  - "portal/**/views.py"
  - "portal/**/forms.py"
---

# Request handlers

Every Portal page is a Django view that shows its own state (`portal/accounts/views.py` is the example).

- **Parse, don't validate.** A handler parses its input once, at the boundary, into a typed value (a Django form or the framework's own view). Code past the boundary takes that value and never re-checks raw input.
- **Behind the login by default.** A page for a Business is a `@login_required` view that reads only `request.user`'s Business. A page open to visitors is listed in `OPEN` in `tests/portal/test_routes.py` with its reason.
- **Fail closed.** A page that cannot tell who is asking refuses (the login redirect), never shows.

## Enforced by

- `tests/portal/test_routes.py`: every route outside `OPEN` sends a visitor to the login.
- One Business never reads another's data: `tests/portal/test_business_settings.py` (a Business edits only its own settings). The settings address for the core (`settings_for_core`) is open in `OPEN` because the shared secret gates it, not a session; its test refuses a missing, wrong or unset secret.
- The Modules page (`modules`, `remove_module`) shows and removes only `request.user`'s Business's Modules; `tests/portal/test_modules_page.py` fails if another Business's Module can be seen, served or removed.
- The public call link (`call_link`) is open in `OPEN` on purpose: `tests/portal/test_call_link.py` shows it takes no Business from the request but its own unguessable slug, and only reads.
- The test call (`test_call`, a POST behind the login) takes no Business from the request: it mints a ticket for `request.user`'s Business, and `tests/portal/test_test_call.py` fails if the request can name another.
- The calls page (`calls`) shows only `request.user`'s Business's Call records, newest first, with no cost; `tests/portal/test_recent_calls.py` fails if another Business's record, a cost or a call id shows.
- The Call record address (`record_call`, a POST) is open in `OPEN` for the same reason as `settings_for_core`: the shared secret gates it, and `tests/portal/test_call_records.py` refuses a missing, wrong or unset secret before any lookup.
- The totals page (`totals`) is behind the login and then the `SUPER_ADMIN_EMAIL` setting, refusing every other Account with 403 (and everyone when it is unset); `tests/portal/test_totals.py` fails if another Account opens it.
