#!/usr/bin/env node
// Guard: a change to something only the evals can test (the list in scripts/eval-required.json: the agent's
// prompt and settings, the Business's instructions, the Pipecat pin) needs a receipt from a passing full `make eval`
// that matches the files as they are now. For the list's `rendered.from` files (voice/settings.py, voice/modules.py)
// only what the model is sent counts: the guard reruns `rendered.command` and compares its hash (VOI-211).
// CI never runs the paid evals; Petter does, locally or through the Evals workflow.
// The list is read from the base branch (scripts/base-config.js), so a PR cannot drop a file it changes from it.
// Known limits: a hand-written receipt passes this check, so eval-receipt.json is fenced (scripts/low-risk-paths.json): a PR
// that changes it needs Petter's evals-approved label (VOI-235);
// and an edit to scripts/eval-receipt.js or to this guard does not trigger it, but those are
// scripts/ files, which a green PR now merges without Petter reading them (VOI-49); and an edit to a `rendered.from`
// file that changes the call but not what the model is sent at its start (how a tool call reaches its Module) passes.
// Compares with $GUARD_BASE (CI sets origin/<base branch> on pull requests), else origin/main.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = process.env.GUARD_ROOT || process.cwd();
const { fingerprint, readConfig, MODEL_INPUT } = require(path.join(__dirname, '..', '..', 'eval-receipt.js'));
const { changedFiles } = require(path.join(__dirname, '..', '..', 'base-config.js'));

const fail = (id, msg) => { console.log(`${id}\t${msg}`); process.exitCode = 1; };

let cfg;
try { cfg = readConfig(ROOT); } catch (e) {
  console.log('#scanned 1');
  fail('config', e.message);
  process.exit();
}
const listed = [...cfg.paths, ...Object.keys(cfg.lines), ...(cfg.rendered ? cfg.rendered.from : [])];
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
  fail(f, `${f === MODEL_INPUT ? 'what the model is sent (scripts/model_input.py)' : f} changed without a passing eval run on it: ${fix}`);
}
