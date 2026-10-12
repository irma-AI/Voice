# Issue tracker: Linear

Issues and specs for this repo live in Linear: team `PET` (Petters), project `Voice`. Use the `linearis` CLI (JSON output; `LINEAR_API_TOKEN` comes from the environment). What agents may do there: `docs/agents/agent-access.md`.

## Conventions

- **Create an issue**: `linearis issues create "<title>" --team PET --project Voice --description "..." --labels needs-triage`.
- **Read an issue**: `linearis issues read PET-<n>`, and `linearis issues discussions PET-<n>` for its comments.
- **List issues**: `linearis issues list --team PET --project Voice`, with `--label` and `--status` filters.
- **Comment on an issue**: `linearis issues discuss PET-<n>`, or `linearis issues reply <thread>` inside a thread.
- **Apply labels**: `linearis issues update PET-<n> --labels "<labels>"`.
- **Close**: `linearis issues update PET-<n> --status Done` after a comment saying why.
- **Find a branch's issue**: `linearis issues from-branch`.

Never delete an issue, and never change other projects, teams, cycles or project settings.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

## When a skill says "publish to the issue tracker"

Create a Linear issue in team `PET`, project `Voice`.

## When a skill says "fetch the relevant ticket"

Run `linearis issues read PET-<n>`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: one issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `linearis issues create ... --parent-ticket PET-<map>`, labelled `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`).
- **Blocking**: `--blocked-by PET-<n>` on create, or `linearis issues relations add PET-<n>` on an existing issue. A ticket is unblocked when every blocker is done.
- **Frontier query**: `linearis issues list --parent PET-<map>`, drop any with an open blocker or an assignee; first in map order wins.
- **Claim**: `linearis issues update PET-<n> --assignee <your user>` (`linearis users list` for names), the session's first write.
- **Resolve**: comment the answer, set status `Done`, then append a context pointer (gist + link) to the map's Decisions-so-far.
