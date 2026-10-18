#!/usr/bin/env node
// Usage gate (spec VOI-100): stops cloud threads before the account's usage limit runs out.
// 1. PreToolUse hook on every tool: reads the shared usage reading and allows, warns or denies (exit 2, stderr to Claude).
// 2. UserPromptSubmit hook: only adds the same state as context.
// 3. `record <5h utilization> <5h resetsAt> <7d utilization> <7d resetsAt>`: writes a fresh reading, taken from the
//    thread's own latest `rate_limit_event` (list_events), whose unifiedWindows hold these four numbers.
// The working threads keep the reading fresh themselves, so idle costs nothing. Pausing and resuming:
// docs/agents/usage-pause.md. The numbers below are Petter's (2026-10-18) and live only here.
'use strict';
const fs = require('fs');
const path = require('path');

const STOP = 0.95;
const WARN = 0.9;
const MAX_AGE_S = 120;

const SHARED = process.env.PROJECT_FILES || '/mnt/project-files';
const FILE = path.join(SHARED, '.usage', 'state.json');
const WINDOWS = { five_hour: 'five-hour', seven_day: 'weekly' };
const PAUSE_DOC = 'docs/agents/usage-pause.md';
const RECORD = 'node scripts/usage-gate.js record <five_hour.utilization> <five_hour.resetsAt> <seven_day.utilization> <seven_day.resetsAt>';

// Tools a thread may always use, so it can say why it stopped (Hard rule 3).
const ALWAYS = new Set(['mcp__hearthbot__reply', 'mcp__hearthbot__update_status', 'ToolSearch']);
const REFRESH = new Set(['mcp__claude-code-remote__list_events', 'mcp__claude-code-remote__get_session']);
const HANDOFF = new Set([
  'mcp__github__create_pull_request', 'mcp__github__update_pull_request', 'mcp__github__pull_request_read',
  'mcp__github__disable_pr_auto_merge', 'mcp__claude-code-remote__send_later',
]);
const RECORD_CMD = /^node scripts\/usage-gate\.js record( [0-9.]+){4}$/;
const HANDOFF_CMD = /^(git (add|commit|push|status|log|diff|fetch|rev-parse|branch|show)\b.*|linearis issues discuss\b.*)$/;

const pct = (u) => `${Math.round(u * 100)}%`;
const stockholm = (s) => new Date(s * 1000).toLocaleString('sv-SE', { timeZone: 'Europe/Stockholm', dateStyle: 'short', timeStyle: 'short' });

// A Bash command passes when every `&&` part is a `cd` or matches; any other shell operator fails it.
function bashOk(cmd, re) {
  if (typeof cmd !== 'string' || /[;|`<>\n]|\$\(/.test(cmd.replace(/&&/g, ''))) return false;
  return cmd.split('&&').every((part) => /^cd \S+$/.test(part.trim()) || re.test(part.trim()));
}

function readState(now) {
  let r;
  try { r = JSON.parse(fs.readFileSync(FILE, 'utf8')); } catch (e) {
    return { kind: 'refresh', why: e.code === 'ENOENT' ? 'there is no usage reading yet' : `the usage reading cannot be read (${e.message})` };
  }
  const bad = Object.keys(WINDOWS).find((w) => !(Number.isFinite(r?.[w]?.utilization) && Number.isFinite(r?.[w]?.resets_at)));
  if (bad || !Number.isFinite(r?.read_at)) return { kind: 'refresh', why: 'the usage reading is malformed' };
  const age = now - r.read_at;
  if (age > MAX_AGE_S || age < -60) return { kind: 'refresh', why: `the usage reading is ${Math.round(age)} s old (at most ${MAX_AGE_S} s)` };
  // A window past its reset counts as zero, so a pause lapses by itself.
  const live = Object.keys(WINDOWS).map((w) => ({ w, u: now < r[w].resets_at ? r[w].utilization : 0, reset: r[w].resets_at }))
    .sort((a, b) => b.u - a.u)[0];
  const at = `${WINDOWS[live.w]} usage at ${pct(live.u)}, reset ${stockholm(live.reset)} Stockholm time`;
  if (live.u >= STOP) return { kind: 'stop', why: at };
  if (live.u >= WARN) return { kind: 'warn', why: at };
  return { kind: 'ok' };
}

function decide(input, now) {
  const tool = input.tool_name;
  const cmd = tool === 'Bash' ? input.tool_input?.command : undefined;
  if (ALWAYS.has(tool) || REFRESH.has(tool) || bashOk(cmd, RECORD_CMD)) return { allow: true };
  const s = readState(now);
  if (s.kind === 'ok') return { allow: true };
  if (s.kind === 'warn') return { allow: true, context: `Usage gate: ${s.why} (stop line ${pct(STOP)}). Finish the current step and prepare the handoff in ${PAUSE_DOC} § Pausing.` };
  if (s.kind === 'refresh') return { allow: false, why: `Usage gate: ${s.why}. Refresh it: read your own session's newest rate_limit_event with mcp__claude-code-remote__list_events (kinds ["rate_limit_event"], your session id from get_session), then run \`${RECORD}\` from the repo root with the four numbers from its unifiedWindows.` };
  if (HANDOFF.has(tool) || bashOk(cmd, HANDOFF_CMD)) return { allow: true };
  return { allow: false, why: `Usage gate: ${s.why}, at or over the stop line ${pct(STOP)}. Pause now: follow ${PAUSE_DOC} § Pausing (commit and push, draft PR with the Paused block, ticket comment, restart at the reset plus five minutes, one-line reply), then end the turn. Only those steps are allowed.` };
}

function record(args, now) {
  const n = args.map(Number);
  if (n.length !== 4 || !n.every(Number.isFinite) || n[0] < 0 || n[0] > 1 || n[2] < 0 || n[2] > 1) {
    console.error(`usage: ${RECORD} (utilization 0 to 1, resetsAt in Unix seconds)`);
    process.exit(1);
  }
  const reading = { five_hour: { utilization: n[0], resets_at: n[1] }, seven_day: { utilization: n[2], resets_at: n[3] }, read_at: now, session: process.env.CLAUDE_CODE_SESSION_ID || null };
  fs.mkdirSync(path.dirname(FILE), { recursive: true });
  const tmp = `${FILE}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(reading)); // write whole, then rename, so a reader never sees half a file
  fs.renameSync(tmp, FILE);
  console.log(`Recorded: five-hour ${pct(n[0])}, weekly ${pct(n[2])}.`);
}

const now = Date.now() / 1000;
const remote = process.env.CLAUDE_CODE_REMOTE === 'true' && fs.existsSync(SHARED); // only Projects cloud threads share a reading
if (process.argv[2] === 'record') record(process.argv.slice(3), now);
else if (remote) {
  let input;
  try { input = JSON.parse(fs.readFileSync(0, 'utf8')); } catch (e) { console.error(`Usage gate: cannot read the hook input (${e.message}).`); process.exit(2); }
  if (input.hook_event_name === 'UserPromptSubmit') {
    const s = readState(now);
    if (s.kind !== 'ok') console.log(`Usage gate: ${s.why}.${s.kind === 'stop' ? ` Pause: ${PAUSE_DOC} § Pausing.` : ''}`);
  } else {
    const d = decide(input, now);
    if (!d.allow) { console.error(d.why); process.exit(2); }
    if (d.context) console.log(JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', additionalContext: d.context } }));
  }
}
