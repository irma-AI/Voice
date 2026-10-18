#!/usr/bin/env node
// The eval receipt: `make eval` (all Scenarios, all passed) runs `node scripts/eval-receipt.js write`, which
// records a hash of every file in scripts/eval-required.json (the one list of what only the evals can test).
// The eval-required guard recomputes the hashes with fingerprint() below and compares.
// Line endings are normalised, so a Windows checkout hashes like Linux CI.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const { readBaseJson } = require('./base-config');

const ROOT = path.resolve(__dirname, '..');
const CONFIG = 'scripts/eval-required.json';
// The list as on the base branch (scripts/base-config.js), so a change cannot drop itself from it; `write` reads
// origin/main like the guard's CI run reads the PR's base.
const readConfig = (root, opts) => readBaseJson(root, CONFIG, opts);

// { "<path>": "<sha256>" }; throws when a listed file or pinned line is gone, so a rename can't silently shrink the list.
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
    out[f] = crypto.createHash('sha256').update(text).digest('hex');
  }
  return out;
}

if (require.main === module) {
  if (process.argv[2] !== 'write') { console.error('usage: node scripts/eval-receipt.js write'); process.exit(2); }
  const cfg = readConfig(ROOT, { local: true });
  const receipt = path.join(ROOT, cfg.receipt);
  fs.writeFileSync(receipt, JSON.stringify({ files: fingerprint(ROOT, cfg) }, null, 2) + '\n');
  console.log(`wrote ${path.relative(ROOT, receipt)}: commit it with the change`);
}
module.exports = { fingerprint, readConfig };
