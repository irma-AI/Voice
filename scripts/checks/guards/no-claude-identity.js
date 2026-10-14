#!/usr/bin/env node
// Guard: no commit that reaches main carries Claude's identity or attribution (CLAUDE.md § Workflow). GitHub's
// squash merge adds "Co-authored-by: <author>" for each branch-commit author other than the merger, so a branch
// of commits authored "Claude <noreply@anthropic.com>" puts that line on main. Checks author and committer, and
// the message for Co-authored-by / Claude-Session trailers, the "Generated with Claude Code" footer and session links.
// In a pull-request run CI sets GUARD_BASE (and GUARD_HEAD, the PR's own head: the checkout is a synthetic merge
// commit) and every commit in the range is read; a local run reads origin/main..HEAD. A push to main (CI, no
// GUARD_BASE) reads only its tip: that is the trace if a squash message carried the line anyway.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync, spawnSync } = require('child_process');
const ROOT = process.env.GUARD_ROOT || process.cwd();

const FIX = 'run `sh scripts/git-identity.sh`, then re-author your branch: `git rebase -r origin/main --exec "git commit --amend --no-edit --reset-author"`, strip any Claude trailer from the messages, and force-push your own branch with --force-with-lease';
const IDENTITY = /@anthropic\.com>?$|^claude\b/i; // "Name <email>" of an author or committer
const MESSAGE = [
  [/^co-authored-by:.*(claude|anthropic)/im, 'a Co-authored-by trailer naming Claude'],
  [/^claude-session:/im, 'a Claude-Session trailer'],
  [/generated with \[?claude code/i, 'a "Generated with Claude Code" footer'],
  [/claude\.ai\/code\/session/i, 'a claude.ai session link'],
];

// A fixture has `.guard-commits.json` (a list of {sha, author, committer, message}) in place of git.
function commits() {
  const stored = path.join(ROOT, '.guard-commits.json');
  if (fs.existsSync(stored)) return JSON.parse(fs.readFileSync(stored, 'utf8'));
  const git = (...a) => execFileSync('git', a, { cwd: ROOT, encoding: 'utf8' });
  const local = !process.env.GITHUB_ACTIONS && spawnSync('git', ['rev-parse', '-q', '--verify', 'origin/main'], { cwd: ROOT }).status === 0;
  const base = process.env.GUARD_BASE || (local ? 'origin/main' : '');
  const range = base ? [`${base}..${process.env.GUARD_HEAD || 'HEAD'}`] : ['-1', 'HEAD'];
  // \x1f splits fields, \x1e ends a commit; a message can hold anything else.
  return git('log', '--format=%H%x1f%an <%ae>%x1f%cn <%ce>%x1f%B%x1e', ...range).split('\x1e')
    .filter((c) => c.trim()).map((c) => {
      const [sha, author, committer, message] = c.trim().split('\x1f');
      return { sha, author, committer, message };
    });
}

const list = commits();
console.log(`#scanned ${list.length + 1}`); // +1: the range itself, which can be empty
for (const c of list) {
  const why = [];
  if (IDENTITY.test(c.author)) why.push(`authored by ${c.author}`);
  if (IDENTITY.test(c.committer)) why.push(`committed by ${c.committer}`);
  for (const [re, what] of MESSAGE) if (re.test(c.message)) why.push(`has ${what}`);
  if (why.length) {
    console.log(`${c.sha.slice(0, 7)}\tcommit ${c.sha.slice(0, 7)} ${why.join(' and ')}: ${FIX}`);
    process.exitCode = 1;
  }
}
