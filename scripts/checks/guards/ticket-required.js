#!/usr/bin/env node
// Guard: a pull request that changes anything outside the "no_ticket" paths of scripts/low-risk-paths.json must
// name a ready Linear ticket in its title or body (scripts/ticket-check.js holds the rule). CI sets GUARD_BASE and
// GUARD_PR_TEXT (title, a newline, body) on pull requests, plus LINEAR_API_TOKEN. Fails closed: with GUARD_BASE set
// and no token, or no answer from Linear, it refuses. Outside a pull-request run (a local make guards) nothing is
// compared, and a note says so. Known limit: see scripts/ticket-check.js.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const ROOT = process.env.GUARD_ROOT || process.cwd();
const { ticketIds, fetchIssue, problem, needsTicket, FIX } = require(path.join(__dirname, '..', '..', 'ticket-check.js'));

// A fixture has `.guard-changed-files`, `.guard-pr-text` and `.guard-tickets.json` (id to Linear issue) in place of
// a git diff, the CI env and Linear.
const read = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');
const fixture = fs.existsSync(path.join(ROOT, '.guard-changed-files'));
if (!fixture && !process.env.GUARD_BASE) {
  console.log('#scanned 1');
  console.error('not a pull-request run (GUARD_BASE unset): the ticket is checked in CI only');
  process.exit(0);
}

function changedFiles() {
  if (fixture) return read('.guard-changed-files').split('\n').filter(Boolean);
  const git = (...a) => execFileSync('git', a, { cwd: ROOT, encoding: 'utf8' }).trim();
  const from = git('merge-base', process.env.GUARD_BASE, 'HEAD');
  return git('diff', '--name-only', '--no-renames', from, 'HEAD').split('\n').filter(Boolean);
}

(async () => {
  const changed = changedFiles();
  console.log(`#scanned ${changed.length + 1}`); // +1: the change set itself, which may be empty
  if (!changed.some((f) => needsTicket(ROOT, f))) return;
  const ids = ticketIds(fixture ? read('.guard-pr-text') : process.env.GUARD_PR_TEXT);
  if (!ids.length) {
    console.log(`no-ticket\tthis PR changes files that need a ticket and closes none. ${FIX}`);
    process.exitCode = 1;
    return;
  }
  const tickets = fixture ? JSON.parse(read('.guard-tickets.json')) : null;
  for (const id of ids) {
    let why;
    try { why = problem(id, tickets ? tickets[id] : await fetchIssue(id)); } catch (e) { why = `cannot ask Linear (${e.message}); set LINEAR_API_TOKEN for this CI step`; }
    if (why) { console.log(`${id}\t${why}. ${FIX}`); process.exitCode = 1; }
  }
})();
