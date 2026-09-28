---
name: enable-security-audit-gate
description: "Turn the security-audit suite on for ONE project. Writes the audit gate into the project's openspec/config.yaml as native OpenSpec operations guidance (operations.apply.guidance + operations.archive.guidance), which `openspec update` never touches; optionally adds a hard verdict check as a git pre-commit or Claude Code PreToolUse hook; migrates a project off the legacy inline patch of the generated openspec-apply-change / openspec-archive-change skills. Use when the user says 'enable the security audit gate', 'turn on security audits here', 'set up the audit gate for this project', 'install the security suite in this repo', 'make the audit run before archive', 'switch the gate to autofix', 'disable the gate', or reports that openspec update removed the audit step."
license: MIT
metadata:
  author: rdcastor
  version: "1.1"
---

Enable, reconfigure, or disable the security-audit gate in the current project.

## Why the gate lives in `openspec/config.yaml`

The suite is installed once, globally, but audits are opt-in per project. The opt-in is the project's own OpenSpec configuration: `operations.apply.guidance` and `operations.archive.guidance` (OpenSpec 1.7 or newer) come back from `openspec instructions apply|archive --json` as `operationGuidance`, and the generated `openspec-apply-change` / `openspec-archive-change` skills read and follow those entries. Because the entries live in the project's config rather than in generated files, `openspec update` cannot remove them, every harness that runs the OpenSpec skills sees the same gate, and a project without the entries has no gate at all.

Guidance is advisory by OpenSpec's design: a prompt-level contract, not an enforced check. For an enforced stop this skill can also wire `scripts/check_verdict.py` as a hook (step 6). OpenSpec has no lifecycle hooks of its own yet (open request Fission-AI/OpenSpec#1910, `beforeArchive` / `afterSync`); when they ship, the same script becomes the `beforeArchive` command.

## Input

- `--policy ask|autofix`: how the gate reacts to a non-SAFE verdict. `ask` (default) surfaces the findings and asks the user whether to fix now, defer, or override. `autofix` fixes every open finding above Low inline with a regression test and re-audits; the gate is met by SAFE_TO_PROCEED or by PROCEED_WITH_FIXES whose open findings are all Low/Info, which are recorded as tracked work for the next release instead of pausing ("Lows never hold a release"); only an explicit, recorded user decision leaves a finding above Low unfixed. If `.security-audit.yaml` sets `gate_policy`, that is the default.
- `--remove`: take the gate out again.
- `--enforce git|claude-code`: also install the hard verdict check (optional, step 6).

## Steps

1. **Check preconditions**

   - The project has an OpenSpec root: `openspec list --json` returns a `root` object. If not, stop: this gate is OpenSpec-native. For a non-OpenSpec project offer `.security-audit.yaml` (see `security-audit/references/project-profile.md`) plus manual `security-audit` runs, and optionally the git hook from step 6.
   - `openspec --version` is at least 1.7.0 (operations guidance). Below that, or well behind the latest release, recommend `npm install -g @fission-ai/openspec@latest` and ask before running it: it changes a global tool.
   - The `security-audit` skill is reachable: `~/.claude/skills/security-audit/SKILL.md` (global install) or `.claude/skills/security-audit/SKILL.md` (project copy). If neither exists, say how to install the suite and stop.

2. **Dry-run the change**

   ```bash
   python "<this skill's folder>/scripts/gate_config.py" --project . --policy ask
   ```

   Without `--apply` the script reports the state of `openspec/config.yaml` (`absent`, `present`, `partial`, `policy-mismatch`, or `outdated` when the entries are from an older suite version) and prints exactly what it would insert or replace. It preserves comments and ordering: with no `operations:` block it appends one; with one, it adds the two entries under the existing `apply:` / `archive:` guidance lists. If the structure is one it will not touch safely (flow-style lists, anchors, a `guidance` value that is not a list) it exits 2 and prints the entries so you can place them by hand from `references/gate-guidance.md`.

3. **Apply**

   ```bash
   python "<this skill's folder>/scripts/gate_config.py" --project . --policy ask --apply
   ```

   The script writes the file, re-parses it the way the CLI does, and restores the original if the entries did not land. Show the user `git diff openspec/config.yaml`.

4. **Verify through OpenSpec itself**

   If an active change exists (`openspec list --json`), run `openspec instructions archive --change "<name>" --json` and confirm `operationGuidance` carries both entries and that the CLI printed no `Invalid 'operations'` warning. Without an active change, `gate_config.py --project . --check` re-parses the file and exits 0 only when both entries are present and current; it reports the configured policy and asserts one only when `--policy` (or `gate_policy` in `.security-audit.yaml`) is given.

