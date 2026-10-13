# What agents can reach

How an agent reaches each source it needs to work like an engineer, and what it may not do there. An agent looks here before saying it can't see something, and a source with no row is one it can't reach yet.

Access starts read-only; writing to a source is its own row with its own reason. Credentials follow `CLAUDE.md` § Hard rules 6, and production data stays stop-and-ask whatever a row says.

| Source | How an agent reaches it | Credential (name only, never the value) | May | May not |
|---|---|---|---|---|
| Tickets: Linear (team `PET`, project `Voice`) | `linearis` CLI, installed by `scripts/cloud-tools.sh` | `LINEAR_API_TOKEN` | read, create, comment, label issues in the Voice project | delete issues; change other projects, teams, cycles or project settings |
| Code: GitHub, this repo | GitHub MCP tools in cloud sessions | the session's GitHub connection | read; push to the session's branch; open PRs; comment; turn on auto-merge when `make merge-check` says `LOW-RISK` and CI passes | merge anything else without Petter's go-ahead (`CLAUDE.md` § Workflow); force-push to `main`; change repo settings |
| Model: Gemini API | requests to `generativelanguage.googleapis.com`; the cloud proxy injects the key | none in the session (proxy-injected); production key is `GOOGLE_API_KEY` in Dokploy | calls inside the spend caps | raise caps, change the key, project or billing tier (`CLAUDE.md` § Stop and ask) |
| Hosting: Dokploy, project `Voice` | Dokploy API at the host the cloud environment's network policy allows; the cloud proxy injects the token | none in the session (proxy-injected) | read app status, deploy history and logs of the Voice project | deploy, change config or env, or read any other project: the token reaches all projects, so this is a rule, not a scope |
| DNS: HostUp | HostUp API (`*.hostup.se`); the cloud proxy injects the token | none in the session (proxy-injected) | read DNS records | change DNS records |
| Paid evals in the cloud: GitHub Actions workflow `Evals` (`.github/workflows/evals.yml`) | start it with the GitHub MCP `actions_run_trigger` after Petter said go in his own words; the run then waits for his Approve click on the `evals` environment | `GOOGLE_API_KEY`, a secret of the `evals` environment only (Petter sets it) | start the workflow on a branch; read its logs | approve a run, edit the environment, its reviewers or its secret, or start a run without his go |
