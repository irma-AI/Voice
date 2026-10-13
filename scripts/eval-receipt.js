#!/usr/bin/env node
// The eval receipt: `make eval` (all Scenarios, all passed) runs `node scripts/eval-receipt.js write`, which
// records a hash of every file in scripts/eval-required.json (the one list of what only the evals can test).
// The eval-required guard recomputes the hashes with fingerprint() below and compares.
// Line endings are normalised, so a Windows checkout hashes like Linux CI.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '..');
const CONFIG = 'scripts/eval-required.json';
const readConfig = (root) => JSON.parse(fs.readFileSync(path.join(root, CONFIG), 'utf8'));

// { "<path>": "<sha256>" }; throws when a listed file or pinned line is gone, so a rename can't silently shrink the list.
function fingerprint(root = ROOT) {
  const cfg = readConfig(root);
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
  const receipt = path.join(ROOT, readConfig(ROOT).receipt);
  fs.writeFileSync(receipt, JSON.stringify({ files: fingerprint() }, null, 2) + '\n');
  console.log(`wrote ${path.relative(ROOT, receipt)}: commit it with the change`);
}
module.exports = { fingerprint, readConfig };
