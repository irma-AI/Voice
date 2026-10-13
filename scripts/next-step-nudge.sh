#!/usr/bin/env bash
# SessionStart hook: tells every session to run the repo's flow before any work. Its stdout is added to Claude's context.
# Runs again after /compact and resume, so the reminder survives a long session.
cat <<'TXT'
Before anything else, load the repo's `next-step` skill with the Skill tool and pass it the user's request or the brief you were given. It picks the flow (grilling, spec, tickets, then one PR per ticket) and says where it stops.
A brief that says what to build ("add X", "implement Y") does not replace it: classify the work through next-step first. No edits, branches or PRs before it has picked a flow, and none for a Feature before Petter has approved its tickets.
TXT
