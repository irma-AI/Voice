#!/usr/bin/env node
// Keeps room under Linear's free-plan cap (VOI-254): a workspace holding CAP issues that are not archived refuses new ones
// ("usage limit exceeded"); archived ones do not count (seen 2026-10-20). Archives the oldest closed issues (completed or
// canceled), never deletes, until there is room for ROOM new ones. `--dry-run` only says what it would archive.
// The cap counts the whole workspace, but only team TEAM's own closed issues are archived: other teams are not ours to
// change (docs/agents/issue-tracker.md). Run as `make linear-room` before creating issues. Uses the session's LINEAR_API_TOKEN.

const CAP = 250;
const ROOM = Number(process.env.ROOM || 20);
const TEAM = "VOI";
const dryRun = process.argv.includes("--dry-run");
const token = process.env.LINEAR_API_TOKEN;

async function graphql(query, variables = {}) {
  const answer = await fetch("https://api.linear.app/graphql", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: token },
    body: JSON.stringify({ query, variables }),
  });
  const body = await answer.json();
  if (!answer.ok || body.errors) throw new Error(`Linear answered ${answer.status}: ${JSON.stringify(body.errors || body)}`);
  return body.data;
}

async function unarchived() {
  const issues = [];
  let after = null;
  do {
    const { issues: page } = await graphql(
      `query($after: String) { issues(first: 250, after: $after) {
         nodes { id identifier createdAt state { type } team { key } }
         pageInfo { hasNextPage endCursor } } }`,
      { after },
    );
    issues.push(...page.nodes);
    after = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
  } while (after);
  return issues;
}

async function main() {
  if (!token) throw new Error("LINEAR_API_TOKEN is not set: no Linear access in this session");
  const issues = await unarchived();
  const over = issues.length + ROOM - CAP;
  if (over <= 0) {
    console.log(`linear-room: ${issues.length} of ${CAP} issues are not archived; room for ${CAP - issues.length}`);
    return;
  }
  const oldestClosed = issues
    .filter((i) => i.team.key === TEAM && (i.state.type === "completed" || i.state.type === "canceled"))
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
    .slice(0, over);
  for (const issue of oldestClosed) {
    if (!dryRun) await graphql(`mutation($id: String!) { issueArchive(id: $id) { success } }`, { id: issue.id });
  }
  const names = oldestClosed.map((i) => i.identifier).join(", ");
  console.log(`linear-room: ${dryRun ? "would archive" : "archived"} ${oldestClosed.length}: ${names}`);
  if (oldestClosed.length < over) {
    throw new Error(
      `only ${oldestClosed.length} closed ${TEAM} issues to archive, ${over} needed: archive other teams' closed issues or open ones in Linear, or raise the plan (its cap is ${CAP})`,
    );
  }
}

main().catch((error) => {
  console.error(`linear-room: ${error.message}`);
  process.exit(1);
});
