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
- One Business never reads another's data: none yet (the first page that shows Business data adds its test).
