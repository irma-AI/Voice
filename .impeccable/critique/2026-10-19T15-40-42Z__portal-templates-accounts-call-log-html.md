---
target: call log pages
total_score: 22
max_score: 36
na_heuristics: 5
p0_count: 0
p1_count: 2
target_identity: "file:/Users/petterannerwall/Developer/Voice/.claude/worktrees/voi-views/portal/templates/accounts/call_log.html"
target_fingerprint: "sha256:aad64edf34d125d8b259c6e10180f3c4551c17734abc2d3c1b953f88c2f84154"
target_path: /Users/petterannerwall/Developer/Voice/.claude/worktrees/voi-views/portal/templates/accounts/call_log.html
timestamp: 2026-10-19T15-40-42Z
slug: portal-templates-accounts-call-log-html
---
# Critique: Call logs and one Call log (VOI-158 pages)
Heuristics: 1:2 2:3 3:2 4:3 5:n/a 6:2 7:2 8:3 9:2 10:3 = 22/36 (61%, Acceptable).
P1 barge-in and no-words invisible in the timeline (fixed: per-event tone, No words after label, frame events muted).
P1 Download pill outranked the timeline (fixed: ghost).
P2 back link 17px (fixed: 44px); operator pages missing from nav (deferred).
P2 raw JSON values (fixed in HTML; text file exact).
P3 list row figure order (fixed: barge-in line in Foam, no date underline).
Deferred: filter/paging, operator nav links, Turn-drawn log, mono face token.
