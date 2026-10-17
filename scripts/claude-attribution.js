// The one list of Claude attribution (CLAUDE.md § Workflow) that must stay out of commits, PR text and PR comments.
// Read by the no-claude-identity guard (commit messages and PR title/body) and by the PreToolUse hook
// scripts/claude-attribution-gate.js (GitHub tool writes). Add a variant here and both catch it.
'use strict';
module.exports = [
  [/^co-authored-by:.*(claude|anthropic)/im, 'a Co-authored-by trailer naming Claude'],
  [/^claude-session:/im, 'a Claude-Session trailer'],
  [/generated (?:with|by) \[?claude code/i, 'a "Generated with/by Claude Code" footer'],
  [/claude\.ai\/code\/session/i, 'a claude.ai session link'],
];
