---
name: remediate-security-findings
description: "Turn a security-audit report into an OpenSpec remediation change. Reads security-audit.json (or .md) from a change, or findings-report.json from a full-codebase audit run, maps each open Critical/High/Medium finding to concrete tasks, and produces proposal + design + tasks ready for /opsx:apply. Use when the user says 'remediate security findings', 'fix the audit findings', 'make a change for the security report', or after a security-audit run in a project that enabled the suite. Does not modify code itself."
license: MIT
metadata:
  author: rdcastor
  version: "1.2"
---

Generate an OpenSpec change that remediates the findings of a security audit.

## Input

Optionally specify:
- A path to a `security-audit.json` / `security-audit.md` (per-change audit) or `findings-report.json` / `findings-report.md` (full-codebase run).
- An OpenSpec change name whose audit report to read (`<changeRoot>/security-audit.json`).
- Nothing: infer the report from the conversation or ask.

This skill runs in projects that enabled the security-audit suite or when the user asks by name; it never runs on its own.

## Steps

1. **Locate the audit report**

   In order:
   - The argument (file path or change name).
   - Conversation context: an audit that just ran.
   - `openspec/changes/*/security-audit.json`: use it if exactly one exists.
   - `openspec/changes/*/findings/*/findings-report.json`: the newest run that has a report.
   - Otherwise ask which report to remediate.

   Read the JSON as the authoritative findings list (IDs, severity, confidence, file, line, status) and the markdown for the remediation snippets. Ignore findings whose `status` is `resolved`. Finding IDs are `F1`, `F2`, ... for a per-change audit and `C03-F2` style for a merged full-codebase report; keep them exactly, other people grep for them.

2. **Determine the change name**

   - Source change `foo-bar`: propose `remediate-foo-bar`.
   - Full-codebase run: `security-remediation-<YYYY-MM-DD>` of the run.
   - Existing directory: append `-v2`, `-v3`, ...

   Announce "Creating change: `<name>`" and confirm the project has an OpenSpec root first (`openspec list --json`).

3. **Filter findings by severity**

   - **In scope** (default): Critical, High, Medium.
   - **Deferred**: Low and Info, listed in the proposal's Non-Goals; no tasks unless the user asks.

   If nothing is in scope (verdict `SAFE_TO_PROCEED`, or only Low/Info left), say so and stop: no change is needed.

4. **Create the change**

   ```bash
   openspec new change "<name>"
   ```

   `openspec new change` is the scaffold command (`openspec new --help` lists it). `openspec change` is a different, read-only group (show, list, validate), not a synonym; hand-scaffolding is never needed. Delta specs go under `specs/<capability-path>/spec.md`: keep an existing capability's full path, and give a new capability the place the project's `openspec/specs/` layout uses (flat or nested), because the archive-time sync matches on that path.

   Before writing each artifact, fetch its instructions so the project's `rules` and `context` apply:

   ```bash
   openspec instructions <artifact-id> --change "<name>" --json
   ```

5. **Write `proposal.md`**

   ```
   ## Why
   <1–2 sentences: which vulnerability classes / attack surface the audit found exposed; audit path and commit>

   ## What Changes
   | ID | Severity | Confidence | Title | OWASP / CWE | Location |
   |----|----------|------------|-------|-------------|----------|
   | F1 | High     | High       | ...   | A01:2021 / CWE-284 | src/api.py:84 |

   <For each finding: one paragraph describing the fix strategy, referencing the audit's remediation snippet when there is one.>

   ## Non-Goals
   - Deferred Low/Info findings: <IDs and titles>
   - <anything explicitly out of scope>

   ## Phases
   Phase 1: Critical/High fixes (the minimum needed to lift a BLOCK)
   Phase 2: Medium fixes
   Phase 3: Tests, verification, re-audit
   ```

6. **Write `design.md`**

   One "Decision" section per finding: the vulnerable pattern (before), the fixed pattern (after, copied from the audit's remediation snippet verbatim when present), and trade-offs. Show the actual code change, not a description of it. When the audit had no snippet, state what the fix must achieve and note that the implementer derives the patch.

7. **Write `tasks.md`**

   One task per finding, grouped by phase, each independently completable. Each finding's task carries its own regression test, so a task is done only when the fix and the test that fails on the old code both exist; the last phase holds only cross-cutting checks. Projects whose task rules say otherwise win.

   ```markdown
   ## Phase 1 — Critical / High

   - [ ] 1.1 <file>:<function>: <what to change>, plus regression test <test name> that exercises the real failure path (not a mock that hides it) and fails on the old code [F1]; verify: <test command>
   - [ ] 1.2 ...

   ## Phase 2 — Medium

   - [ ] 2.1 ... plus regression test <test name> [F3]; verify: ...

   ## Phase 3 — Cross-cutting verification

   - [ ] 3.1 Run the project's own checks (lint / type-check / full test suite as the rules file or CI defines them); all must pass
   - [ ] 3.2 Re-run `security-audit` in re-audit mode against <audit path>; every addressed finding must show `status: resolved`, and the verdict must be SAFE_TO_PROCEED or PROCEED_WITH_FIXES with only the deferred Low/Info findings open
   - [ ] 3.3 Commit following the repository's convention (e.g. `security: remediate F1, F3`), never bypassing hooks
   ```

8. **Summarise**

   ```
   ## Remediation Change Created: <name>

   **Source audit:** <path> (commit <sha>)
   **Findings addressed:** <N> (Critical: X, High: Y, Medium: Z)
   **Deferred (Low/Info):** <M>

   ### Findings → Tasks
   - F1 (High) → tasks 1.1, 3.1
   - ...

   Ready to implement: /opsx:apply <name>
   ```

## Guardrails

- Copy remediation snippets from the audit verbatim; do not invent new patches.
- Do not implement code changes here; this skill only produces the OpenSpec change.
- Never copy a secret value from the audit or the code into the proposal, design, or tasks.
- If the audit's verdict is `BLOCK`, Phase 1 is the minimum required to lift the block; say so.
- Keep tasks atomic: one logical change per task, even if that means more tasks.
- Respect the project's verification conventions (`CLAUDE.md` / `AGENTS.md` / CI) instead of assuming a language-specific command.
