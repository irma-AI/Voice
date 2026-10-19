#!/usr/bin/env node
// Guard: DECISIONS.md and its monthly archive (docs/decisions/<yyyy-mm>.md, VOI-137) hold one dated line per decision,
// at most 300 characters.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = process.env.GUARD_ROOT || process.cwd();
const MAX = 300;
const violation = (where, msg) => { console.log(`${where}\t${where}: ${msg}`); process.exitCode = 1; };
const ARCHIVE = 'docs/decisions';
const archive = fs.existsSync(path.join(ROOT, ARCHIVE)) ? fs.readdirSync(path.join(ROOT, ARCHIVE)).filter((f) => f.endsWith('.md')).map((f) => `${ARCHIVE}/${f}`) : [];
const files = ['DECISIONS.md', ...archive].filter((f) => fs.existsSync(path.join(ROOT, f)));
console.log(`#scanned ${files.length}`);
for (const file of files) {
  let started = false;
  fs.readFileSync(path.join(ROOT, file), 'utf8').split('\n').forEach((line, i) => {
    if (!line.trim() || (!started && !line.startsWith('['))) return; // header text before the first entry
    started = true;
    const where = `${file}:${i + 1}`;
    if (!/^\[\d{4}-\d{2}-\d{2}\] ./.test(line)) violation(where, 'not a decision line: write it as "[YYYY-MM-DD] <decision>: <why>"');
    else if (line.length > MAX) violation(where, `${line.length} characters (cap ${MAX}): keep the decision and why here, move detail to the PR body`);
  });
}
