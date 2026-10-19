#!/usr/bin/env node
// `make archive-decisions` (VOI-137): moves DECISIONS.md lines older than KEEP_DAYS (default 7) into
// docs/decisions/<yyyy-mm>.md, so a grep of DECISIONS.md shows this week and the questions still waiting.
// Kept: the header, every line dated within KEEP_DAYS of today, and every ESCALATED and RESOLVED line: nothing pairs a
// question with its answer reliably, so a person moves an answered pair to the archive by hand (fails closed).
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = process.env.ARCHIVE_ROOT || process.cwd();
const KEEP_DAYS = Number(process.env.KEEP_DAYS || 7);
const today = process.env.ARCHIVE_TODAY || new Date().toLocaleDateString('sv-SE'); // the local date, as YYYY-MM-DD
const cutoff = new Date(Date.parse(today) - KEEP_DAYS * 864e5).toISOString().slice(0, 10);
const DIR = path.join(ROOT, 'docs', 'decisions');
const FILE = path.join(ROOT, 'DECISIONS.md');

const dated = (line) => (line.match(/^\[(\d{4}-\d{2}-\d{2})\] /) || [])[1];
const question = (line) => /^\[\d{4}-\d{2}-\d{2}\] (ESCALATED|RESOLVED)/.test(line);

const lines = fs.readFileSync(FILE, 'utf8').split('\n');
const keep = [];
const move = {};
for (const line of lines) {
  const d = dated(line);
  if (!d || d >= cutoff || question(line)) { keep.push(line); continue; }
  (move[d.slice(0, 7)] ||= []).push(line);
}
fs.mkdirSync(DIR, { recursive: true });
for (const [month, moved] of Object.entries(move)) {
  const file = path.join(DIR, `${month}.md`);
  const head = fs.existsSync(file) ? '' : `# Decisions, ${month}\n\nMoved from DECISIONS.md by \`make archive-decisions\` (older than its KEEP_DAYS, 7 by default), and answered questions moved by hand.\n\n`;
  fs.appendFileSync(file, head + moved.join('\n') + '\n');
}
fs.writeFileSync(FILE, keep.join('\n').replace(/\n{3,}/g, '\n\n'));
const total = Object.values(move).reduce((n, m) => n + m.length, 0);
console.log(`archived ${total} lines older than ${cutoff}; DECISIONS.md keeps ${keep.length}`);
