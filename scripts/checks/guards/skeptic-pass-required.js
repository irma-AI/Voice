#!/usr/bin/env node
// Guard: a pull request that changes money, access or Business-isolation code (the "skeptic_pass" list in
// scripts/low-risk-paths.json) needs a "Skeptic pass" section in its body: the frozen SHA the skeptics read, then
// the counterexamples found or "none found" (the skeptic-pass skill's output). The list is read from the base
// branch (scripts/base-config.js), so a PR cannot drop a file it changes from it. CI sets GUARD_BASE and
// GUARD_PR_TEXT (title, a newline, body) on pull requests; outside a pull-request run (a local make guards)
// nothing is compared, and a note says so. Known limit: the guard sees that the section is there, not that
// skeptics ran or that the SHA is a commit of this PR.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { readBaseJson } = require(path.join(__dirname, '..', '..', 'base-config.js'));
const ROOT = process.env.GUARD_ROOT || process.cwd();

// A fixture has `.guard-changed-files` and `.guard-pr-text` in place of a git diff and the CI env.
const read = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');
const fixture = fs.existsSync(path.join(ROOT, '.guard-changed-files'));
if (!fixture && !process.env.GUARD_BASE) {
  console.log('#scanned 1');
  console.error('not a pull-request run (GUARD_BASE unset): the skeptic pass is checked in CI only');
  process.exit(0);
}

let listed;
try {
  listed = readBaseJson(ROOT, 'scripts/low-risk-paths.json').skeptic_pass;
  if (listed === undefined) {
    // The PR that adds the list is the only one whose base lacks it; this PR's copy stands in, with a trace.
    console.error('the base branch has no "skeptic_pass" list yet: using this PR\'s copy of scripts/low-risk-paths.json');
    listed = JSON.parse(read('scripts/low-risk-paths.json')).skeptic_pass;
  }
} catch (e) {
  console.log('#scanned 1');
  console.log(`config\t${e.message}`);
  process.exit(1);
}
if (!Array.isArray(listed) || !listed.length) {
  console.log('#scanned 1');
  console.log('config\tscripts/low-risk-paths.json has no "skeptic_pass" list: add the paths it guards');
  process.exit(1);
}

function changedFiles() {
  if (fixture) return read('.guard-changed-files').split('\n').filter(Boolean);
  const git = (...a) => execFileSync('git', a, { cwd: ROOT, encoding: 'utf8' }).trim();
  const from = git('merge-base', process.env.GUARD_BASE, 'HEAD');
  // No diff filter and no renames: a deleted or moved listed file counts too.
  return git('diff', '--name-only', '--no-renames', from, 'HEAD').split('\n').filter(Boolean);
}

// The body of the "Skeptic pass" heading, up to the next heading, or null.
function section(text) {
  const m = String(text || '').match(/^#{1,6}[ \t]*skeptic pass[ \t]*\n([\s\S]*?)(?=^#{1,6}[ \t]|(?![\s\S]))/im);
  return m ? m[1] : null;
}

const changed = changedFiles();
console.log(`#scanned ${changed.length + 1}`); // +1: the change set itself, which may be empty
const touched = changed.filter((f) => listed.some((g) => path.matchesGlob(f, g)));
if (!touched.length) process.exit(0);

const body = section(fixture ? read('.guard-pr-text') : process.env.GUARD_PR_TEXT);
const fix = 'run the skeptic-pass skill on the frozen head, then add to the PR body a "## Skeptic pass" section with the SHA they read and the counterexamples found, or "none found"';
if (body === null) {
  console.log(`no-section\t${touched.join(', ')} changed and the PR body has no "Skeptic pass" section: ${fix}`);
  process.exitCode = 1;
} else if (!/\b[0-9a-f]{7,40}\b/i.test(body)) {
  console.log(`no-sha\tthe "Skeptic pass" section names no frozen SHA (7 to 40 hex digits): ${fix}`);
  process.exitCode = 1;
} else if (!/none found|counterexample/i.test(body)) {
  console.log(`no-result\tthe "Skeptic pass" section says neither "none found" nor what the counterexamples were: ${fix}`);
  process.exitCode = 1;
}
