#!/usr/bin/env node
// Guard: a pull request that changes anything outside the "no_ticket" paths of scripts/low-risk-paths.json must
// name a ready Linear ticket in its title or body (scripts/ticket-check.js holds the rule). CI sets GUARD_BASE and
// GUARD_PR_TEXT (title, a newline, body) on pull requests, plus LINEAR_API_TOKEN. Fails closed: with GUARD_BASE set
// and no token, or no answer from Linear, it refuses. Outside a pull-request run (a local make guards) nothing is
// compared, and a note says so. The no_ticket list is read from the base branch (scripts/base-config.js), so this PR
// cannot exempt itself. Known limit: see scripts/ticket-check.js.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = process.env.GUARD_ROOT || process.cwd();
const { changedFiles, inFixture } = require(path.join(__dirname, '..', '..', 'base-config.js'));
const { ticketIds, fetchIssue, problem, needsTicket, FIX, TEAM } = require(path.join(__dirname, '..', '..', 'ticket-check.js'));

// A fixture has `.guard-changed-files`, `.guard-pr-text` and `.guard-tickets.json` (id to Linear issue) in place of
// a git diff, the CI env and Linear.
const read = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');
const fixture = inFixture(ROOT) && fs.existsSync(path.join(ROOT, '.guard-changed-files'));

// The team key lives in ticket-check.js and in docs/agents/issue-tracker.md: name the side to edit when they differ.
const tracker = fs.existsSync(path.join(ROOT, 'docs/agents/issue-tracker.md')) ? read('docs/agents/issue-tracker.md') : '';
const teamDrift = tracker.includes(`team \`${TEAM}\``) ? null : `docs/agents/issue-tracker.md does not name team \`${TEAM}\`, the TEAM in scripts/ticket-check.js: edit the one that is wrong`;
if (!fixture && !process.env.GUARD_BASE) {
  console.log('#scanned 1');
  if (teamDrift) { console.log(`team\t${teamDrift}`); process.exitCode = 1; }
  console.error('not a pull-request run (GUARD_BASE unset): the ticket is checked in CI only');
  process.exit(process.exitCode || 0);
}

(async () => {
  let changed;
  try { changed = changedFiles(ROOT); } catch (e) { console.log('#scanned 1'); console.log(`base\t${e.message}`); process.exitCode = 1; return; }
  console.log(`#scanned ${changed.length + 1}`); // +1: the change set itself, which may be empty
  if (teamDrift) { console.log(`team\t${teamDrift}`); process.exitCode = 1; }
  let needed;
  try { needed = changed.some((f) => needsTicket(ROOT, f)); } catch (e) {
    console.log(`config\t${e.message}`);
    process.exitCode = 1;
    return;
  }
  if (!needed) return;
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
