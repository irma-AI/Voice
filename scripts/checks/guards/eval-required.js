#!/usr/bin/env node
// Guard: a change to something only the evals can test (the list in scripts/eval-required.json: the agent's
// prompt and settings, the Business's facts, the Pipecat pin) needs a receipt from a passing full `make eval`
// that matches the files as they are now. CI never runs the paid evals; Petter does, locally.
// Known limits: a hand-written receipt passes this check, so review checks that the receipt came from `make eval`;
// and an edit to the list, to scripts/eval-receipt.js or to this guard does not trigger it, but those are
// scripts/ files, which scripts/merge-check.js never calls low-risk, so Petter reads them before the merge.
// Compares with $GUARD_BASE (CI sets origin/<base branch> on pull requests), else origin/main.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const ROOT = process.env.GUARD_ROOT || process.cwd();
const { fingerprint, readConfig } = require(path.join(__dirname, '..', '..', 'eval-receipt.js'));

const fail = (id, msg) => { console.log(`${id}\t${msg}`); process.exitCode = 1; };

function changedFiles() {
  const listed = path.join(ROOT, '.guard-changed-files'); // fixtures list their "changed" files here
  if (fs.existsSync(listed)) return fs.readFileSync(listed, 'utf8').split('\n').filter(Boolean);
  const git = (...a) => execFileSync('git', a, { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  const base = process.env.GUARD_BASE || 'origin/main';
  let from;
  try { from = git('merge-base', base, 'HEAD'); } catch {
    // CI named a base it cannot reach: refuse. Only the unset local default may pass, with its note.
    if (process.env.GUARD_BASE) { fail('base', `cannot compare with ${process.env.GUARD_BASE}: fetch it (CI checks out with fetch-depth 0)`); return []; }
    console.error(`no ${base} to compare with; nothing checked (CI sets GUARD_BASE on pull requests)`);
    return [];
  }
  // No diff filter and no renames: a deleted or moved listed file counts too.
  const committed = git('diff', '--name-only', '--no-renames', from, 'HEAD').split('\n');
  const working = git('diff', '--name-only', '--no-renames', 'HEAD').split('\n');
  return [...new Set([...committed, ...working])].filter(Boolean);
}

const cfg = readConfig(ROOT);
const listed = [...cfg.paths, ...Object.keys(cfg.lines)];
const changed = changedFiles();
console.log(`#scanned ${changed.length + 1}`); // +1: the change set itself, which may be empty
if (!changed.some((f) => listed.includes(f))) process.exit();

const fix = 'run `make eval` (paid, local: ask Petter first) and commit the eval-receipt.json it writes';
let now;
try { now = fingerprint(ROOT); } catch (e) { fail('config', e.message); process.exit(); }
let receipt = {};
try { receipt = JSON.parse(fs.readFileSync(path.join(ROOT, cfg.receipt), 'utf8')).files || {}; } catch { /* no usable receipt: every file counts as stale */ }
for (const f of Object.keys(now).filter((f) => receipt[f] !== now[f])) {
  fail(f, `${f} changed without a passing eval run on it: ${fix}`);
}
