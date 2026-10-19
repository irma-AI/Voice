# Guards

`make guards` runs `run.js`: first a self-test of every guard, then the real run. A guard is a `.js` file, run with Node, or an executable file in any language, run through its shebang.

## The guard contract

A guard is one file in `guards/`. It:

1. Scans from `$GUARD_ROOT` (the repo root, or a fixture folder during the self-test).
2. Prints `#scanned <n>`, the number of files or items it checked. A missing line or 0 fails, so a guard that checks nothing can't pass.
3. Prints one line per violation: `<stable id><TAB><message>`. The message ends with the exact fix: the helper to use, the lines to add, the command to run.
4. Exits 1 when it printed a violation, 0 otherwise. Anything on stderr shows as a note.

Every guard has a fixture, `fixtures/<guard name>/`, laid out like a repo, that must make it fail; `fixtures/<guard name>.<case>/` adds another case that must fail too, and a fixture's `.guard-env.json` (`{ "<VAR>": "<value>" }`) sets environment variables for its run. The self-test runs the guard on each first. A guard that reads a pull request's changed files lets the fixture list them in `.guard-changed-files` (and its labels in `.guard-labels`, a JSON list) instead of a git diff and CI's env; these `.guard-*` files count only under `fixtures/`.

## Where a guard reads from

`scripts/base-config.js` is the one place for both:

- **Configuration** (`scripts/low-risk-paths.json`, `scripts/eval-required.json`, `scripts/checks/db-test-required.json`, `scripts/checks/layers.json`): `readBaseJson` reads it from the base branch (`$GUARD_BASE`, which CI sets on pull requests), so a pull request cannot loosen or delete the rule that checks it; with `$GUARD_BASE` unset (a local run) the working-tree copy decides. A fixture's `.guard-base/<path>` stands in for the base, so the fixture can loosen its own copy and still fail. A config that switches a guard on (`{ optional: true }`) and is not on the base yet comes from the pull request that adds it, with a note.
- **Changed files**: `changedFiles(root, { diff })` returns the diff from the merge-base with `$GUARD_BASE` (else origin/main) plus uncommitted edits; `diff` is the guard's own diff flags. With `$GUARD_BASE` set, a diff that cannot be computed fails the guard; only a local run with no origin/main gets no files and a note.

## Baselines

A baseline (`baselines/<name>.json`, `{ "<id>": <allowed count> }`) lets a guard adopt a strict rule while existing violations stay. A new violation, or a higher count, fails. A fixed one also fails until its count is lowered, so the list only gets shorter. `node scripts/checks/run.js --init-baseline <name>` creates a missing baseline from today's violations, and `--report` lists what each baseline still allows, largest first. Raising a baseline is a hand edit with a `DECISIONS.md` line saying why; owner review through `.github/CODEOWNERS` is not enforced: solo maintainer. The `add-baseline` skill walks through adding one.

## Example

A guard that keeps `print()` out of Python app code, so logging goes through the repo's one logger (`ARCHITECTURE.md` § Cross-cutting concerns). Its fixture is `fixtures/no-print/app.py` holding `print(order)`.

```js
#!/usr/bin/env node
// Guard: no print() in app code; log through <your logging module>.
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const ROOT = process.env.GUARD_ROOT || process.cwd();
const files = execFileSync('git', ['ls-files', '-co', '--exclude-standard', '*.py'], { cwd: ROOT, encoding: 'utf8' })
  .split('\n').filter((f) => f && !f.startsWith('scripts/checks/fixtures/') && !f.includes('tests/'));
console.log(`#scanned ${files.length}`);
for (const f of files) fs.readFileSync(path.join(ROOT, f), 'utf8').split('\n').forEach((line, i) => {
  if (/^\s*print\(/.test(line)) { console.log(`${f}\t${f}:${i + 1}: use the logger from <your logging module> instead of print()`); process.exitCode = 1; }
});
```
