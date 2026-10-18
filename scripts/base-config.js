// The configuration a guard enforces (scripts/low-risk-paths.json, scripts/eval-required.json), read from the base
// branch so a pull request cannot loosen the rule that checks it (VOI-124). A list edit applies once it merges.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const FIXTURES = path.join(__dirname, 'checks', 'fixtures');

// CI (GUARD_BASE set) reads the base and throws when it can't; the hooks pass { local: true } for origin/main.
function readBaseJson(root, rel, { local = false } = {}) {
  // Only a guard fixture may stand in for the base; a .guard-base/ elsewhere would let a PR pick its own "base".
  const fixture = path.join(root, '.guard-base', rel);
  if (!path.relative(FIXTURES, root).startsWith('..') && fs.existsSync(fixture)) return JSON.parse(fs.readFileSync(fixture, 'utf8'));
  const show = (ref) => JSON.parse(execFileSync('git', ['show', `${ref}:${rel}`], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }));
  const base = process.env.GUARD_BASE;
  if (base) {
    try { return show(base); } catch (e) { throw new Error(`cannot read ${rel} from ${base} (${e.message.split('\n')[0]}): fetch the base branch (CI checks out with fetch-depth 0)`); }
  }
  if (local) {
    try { return show('origin/main'); } catch { console.error(`note: ${rel} is not on origin/main here, so the working-tree copy decides`); }
  }
  return JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
}

module.exports = { readBaseJson };
