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
- The Access tokens page (`access_tokens`, `revoke_access_token`) shows and revokes only `request.user`'s Business's tokens and shows a new token's secret once, on the answer to the POST, never in a later view; `tests/portal/test_access_tokens.py` fails if another Business's token can be listed or revoked, or the secret shows again.
- The logo address (`logo`) is open in `OPEN` on purpose: the core's call page loads it. It is keyed by the hash of the logo's bytes, never a Business's id or call link, and `tests/portal/test_theme.py` fails if an id or call link opens one.
- The public call link (`call_link`) is open in `OPEN` on purpose: `tests/portal/test_call_link.py` shows it takes no Business from the request but its own unguessable slug, only reads, and makes no ticket for a request that does not say it is in a frame, for a Business with no saved website domain, or once the Business's daily budget is spent (test calls apart). The Call button script (`call_button_js`) is open for the same reason: the Business's website loads it, it is the same text for everyone and holds no Business.
- The test call (`test_call`, a POST behind the login) takes no Business from the request: it mints a ticket for `request.user`'s Business, and `tests/portal/test_test_call.py` fails if the request can name another.
- The calls page (`calls`) shows only `request.user`'s Business's Call records, newest first, with no cost; `tests/portal/test_recent_calls.py` fails if another Business's record, a cost or a call id shows.
- The Call record address (`record_call`, a POST) is open in `OPEN` for the same reason as `settings_for_core`: the shared secret gates it, and `tests/portal/test_call_records.py` refuses a missing, wrong or unset secret before any lookup.
- The totals page (`totals`) is behind the login and then the `SUPER_ADMIN_EMAIL` setting, refusing every other Account with 403 (and everyone when it is unset); `tests/portal/test_totals.py` fails if another Account opens it.
- A form the CSRF check refuses (a page left open, a login in another tab) gets the Portal's page saying nothing changed, never Django's; a GET of a POST-only address (Test call, Remove) does nothing and goes back to its page: `tests/portal/test_inputs.py` (Revoke on the Access tokens page: `tests/portal/test_access_tokens.py`).
