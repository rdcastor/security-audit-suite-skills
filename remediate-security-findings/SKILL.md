---
name: remediate-security-findings
description: Generate an OpenSpec proposal for remediating security audit findings. Triggered by "remediate security findings". Reads a security-audit.md report (or security-audit.json), maps each finding to concrete tasks, and produces a full change with proposal, design, and tasks ready for /opsx:apply.
license: MIT
metadata:
  author: rdcastor
  version: "1.0"
---

Generate an OpenSpec change proposal for remediating security audit findings.

## Input

Optionally specify:
- A path to a `security-audit.md` or `security-audit.json` report.
- An OpenSpec change name whose audit report to read (looks for `openspec/changes/<name>/security-audit.md`).
- Nothing — infer the report from conversation context or ask.

## Steps

1. **Locate the audit report**

   Check in order:
   - Argument passed to the skill (file path or change name).
   - Conversation context — was a security audit just run? Use that report.
   - `openspec/changes/*/security-audit.json` — if exactly one exists, use it.
   - If ambiguous, use the **AskUserQuestion** tool:
     > "Which security audit report should I remediate? Provide a path or change name."

   Read both `security-audit.md` (full narrative) and `security-audit.json` (structured findings) when both exist. The JSON `findings` array is the authoritative list; the markdown provides remediation detail.

2. **Determine the change name**

   Derive a kebab-case change name from the source:
   - Source change was `foo-bar` → propose `remediate-foo-bar`.
   - Generic audit (no source change) → propose `security-remediation`.
   - If the name already exists as a change directory, append `-v2`, `-v3`, etc.

   Announce: "Creating change: `<name>`"

3. **Filter findings by severity**

   Split findings into two buckets:
   - **In-scope** (default): Critical, High, Medium — these go into the proposal and tasks.
   - **Noted but deferred**: Low / Info — list them in the proposal's Non-Goals section; do not generate tasks for them unless the caller explicitly asks.

   If the report verdict is `SAFE_TO_PROCEED` (no actionable findings), tell the user and exit — no proposal needed.

4. **Create the change**

   ```bash
   openspec new change "<name>"
   ```

5. **Write `proposal.md`**

   Structure:
   ```
   ## Problem
   <1–2 sentences: what vulnerability class / attack surface is exposed>

   ## Findings Being Addressed
   | ID | Severity | Title | OWASP / CWE |
   |----|----------|-------|-------------|
   | A  | Medium   | ...   | A01:2021 / CWE-284 |
   ...

   ## Proposed Solution
   <For each finding: one paragraph describing the fix strategy.
    Reference the remediation snippet from the audit report if present.>

   ## Non-Goals
   - Low/Info findings deferred: <list>
   - <anything explicitly out of scope>

   ## Phases
   Phase 1 — Critical/High fixes (if any)
   Phase 2 — Medium fixes
   Phase 3 — Tests & verification
   ```

6. **Write `design.md`**

   One "Decision" section per finding with:
   - The vulnerable pattern (before)
   - The fixed pattern (after) — copy the remediation snippet from the audit report verbatim
   - Any trade-offs or caveats

   Keep it concrete: show the actual code change, not a description of it.

7. **Write `tasks.md`**

   One task per distinct code change required. Group by phase. Each task must be independently completable. Format:

   ```markdown
   ## Phase 1 — Critical / High

   - [ ] 1.1 <file>:<function> — <what to change> [Finding <ID>]
   - [ ] 1.2 ...

   ## Phase 2 — Medium

   - [ ] 2.1 ...

   ## Phase 3 — Tests & Verification

   - [ ] 3.1 Add test: <test name> — verifies finding <ID> is closed
   - [ ] 3.2 Run `py_compile` on all modified files; full test suite must pass
   - [ ] 3.3 Commit as `security: remediate <finding IDs>`
   ```

   Include a final task: re-run `security-audit` scoped to this change and confirm the original findings are resolved.

8. **Summarise**

   Print:
   ```
   ## Remediation Change Created: <name>

   **Findings addressed:** <N> (Critical: X, High: Y, Medium: Z)
   **Deferred (Low/Info):** <M>

   ### Findings → Tasks
   - Finding A (Medium) → tasks 2.1, 3.1
   - ...

   Ready to implement: /opsx:apply <name>
   ```

## Guardrails

- Copy remediation snippets from the audit report verbatim — do not invent new patches.
- If the audit report has no remediation snippet for a finding, write the task description in terms of what to achieve, not how, and note that the implementer should derive the patch.
- Do not implement any code changes — this skill only produces the OpenSpec proposal.
- If the audit report's verdict is `BLOCK`, prioritise Critical/High findings in Phase 1 and make that phase's tasks the minimum required to unblock archival.
- Keep tasks atomic: one logical change per task, even if that means more tasks.
