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
- The call-start and call-end addresses (`start_call`, `end_call`) and the public call link (`call_link`) are open in `OPEN` for the same reason; `tests/portal/test_calls.py` refuses a missing or wrong secret, and shows the link takes no Business from the request but its own slug, so opening it counts and spends nothing.
- The test call (`test_call`, a POST behind the login) takes no Business from the request: it mints a ticket for `request.user`'s Business, and `tests/portal/test_test_call.py` fails if the request can name another.
