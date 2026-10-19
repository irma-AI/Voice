#!/usr/bin/env node
// `make archive-decisions` (VOI-137): moves DECISIONS.md lines older than KEEP_DAYS (default 7) into
// docs/decisions/<yyyy-mm>.md, so a grep of DECISIONS.md shows this week and the questions still waiting.
// Kept: the header, every line dated within KEEP_DAYS of today, and every ESCALATED and RESOLVED line of a date
// that has fewer RESOLVED answers than ESCALATED questions (archive files counted too).
// shortcut: questions and answers are matched by date and count, not by subject, so a date with one open question
// keeps all its escalations; write a question id into both lines if that ever keeps too much.
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = process.env.ARCHIVE_ROOT || process.cwd();
const KEEP_DAYS = Number(process.env.KEEP_DAYS ?? 7);
const today = process.env.ARCHIVE_TODAY || new Date().toISOString().slice(0, 10);
const cutoff = new Date(Date.parse(today) - KEEP_DAYS * 864e5).toISOString().slice(0, 10);
const DIR = path.join(ROOT, 'docs', 'decisions');
const FILE = path.join(ROOT, 'DECISIONS.md');

const dated = (line) => (line.match(/^\[(\d{4}-\d{2}-\d{2})\] /) || [])[1];
const asks = (line) => (line.match(/^\[(\d{4}-\d{2}-\d{2})\] ESCALATED/) || [])[1];
const answers = (line) => (line.match(/^\[\d{4}-\d{2}-\d{2}\] RESOLVED (\d{4}-\d{2}-\d{2})/) || [])[1];

const lines = fs.readFileSync(FILE, 'utf8').split('\n');
const archived = fs.existsSync(DIR) ? fs.readdirSync(DIR).filter((f) => f.endsWith('.md')).flatMap((f) => fs.readFileSync(path.join(DIR, f), 'utf8').split('\n')) : [];
const count = (pick, all) => all.reduce((n, l) => { const d = pick(l); if (d) n[d] = (n[d] || 0) + 1; return n; }, {});
const asked = count(asks, lines.concat(archived));
const answered = count(answers, lines.concat(archived));
const waiting = (d) => (asked[d] || 0) > (answered[d] || 0);

const keep = [];
const move = {};
for (const line of lines) {
  const d = dated(line);
  const question = asks(line) || answers(line);
  if (!d || d >= cutoff || (question && waiting(question))) { keep.push(line); continue; }
  (move[d.slice(0, 7)] ||= []).push(line);
}
fs.mkdirSync(DIR, { recursive: true });
for (const [month, moved] of Object.entries(move)) {
  const file = path.join(DIR, `${month}.md`);
  const head = fs.existsSync(file) ? '' : `# Decisions, ${month}\n\nMoved from DECISIONS.md by \`make archive-decisions\` once older than a week; open questions stay there.\n\n`;
  fs.appendFileSync(file, head + moved.join('\n') + '\n');
}
fs.writeFileSync(FILE, keep.join('\n').replace(/\n{3,}/g, '\n\n'));
const total = Object.values(move).reduce((n, m) => n + m.length, 0);
console.log(`archived ${total} lines older than ${cutoff}; DECISIONS.md keeps ${keep.length}`);
