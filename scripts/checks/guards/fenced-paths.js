#!/usr/bin/env node
// Guard: a pull request that changes a fenced path (the "fenced" key in scripts/low-risk-paths.json,
// today tests/evals/**) needs the label named there, which only Petter adds. CI sets GUARD_BASE on pull
// requests and GUARD_PR_LABELS to the PR's label names as JSON; with GUARD_BASE but no labels it refuses. The fence
// is read from the base branch (scripts/base-config.js).
// Outside a pull-request run (a local make guards) nothing is compared, and a note says so.
'use strict';
const fs = require('fs');
const path = require('path');
const { readBaseJson, changedFiles, inFixture } = require(path.join(__dirname, '..', '..', 'base-config.js'));
const ROOT = process.env.GUARD_ROOT || process.cwd();

// A fixture has `.guard-changed-files` (and `.guard-labels`) in place of a git diff and the CI env.
const listed = path.join(ROOT, '.guard-changed-files');
const fixture = inFixture(ROOT) && fs.existsSync(listed);
if (!fixture && !process.env.GUARD_BASE) {
  console.log('#scanned 1');
  console.error('not a pull-request run (GUARD_BASE unset): the fence is checked in CI only');
  process.exit(0);
}

// The fence as on the base branch, so this PR cannot unfence what it changes.
let label, paths;
try { ({ label, paths } = readBaseJson(ROOT, 'scripts/low-risk-paths.json').fenced); } catch (e) {
  console.log('#scanned 1');
  console.log(`config\t${e.message}`);
  process.exit(1);
}

let labels;
try {
  const raw = fixture
    ? (fs.existsSync(path.join(ROOT, '.guard-labels')) ? fs.readFileSync(path.join(ROOT, '.guard-labels'), 'utf8') : '[]')
    : process.env.GUARD_PR_LABELS || '[]';
  labels = JSON.parse(raw);
  if (!Array.isArray(labels)) throw new Error('not a list');
} catch (e) {
  console.log('#scanned 1');
  console.log(`labels\tcannot read the PR labels (${e.message}): make GUARD_PR_LABELS a JSON list of label names in .github/workflows/ci.yml`);
  process.exit(1);
}


let changed;
try { changed = changedFiles(ROOT); } catch (e) { console.log('#scanned 1'); console.log(`base\t${e.message}`); process.exit(1); }
console.log(`#scanned ${changed.length + 1}`); // +1: the change set itself, which may be empty
if (labels.includes(label)) process.exit(0);
for (const f of changed.filter((f) => paths.some((g) => path.matchesGlob(f, g)))) {
  console.log(`${f}\t${f} is fenced and this PR has no "${label}" label: leave it to Petter to add the label (only he does), or take the change out of this PR`);
  process.exitCode = 1;
}
