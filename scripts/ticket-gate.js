#!/usr/bin/env node
// PreToolUse hook (Edit|Write|NotebookEdit): denies an edit to a repo file unless the session's ticket is a ready
// Linear ticket (scripts/ticket-check.js). Files in "no_ticket" of scripts/low-risk-paths.json, and files outside
// the repo, need none. The session's ticket is $NEXT_STEP_TICKET, else the id in the file `next-step-ticket` in the
// git dir (/next-step writes it when it starts a ticket), else a PET-<n> in the branch name.
// Fails closed: no ticket, no token or no answer from Linear denies the edit and says why (exit 2, stderr to Claude).
// Known limit: Bash can still write files; the CI guard ticket-required.js is the backstop for those.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { ticketIds, fetchIssue, problem } = require('./ticket-check');

const git = (...a) => execFileSync('git', a, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
const deny = (why) => { console.error(`Edit denied: ${why}`); process.exit(2); };

(async () => {
  let input;
  try { input = JSON.parse(fs.readFileSync(0, 'utf8')); } catch (e) { return deny(`cannot read the hook input (${e.message})`); }
  const target = input.tool_input?.file_path || input.tool_input?.notebook_path;
  if (!target) return deny('the tool call names no file, so the ticket rule cannot be checked');
  const root = git('rev-parse', '--show-toplevel');
  const rel = path.relative(root, path.resolve(input.cwd || root, target));
  if (rel.startsWith('..')) return; // outside the repo: scratch files and memory
  const cfg = JSON.parse(fs.readFileSync(path.join(root, 'scripts', 'low-risk-paths.json'), 'utf8'));
  if (cfg.no_ticket.some((g) => path.matchesGlob(rel, g))) return;

  let id = process.env.NEXT_STEP_TICKET;
  if (!id) { try { id = fs.readFileSync(git('rev-parse', '--git-path', 'next-step-ticket'), 'utf8').trim(); } catch { /* no marker */ } }
  if (!id) id = ticketIds(git('branch', '--show-current'))[0];
  const fix = 'Run the next-step skill. Once its ticket is labelled ready-for-agent, start work with `/next-step PET-<n>`, which records the ticket for this session.';
  if (!id) return deny(`${rel} needs a ready Linear ticket and this session has none. ${fix}`);
  let issue;
  try { issue = await fetchIssue(id); } catch (e) { return deny(`cannot ask Linear about ${id} (${e.message}), so the ticket rule cannot be checked. Fix the Linear access and retry.`); }
  const why = problem(id, issue);
  if (why) deny(`${why}. ${fix}`);
})();
