// The configuration a guard enforces (scripts/low-risk-paths.json, scripts/eval-required.json), read from the base
// branch so a pull request cannot loosen the rule that checks it (VOI-124). A fixture's .guard-base/<rel> stands in
// for the base. On a pull-request run (GUARD_BASE set) the file comes from `git show $GUARD_BASE:<rel>`, and a
// failure throws: fail closed. The edit hook and pre-commit pass { local: true } and read origin/main when it has the
// file. Otherwise (a local make guards) the working tree. A change to the configuration takes effect once it merges.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

function readBaseJson(root, rel, { local = false } = {}) {
  const fixture = path.join(root, '.guard-base', rel);
  if (fs.existsSync(fixture)) return JSON.parse(fs.readFileSync(fixture, 'utf8'));
  const show = (ref) => execFileSync('git', ['show', `${ref}:${rel}`], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  if (process.env.GUARD_BASE) return JSON.parse(show(process.env.GUARD_BASE));
  if (local) { try { return JSON.parse(show('origin/main')); } catch { /* no origin/main, or the file is new: the working tree */ } }
  return JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
}

module.exports = { readBaseJson };
