---
target: views added since the redesign
total_score: 27
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 1
target_identity: "file:/Users/petterannerwall/Developer/Voice/.claude/worktrees/voi-views/portal/templates/accounts"
timestamp: 2026-10-19T15-26-51Z
slug: portal-templates-accounts
---
# Critique: views added since the redesign (VOI-171)
Targets: tokens.html, dashboard.html (tokens link, Call button note), settings.html (privacy notice field), voice/page.html (privacy link), base.html nav.

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of status | 3 | Revoked token now muted, still listed first |
| 2 | Match real world | 2 | "agent" means the voice agent and the owner's own AI agent on one screen; "Scope", "Claude Code", "Operator" |
| 3 | User control | 3 | Two-step Revoke |
| 4 | Consistency | 2 | Portal h1 at 3.5rem on tokens/calls/modules, 2.25rem on dashboard/settings; DESIGN says 3rem |
| 5 | Error prevention | 3 | Token Label has no help text |
| 6 | Recognition | 3 | Privacy notice filed under the agent, absent from the Callers preview |
| 7 | Flexibility | 3 | Dashboard rows repeat the nav |
| 8 | Minimalist | 3 | CSP text dominates the Call button section |
| 9 | Error recovery | 3 | Token errors use ad-hoc red box, no error token |
| 10 | Help | 2 | Tokens never says what an owner would use one for; times in UTC |
Total 27/40, Acceptable.

Priority issues
- P1 "agent" means two things (dashboard.html:19, tokens.html:5): clarify; needs a GLOSSARY term for the owner's own AI agent.
- P2 Privacy notice belongs with what Callers see (settings.html:21, call preview omits it): layout.
- P2 Two Portal h1 scales and "we" vs "Voice" voice: typeset, clarify.
- P2 Access tokens at full nav rank for a non-technical owner: shape/distill.
- P3 Times in UTC on tokens: polish.
Fixed during alignment: call-page privacy link 14.5px -> 24px target and DESIGN text-link underline; revoked token muted; tabular meta; dashboard integrity note in plain words; "your Callers".
