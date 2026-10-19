#!/usr/bin/env node
// Guard: every commit that reaches main is authored and committed by the one identity in scripts/git-identity.sh, and no
// commit or PR text carries Claude's identity or attribution (CLAUDE.md § Workflow). An allow-list since VOI-140: a
// deny-list of Claude's address let another address of Petter's onto four branches on 2026-10-18. GitHub's
// squash merge adds "Co-authored-by: <author>" for each branch-commit author other than the merger, so a branch
// of commits authored "Claude <noreply@anthropic.com>" puts that line on main. Checks author and committer, and
// the message for Co-authored-by / Claude-Session trailers, the "Generated with/by Claude Code" footer and session links.
// The PR's title and body (GUARD_PR_TEXT, set by CI on pull requests; the GitHub tool appends the footer and a session
// link to every PR it opens) get the same message check; CI re-runs on an edit. PR comments are not checked.
// In a pull-request run CI sets GUARD_BASE (and GUARD_HEAD, the PR's own head: the checkout is a synthetic merge
// commit) and every commit in the range is read; a local run reads origin/main..HEAD. A push to main (CI, no
// GUARD_BASE) reads only its tip: that is the trace if a squash message carried the line anyway.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync, spawnSync } = require('child_process');
const ROOT = process.env.GUARD_ROOT || process.cwd();

const FIX = 'run `sh scripts/git-identity.sh` (and pass no -c user.name or user.email), then re-author your branch: `git rebase -r origin/main --exec "git commit --amend --no-edit --reset-author"`, strip any Claude trailer from the messages, and force-push your own branch with --force-with-lease';
// The one identity, read from the script that sets it (hard rule 5); the pre-commit hook reads the same line.
const EMAIL = fs.readFileSync(path.join(ROOT, 'scripts', 'git-identity.sh'), 'utf8').match(/^email='(.*)'$/m)[1];
const allowed = (ident) => ident.endsWith(`<${EMAIL}>`); // "Name <email>" of an author or committer
// GitHub commits a squash merge itself, so a push to main (tip-only run) sees it as the committer (VOI-144).
const GITHUB = 'GitHub <noreply@github.com>';
const MESSAGE = require(path.join(__dirname, '..', '..', 'claude-attribution.js')); // shared with the GitHub write hook

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
// A fixture has `.guard-pr-text` in place of the CI env.
const prFile = path.join(ROOT, '.guard-pr-text');
const prText = fs.existsSync(prFile) ? fs.readFileSync(prFile, 'utf8') : process.env.GUARD_PR_TEXT || '';
console.log(`#scanned ${list.length + 2}`); // +2: the commit range and the PR text, which can be empty
const prWhy = MESSAGE.filter(([re]) => re.test(prText)).map(([, what]) => `has ${what}`);
if (prWhy.length) {
  console.log(`pr-text\tthe PR title or body ${prWhy.join(' and ')}: edit the PR and delete those lines (keep the "Requested by" block); the GitHub tool adds them on create, so re-read the body after opening the PR`);
  process.exitCode = 1;
}
for (const c of list) {
  const why = [];
  if (!allowed(c.author)) why.push(`authored by ${c.author}`);
  if (!allowed(c.committer) && c.committer !== GITHUB) why.push(`committed by ${c.committer}`);
  for (const [re, what] of MESSAGE) if (re.test(c.message)) why.push(`has ${what}`);
  if (why.length) {
    console.log(`${c.sha.slice(0, 7)}\tcommit ${c.sha.slice(0, 7)} ${why.join(' and ')}: ${FIX}`);
    process.exitCode = 1;
  }
}
