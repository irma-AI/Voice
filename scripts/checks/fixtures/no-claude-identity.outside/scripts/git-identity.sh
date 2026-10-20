#!/bin/sh
# SessionStart hook, and the fix the no-claude-identity guard names: commits in this repo are authored by Petter's
# GitHub noreply identity, never by Claude. GitHub's squash merge adds "Co-authored-by: <author>" for every branch
# commit author other than the merger, so a Claude-authored branch puts that line on main. This is the one place
# the identity is written down (hard rule 5). A person's own identity is left alone.
name='Petter Annerwall'
email='5909669+petterannerwall@users.noreply.github.com'
cd "$(dirname "$0")/.." || exit 2
case "$(git config user.email)" in
  ''|*@anthropic.com) git config user.name "$name" && git config user.email "$email" ;;
esac
[ "$(git config user.name)" != Claude ] || git config user.name "$name"
