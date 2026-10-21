# What a PR screenshot may show

Question: when an agent attaches before and after screenshots to a pull request (VOI-258), what may they show, and how is each surface made safe to capture?

## Who sees an attachment

- The repository is public (`gh repo view --json visibility` returned `PUBLIC`, read 2026-10-21). An image attached to a PR body is visible to anyone, and it stays reachable after the PR closes. So a screenshot may show only seeded, synthetic data.
- `gh` 2.99.0 uploads images with the repeatable `--attach` flag on `gh pr create`, `gh pr edit` and `gh pr comment`. A body reference such as `![alt](./file.png)` is rewritten to the uploaded asset, and unreferenced attachments are appended. If some uploads fail, the PR is still made and the command exits non-zero. Up to 50 files per command, alt text after `#` (`gh pr create --help`, gh 2.99.0, read 2026-10-21; also `.claude/skills/playwright-cli/references/pr-attachments.md`).

## Which database the Portal shows

Before VOI-257, `make portal-up` could read another project's Postgres on 5432, so a screenshot could have shown someone else's data. Now the Portal's Postgres is on 55431, and `scripts/local-portal-db.sh` refuses to start when `DATABASE_URL`'s port is not the one Voice's container got (VOI-257, VOI-260). A Portal started with `make portal-up` is therefore on Voice's own database. `make seed` (VOI-259) fills it with two synthetic Businesses on example.com, PTS's reserved phone numbers (`docs/research/swedish-fictional-phone-numbers.md`), and calls, call logs and a pending change.

## Each surface

| Surface | Seeded data fills it | Never capture |
|---|---|---|
| Landing page (logged out, `/`) | no data to fill | — |
| Dashboard (`/`, logged in) | the Business's name, website, calls today | the Call button snippet: it holds the Business's call link (`call_slug`), a credential for starting calls (`.claude/rules/security.md`). Capture above it or leave the dashboard out. |
| Calls, Modules, Settings, Pending changes | yes | — |
| Access tokens (`/tokens/`) | the list of token labels | the page right after making a token: it shows the new secret once |
| Call logs and Totals | yes, for the operator only: set `SUPER_ADMIN_EMAIL` in `.env` to the first seeded login, which `make seed` prints | — |
| The core's call page during a live call (`make up`, :7860) | no: a call needs a Portal-made link, spends Gemini credit, and shows the live transcript | the whole page: out of scope until a synthetic Caller exists |

## The website domain

The seed sets every website to `example.com` (RFC 2606). A logo is never fetched from a website: a Business uploads it (`portal/accounts/theme.py`). The domain matters because the dashboard names it, and because the core lets only that site frame the call page, so a reserved domain keeps any real company's name out of the shot.

Not checked: whether GitHub ever deletes an attachment that no PR references any more. Treat every upload as permanent.
