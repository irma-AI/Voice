// The one ticket rule, used by the edit hook (scripts/ticket-gate.js) and the CI guard
// (scripts/checks/guards/ticket-required.js): work needs a ready Linear ticket in team PET, project Voice.
// "Ready" is the label to-tickets and triage put on a ticket (docs/agents/triage-labels.md); a done or
// cancelled ticket backs no new work. Fails closed: no token or no answer from Linear is a problem, not a pass.
// Known limit: Linear can't say who added the label, so an agent that labels its own ticket passes; this
// catches skipped flows and invented ticket numbers, not a deliberate forgery.
'use strict';
const READY = 'ready-for-agent';
const PROJECT = 'Voice';

const ticketIds = (text) => [...new Set(String(text || '').match(/\bPET-\d+\b/gi) || [])].map((s) => s.toUpperCase());

async function fetchIssue(id, token = process.env.LINEAR_API_TOKEN) {
  if (!token) throw new Error('LINEAR_API_TOKEN is not set');
  const res = await fetch('https://api.linear.app/graphql', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: token },
    body: JSON.stringify({
      query: 'query($id:String!){issue(id:$id){identifier project{name} labels{nodes{name}} state{type}}}',
      variables: { id },
    }),
    signal: AbortSignal.timeout(10000),
  });
  if (!res.ok) throw new Error(`Linear answered HTTP ${res.status}`);
  const body = await res.json();
  if (body.errors) {
    if (/^Entity not found/.test(body.errors[0].message)) return null; // the caller says "no such ticket"
    throw new Error(body.errors[0].message);
  }
  return body.data.issue;
}

// Returns why the ticket can't back work, or null when it can.
function problem(id, issue) {
  if (!issue) return `${id} does not exist in Linear`;
  if (issue.project?.name !== PROJECT) return `${id} is not in the Linear project ${PROJECT}`;
  if (!issue.labels.nodes.some((l) => l.name === READY)) return `${id} is not labelled ${READY}: it has not been through triage or to-tickets yet`;
  if (['completed', 'canceled'].includes(issue.state.type)) return `${id} is already done or cancelled`;
  return null;
}

module.exports = { ticketIds, fetchIssue, problem, READY };
