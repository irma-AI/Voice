#!/usr/bin/env node
// Guard: a change to a migration ships with a real-store test, or the migration says why not
// (`db-test: skip <reason>`). Adopted by adding scripts/checks/db-test-required.json,
// { "migrations": [globs], "tests": [globs] } (the stack recipe has one); without it the guard is off.
// The config is read from the base branch and the diff fails closed in CI (scripts/base-config.js): a PR cannot
// loosen or delete the config that checks it. Compares with $GUARD_BASE (CI sets origin/<base branch>), else origin/main.
'use strict';
const fs = require('fs');
const path = require('path');
const { readBaseJson, changedFiles } = require(path.join(__dirname, '..', '..', 'base-config.js'));
const ROOT = process.env.GUARD_ROOT || process.cwd();
const CONFIG = 'scripts/checks/db-test-required.json';

let cfg, changed;
try {
  cfg = readBaseJson(ROOT, CONFIG, { optional: true });
  if (cfg !== null) changed = changedFiles(ROOT, { diff: ['--diff-filter=AMR'] });
} catch (e) {
  console.log('#scanned 1');
  console.log(`base\t${e.message}`);
  process.exit(1);
}
if (cfg === null) {
  console.log('#scanned 1');
  console.error(`not adopted: add ${CONFIG} to require a real-store test with each migration change`);
  process.exit(0);
}
const matches = (globs) => (f) => globs.some((g) => path.matchesGlob(f, g));

console.log(`#scanned ${changed.length + 1}`); // +1: the change set itself, which may be empty
if (changed.some(matches(cfg.tests))) process.exit();
for (const f of changed.filter(matches(cfg.migrations))) {
  const abs = path.join(ROOT, f);
  if (!fs.existsSync(abs) || /db-test:\s*skip\s+\S+/.test(fs.readFileSync(abs, 'utf8'))) continue;
  console.log(`${f}\t${f} changes the schema with no real-store test in this change: add one (.claude/rules/tests.md), or write \`db-test: skip <reason>\` in the migration`);
  process.exitCode = 1;
}
