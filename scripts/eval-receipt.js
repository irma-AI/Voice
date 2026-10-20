#!/usr/bin/env node
// The eval receipt: `make eval` (all Scenarios, all passed) runs `node scripts/eval-receipt.js write`, which
// records a hash of every file in scripts/eval-required.json (the one list of what only the evals can test), and
// under "model-input" a hash of what the model is sent: the output of the list's `rendered.command`
// (scripts/model_input.py), which the guard reruns when a `rendered.from` file changes. So an edit to those files
// that the model never sees needs no paid run (VOI-211).
// The eval-required guard recomputes the hashes with fingerprint() below and compares.
// Line endings are normalised, so a Windows checkout hashes like Linux CI.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const { readBaseJson } = require('./base-config');

const ROOT = path.resolve(__dirname, '..');
const CONFIG = 'scripts/eval-required.json';
// The list as on the base branch (scripts/base-config.js), so a change cannot drop itself from it; `write` reads
// origin/main like the guard's CI run reads the PR's base.
const readConfig = (root, opts) => readBaseJson(root, CONFIG, opts);

const sha = (text) => crypto.createHash('sha256').update(text.replace(/\r\n/g, '\n')).digest('hex');
const MODEL_INPUT = 'model-input';

// What the model is sent, rendered by the list's command; throws (fail closed) when it cannot run.
function modelInput(root, [cmd, ...args]) {
  const r = spawnSync(cmd, args, { cwd: root, encoding: 'utf8' });
  if (r.status !== 0 || !r.stdout.trim()) {
    const why = (r.error ? String(r.error) : (r.stderr || '').trim().split('\n').slice(-3).join(' | ')).slice(0, 400);
    throw new Error(`\`${[cmd, ...args].join(' ')}\` (${CONFIG} rendered.command) did not render what the model is sent (exit ${r.status}): ${why}`);
  }
  return sha(r.stdout);
}

// { "<path>": "<sha256>", "model-input": "<sha256>" }; throws when a listed file or pinned line is gone, so a rename
// can't silently shrink the list.
function fingerprint(root = ROOT, cfg = readConfig(root)) {
  const out = {};
  for (const f of [...cfg.paths, ...Object.keys(cfg.lines)]) {
    const file = path.join(root, f);
    if (!fs.existsSync(file)) throw new Error(`${f} is listed in ${CONFIG} but does not exist: update the list`);
    let text = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
    const only = cfg.lines[f];
    if (only !== undefined) {
      text = text.split('\n').filter((l) => l.includes(only)).join('\n');
      if (!text) throw new Error(`${f} has no line containing "${only}" (${CONFIG}): update the list`);
    }
    out[f] = sha(text);
  }
  if (cfg.rendered) out[MODEL_INPUT] = modelInput(root, cfg.rendered.command);
  return out;
}

if (require.main === module) {
  if (process.argv[2] !== 'write') { console.error('usage: node scripts/eval-receipt.js write'); process.exit(2); }
  const cfg = readConfig(ROOT, { local: true });
  const receipt = path.join(ROOT, cfg.receipt);
  fs.writeFileSync(receipt, JSON.stringify({ files: fingerprint(ROOT, cfg) }, null, 2) + '\n');
  console.log(`wrote ${path.relative(ROOT, receipt)}: commit it with the change`);
}
module.exports = { fingerprint, readConfig, MODEL_INPUT };
