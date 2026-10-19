#!/usr/bin/env node
// Guard: a pull request may not touch a frozen path (the "frozen" list in scripts/low-risk-paths.json: today the
// Call button file call-button.v1.js and its hash, which every pasted tag names, so an edit would stop the button on
// every Business's website; a changed script is a new version, VOI-135). No label lifts it: to retire a version,
// first merge a PR that takes it off the list, then one that removes it. The list is read from the base branch
// (scripts/base-config.js). Outside a pull-request run (a local make guards) nothing is compared, and a note says so.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { readBaseJson } = require(path.join(__dirname, '..', '..', 'base-config.js'));
const ROOT = process.env.GUARD_ROOT || process.cwd();

// A fixture has `.guard-changed-files` in place of a git diff and the CI env.
const listed = path.join(ROOT, '.guard-changed-files');
const fixture = fs.existsSync(listed);
if (!fixture && !process.env.GUARD_BASE) {
  console.log('#scanned 1');
  console.error('not a pull-request run (GUARD_BASE unset): frozen paths are checked in CI only');
  process.exit(0);
}

let frozen;
try { frozen = readBaseJson(ROOT, 'scripts/low-risk-paths.json').frozen || []; } catch (e) {
  console.log('#scanned 1');
  console.log(`config\t${e.message}`);
  process.exit(1);
}

function changedFiles() {
  if (fixture) return fs.readFileSync(listed, 'utf8').split('\n').filter(Boolean);
  const git = (...a) => execFileSync('git', a, { cwd: ROOT, encoding: 'utf8' }).trim();
  const from = git('merge-base', process.env.GUARD_BASE, 'HEAD');
  // No diff filter and no renames: a deleted or moved frozen file counts too.
  return git('diff', '--name-only', '--no-renames', from, 'HEAD').split('\n').filter(Boolean);
}

const changed = changedFiles();
console.log(`#scanned ${changed.length + 1}`); // +1: the change set itself, which may be empty
for (const f of changed.filter((f) => frozen.some((g) => path.matchesGlob(f, g)))) {
  console.log(`${f}\t${f} is frozen: every pasted Call button tag names its hash, so put the change in the next version (call-button.v2.js, its own hash, the dashboard and CALL_BUTTON_FILE pointing at it) and leave this file as it is`);
  process.exitCode = 1;
}
