// What a guard compares a pull request with: the configuration it enforces (scripts/low-risk-paths.json,
// scripts/eval-required.json, scripts/checks/db-test-required.json, scripts/checks/layers.json), read from the base
// branch so a pull request cannot loosen the rule that checks it (VOI-124), and the files the change touches (VOI-165).
// A list edit applies once it merges.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const FIXTURES = path.join(__dirname, 'checks', 'fixtures');
// Only a guard fixture may stand in for the base or the diff; a .guard-* file elsewhere would let a PR pick its own.
const inFixture = (root) => !path.relative(FIXTURES, root).startsWith('..');
const git = (root, ...a) => execFileSync('git', a, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
const firstLine = (e) => String(e.stderr || e.message).trim().split('\n')[0];

// CI (GUARD_BASE set) reads the base and throws when it can't; the hooks pass { local: true } for origin/main.
// { optional: true } is for a config that switches a guard on: absent on a base that is there, the PR's copy stands in
// (the PR that adopts the guard), with a note; absent there too, it returns null.
function readBaseJson(root, rel, { local = false, optional = false } = {}) {
  const fixture = path.join(root, '.guard-base', rel);
  if (inFixture(root) && fs.existsSync(fixture)) return JSON.parse(fs.readFileSync(fixture, 'utf8'));
  const show = (ref) => JSON.parse(git(root, 'show', `${ref}:${rel}`));
  const base = process.env.GUARD_BASE;
  if (base) {
    let text;
    try { text = git(root, 'show', `${base}:${rel}`); } catch (e) {
      // The base is there and lacks the file: absent, not unreadable. A missing base still throws.
      let absent = false;
      if (optional) try { absent = git(root, 'ls-tree', '--full-tree', '--name-only', `${base}^{commit}`, '--', rel) === ''; } catch { /* no base: throw below */ }
      if (!absent) throw new Error(`cannot read ${rel} from ${base} (${firstLine(e)}): fetch the base branch (CI checks out with fetch-depth 0)`);
      if (fs.existsSync(path.join(root, rel))) console.error(`note: ${base} has no ${rel} yet, so this PR's copy decides`);
    }
    if (text !== undefined) return JSON.parse(text);
  }
  if (local) {
    try { return show('origin/main'); } catch { console.error(`note: ${rel} is not on origin/main here, so the working-tree copy decides`); }
  }
  const file = path.join(root, rel);
  if (optional && !fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

// The files this change touches: the committed diff from the merge-base with GUARD_BASE (else origin/main), plus
// uncommitted edits. `diff` is the guard's own `git diff` flags. Fails closed: with GUARD_BASE set, a diff that can't
// be computed throws; only a local run (GUARD_BASE unset) with no origin/main gets [] and a note.
function changedFiles(root, { diff = ['--no-renames'] } = {}) {
  const listed = path.join(root, '.guard-changed-files'); // fixtures list their "changed" files here
  if (inFixture(root) && fs.existsSync(listed)) return fs.readFileSync(listed, 'utf8').split('\n').filter(Boolean);
  const base = process.env.GUARD_BASE || 'origin/main';
  let from;
  try { from = git(root, 'merge-base', base, 'HEAD'); } catch (e) {
    if (process.env.GUARD_BASE) throw new Error(`cannot compare with ${base} (${firstLine(e)}): fetch it (CI checks out with fetch-depth 0)`);
    console.error(`no ${base} to compare with; nothing checked (CI sets GUARD_BASE on pull requests)`);
    return [];
  }
  const committed = git(root, 'diff', '--name-only', ...diff, from, 'HEAD').split('\n');
  const working = git(root, 'diff', '--name-only', ...diff, 'HEAD').split('\n');
  return [...new Set([...committed, ...working])].filter(Boolean);
}

module.exports = { readBaseJson, changedFiles, inFixture };
