#!/usr/bin/env node
// Guard: a change to something only the evals can test (the list in scripts/eval-required.json: the agent's
// prompt and settings, the Business's instructions, the Pipecat pin) needs a receipt from a passing full `make eval`
// that matches the files as they are now. CI never runs the paid evals; Petter does, locally.
// The list is read from the base branch (scripts/base-config.js), so a PR cannot drop a file it changes from it.
// Known limits: a hand-written receipt passes this check, so review checks that the receipt came from `make eval`;
// and an edit to scripts/eval-receipt.js or to this guard does not trigger it, but those are
// scripts/ files, which a green PR now merges without Petter reading them (VOI-49).
// Compares with $GUARD_BASE (CI sets origin/<base branch> on pull requests), else origin/main.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = process.env.GUARD_ROOT || process.cwd();
const { fingerprint, readConfig } = require(path.join(__dirname, '..', '..', 'eval-receipt.js'));
const { changedFiles } = require(path.join(__dirname, '..', '..', 'base-config.js'));

const fail = (id, msg) => { console.log(`${id}\t${msg}`); process.exitCode = 1; };

let cfg;
try { cfg = readConfig(ROOT); } catch (e) {
  console.log('#scanned 1');
  fail('config', e.message);
  process.exit();
}
const listed = [...cfg.paths, ...Object.keys(cfg.lines)];
let changed;
try { changed = changedFiles(ROOT); } catch (e) { console.log('#scanned 1'); fail('base', e.message); process.exit(); }
console.log(`#scanned ${changed.length + 1}`); // +1: the change set itself, which may be empty
if (!changed.some((f) => listed.includes(f))) process.exit();

const fix = 'run `make eval` (paid, local: ask Petter first) and commit the eval-receipt.json it writes';
let now;
try { now = fingerprint(ROOT, cfg); } catch (e) { fail('config', e.message); process.exit(); }
let receipt = {};
try { receipt = JSON.parse(fs.readFileSync(path.join(ROOT, cfg.receipt), 'utf8')).files || {}; } catch { /* no usable receipt: every file counts as stale */ }
for (const f of Object.keys(now).filter((f) => receipt[f] !== now[f])) {
  fail(f, `${f} changed without a passing eval run on it: ${fix}`);
}