5. **Migrate a project off the suite 1.x inline patch**

   - If `.claude/skills/openspec-apply-change/SKILL.md` or `.claude/skills/openspec-archive-change/SKILL.md` (or their `.codex` / `.gemini` / `.agents` mirrors) mention `security-audit`, they carry the old hand-patched gate. With the config entries in place, ask the user before running `openspec update`: it regenerates those files cleanly and the gate keeps working from the config. Never edit generated files by hand.
   - Delete project-local copies of `restore-openspec-audit-gate/` from every skills directory; the skill no longer exists.
   - If the project keeps its own copies of `security-audit/`, `prepare-full-codebase-security-audit/` or `remediate-security-findings/` while the suite is also installed globally, say they are duplicates that will drift and recommend removing them or replacing them with the project's pointer-stub convention. Leave them alone unless asked; the repo's own rules decide how skills are mirrored.
   - If the rules file says "run restore-openspec-audit-gate after openspec update", replace that sentence with a pointer to this skill (keep `CLAUDE.md` and `AGENTS.md` identical where both exist).

6. **Optional: enforce the verdict with a hook**

   Guidance asks the agent to run the audit; a hook refuses to archive or commit without a SAFE sidecar. `scripts/check_verdict.py` reads `openspec/changes/<name>/security-audit.json` and exits 0 only for `SAFE_TO_PROCEED` (1: BLOCK or PROCEED_WITH_FIXES; 3: no sidecar; 4: stale, HEAD moved past the audited commit with code changes in between; 5: usage error). Copy the script into the project first so the hook path is repo-relative and works on every machine (`.claude/hooks/check_security_verdict.py` for Claude Code, `scripts/check_security_verdict.py` otherwise), then wire it the way the user picked:

   - **git pre-commit** (any harness): `--staged` checks every `openspec/changes/archive/*/security-audit.json` the commit stages, and fails when an archived change has no sidecar. Snippet in `references/gate-guidance.md`. Under the `autofix` policy pass `--allow-low` so a report with only Low/Info findings open passes, matching the gate text.
   - **Claude Code PreToolUse hook** (Claude Code only): `--from-hook` reads the tool call from stdin, acts only when the Bash command runs `openspec archive <name>` or moves `openspec/changes/<name>` into `archive/`, and exits 2 to block with the reason. Write the entry into the project's `.claude/settings.json` (never the user's global settings) and show it before saving. Snippet in `references/gate-guidance.md`.
   - **OpenSpec `beforeArchive`**, once OpenSpec ships lifecycle hooks: the same script, same exit codes.

   Install only the hook the user explicitly chose; hooks change what the harness will refuse to do.

7. **Name the gate in the project's rules file**

   Add a short "Security audit gate" section to the project's rules file (`CLAUDE.md` / `AGENTS.md`; keep the pair identical if both exist): where the gate lives (`openspec/config.yaml`), the policy, the hook if any, and "re-run `enable-security-audit-gate` to change it". Under ten lines; the config is the source of truth. This is how anyone reading only the rules file, human or agent, knows the project opted in.

8. **Report**

   What changed in `openspec/config.yaml` (the diff), the policy, the verification result, hooks installed or none, migration steps taken, and how to undo (`--remove`). Do not commit; the repo's own rules decide when.

## Removing or changing the gate

`--remove` deletes the suite's entries (and any `guidance:`, `apply:`, `archive:` or `operations:` key left empty by that), re-parses, and shows the diff. To switch policy run again with the new `--policy`; the script replaces the old entries in place. After a suite upgrade that changed the entry text, `--check` reports `outdated` and `--apply` with the project's policy replaces the entries; nothing else in the file moves. Hooks are removed by hand from wherever step 6 put them; that step's report says where.

## Guardrails

- Touch only `openspec/config.yaml` (and, when asked, the rules file, `.claude/settings.json`, `.git/hooks/pre-commit`, and the copied checker script). Never edit generated OpenSpec skill files.
- Never run `openspec update` or `npm install -g` without asking: both change files outside this project's config.
- Idempotent: running twice leaves one copy of each entry.
- The policy in `openspec/config.yaml` and `gate_policy` in `.security-audit.yaml` must agree; if they differ, say so and update the profile to match the choice just made.
