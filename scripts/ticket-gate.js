#!/usr/bin/env node
// Two entry points for one rule: work needs a ready Linear ticket (scripts/ticket-check.js).
// 1. PreToolUse hook (Edit|Write|NotebookEdit): denies an edit to a repo file without one.
// 2. `--staged`, run by scripts/git-hooks/pre-commit: refuses a commit whose staged files need one, however they
//    were written (Bash scripts included). Only inside Claude Code ($CLAUDECODE), so Petter's own commits are free.
// Files in "no_ticket" of scripts/low-risk-paths.json (as on origin/main, scripts/base-config.js), and files outside the repo, need none. The session's ticket
// is $NEXT_STEP_TICKET, else the id in the file `next-step-ticket` in the git dir (/next-step writes it when it
// starts a ticket; the SessionStart hook deletes it on a fresh start), else a ticket id in the branch name.
// Fails closed: no ticket, no token or no answer from Linear denies and says why (exit 2, stderr to Claude).
// Known limit: Bash can still write files in the working tree; they cannot be committed here, and the CI guard
// ticket-required.js is the backstop for `git commit --no-verify`.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { idIn, fetchIssue, problem, needsTicket, TEAM } = require('./ticket-check');

const git = (...a) => execFileSync('git', a, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
const staged = process.argv.includes('--staged');
const deny = (why) => { console.error(`${staged ? 'Commit' : 'Edit'} denied: ${why}`); process.exit(2); };

(async () => {
  const root = git('rev-parse', '--show-toplevel');
  let rel;
  if (staged) {
    if (!process.env.CLAUDECODE) return; // a person's commit: the CI guard is their check
    rel = git('diff', '--cached', '--name-only', '--no-renames').split('\n').find((f) => f && needsTicket(root, f, { local: true }));
    if (!rel) return;
  } else {
    let input;
    try { input = JSON.parse(fs.readFileSync(0, 'utf8')); } catch (e) { return deny(`cannot read the hook input (${e.message})`); }
    const target = input.tool_input?.file_path || input.tool_input?.notebook_path;
    if (!target) return deny('the tool call names no file, so the ticket rule cannot be checked');
    let abs = path.resolve(input.cwd || root, target);
    try { abs = fs.realpathSync(abs); } catch { /* a new file: nothing to resolve */ } // a symlink under docs/ must not hide code
    rel = path.relative(fs.realpathSync(root), abs);
    if (rel.startsWith('..')) return; // outside the repo: scratch files and memory
    if (!needsTicket(root, rel, { local: true })) return;
  }

  let id = process.env.NEXT_STEP_TICKET;
  if (!id) { try { id = fs.readFileSync(git('rev-parse', '--git-path', 'next-step-ticket'), 'utf8').trim(); } catch { /* no marker */ } }
  if (!id) id = idIn(git('branch', '--show-current'));
  const fix = `Run the next-step skill. Once its ticket is labelled ready-for-agent, start work with \`/next-step ${TEAM}-<n>\`, which records the ticket for this session.`;
  if (!id) return deny(`${rel} needs a ready Linear ticket and this session has none. ${fix}`);
  let issue;
  try { issue = await fetchIssue(id); } catch (e) { return deny(`cannot ask Linear about ${id} (${e.message}), so the ticket rule cannot be checked. Fix the Linear access and retry.`); }
  const why = problem(id, issue);
  if (why) deny(`${why}. ${fix}`);
})().catch((e) => deny(`the ticket rule crashed (${e.message}), so it cannot be checked`)); // a crash must not read as "allowed"
