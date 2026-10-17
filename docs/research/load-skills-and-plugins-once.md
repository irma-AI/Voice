# Can a skill or plugin that lives in the repo and on the claude.ai account load only once?

Written 2026-10-17. Every page below was read 2026-10-17. The effect in a fresh cloud session is **not checked** yet; `claude plugin list` in this session showed the three plugins as disabled after the setting was added.

## What happened

Every session and subagent got the ponytail rules twice at start:

- Copy A, about 3.3 KB: the claude.ai account plugin `ponytail@synced`, version 5.3.2, downloaded to `~/.claude/plugins/synced/`.
- Copy B, about 5.2 KB: the repo's own hooks in `.claude/hooks/ponytail-*.js`, wired in `.claude/settings.json`. Vendored 2026-10-13 by `scripts/vendor-skills.sh` and never refreshed. Upstream was already at 5.3.2 (released 2026-10-17, `DietrichGebert/ponytail`).

The same happens for the other two sources the repo vendors: `impeccable@synced` and `mattpocock-skills@synced` load their skills as `impeccable:impeccable`, `mattpocock-skills:tdd` and so on beside the repo's own. `humanizer@synced` is not vendored, so it is not a duplicate.

## What Claude Code does

- **Plugin skills never replace repo skills.** "Plugin skill and a skill at any local location: Both load, because plugin skills are namespaced as `/plugin-name:skill-name`." [Skills, "Resolve skills that share a name"](https://code.claude.com/docs/en/skills). The precedence order (enterprise over personal over project) only applies between non-plugin skills.
- **Hooks are added, not replaced.** "When a plugin is enabled, its hooks merge with your user and project hooks." Identical handlers are deduplicated only across settings files: "A plugin's or skill's copy of the same handler stays separate." [Hooks reference](https://code.claude.com/docs/en/hooks).
- **A synced plugin loses name conflicts only against another plugin.** Order: managed, `--plugin-dir`, installed marketplace plugin, skills-directory plugin, then "a plugin synced from claude.ai". [Plugin loading, "Name conflicts"](https://code.claude.com/docs/en/plugins/loading). The repo's vendored skills and hooks are not plugins, so no conflict arises and both copies load.
- **The repo can switch one synced plugin off.** "To keep the plugin out of a project in every environment, set the same key in the project's committed `.claude/settings.json`", with the key `"<name>@synced": false` under `enabledPlugins`. [Plugin loading, "Control which synced plugins load"](https://code.claude.com/docs/en/plugins/loading#synced-plugins). `enabledPlugins` is read from any settings file, project over user. [Settings reference, `enabledPlugins`](https://code.claude.com/docs/en/settings-reference#enabledplugins).
- **The repo cannot switch the sync off.** `syncClaudeAiPlugins` and `syncClaudeAiSkills` are "User, local, or managed" scope: "A repository can't turn it off for you", and a `false` in `.claude/settings.json` is ignored. [Settings reference](https://code.claude.com/docs/en/settings-reference#syncclaudeaiplugins), [Settings files and precedence, exceptions](https://code.claude.com/docs/en/settings).
- **Cloud sessions read the committed file.** In a session with one repository, `.claude/settings.json` hooks and settings apply; user and local settings are not read. [Cloud environments, "What carries over"](https://code.claude.com/docs/en/cloud-environments#what-carries-over-from-your-setup), [Settings in cloud sessions](https://code.claude.com/docs/en/settings#settings-in-cloud-sessions). The same page says a cloud session does not install plugins a repo turns on; this only concerns turning on, and a `false` needs no install.

## What this means for Voice

- One line per duplicated source in the committed `.claude/settings.json`: `ponytail@synced`, `impeccable@synced`, `mattpocock-skills@synced`, all `false`. The repo copy then is the only one.
- Synced account **skills** (`~/.claude/skills/synced/`) cannot be switched off by the repo, but none of them shares a name with a repo skill (checked by listing both folders on 2026-10-17), and personal skills would beat project ones of the same name, so a future clash would need a rename.
- Only Petter (user or managed settings, or the claude.ai plugin page) can stop the downloads or remove the account plugins altogether; that is not needed for this.
- A new vendored source that also exists as an account plugin needs its own `enabledPlugins` row. There is no check for this: the account's plugin list is not visible to CI.

## Not checked

- That a fresh cloud session starts with one ponytail copy: only the next session shows it.
- Whether the vendored impeccable and mattpocock skills are current: only ponytail was refreshed here.
