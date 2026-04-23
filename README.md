# Security Audit Suite — Claude Code Skills

A set of Claude Code skills that add a structured AppSec review layer to your development workflow. Works standalone or deeply integrated with [OpenSpec](https://github.com/Fission-AI/OpenSpec), a capability-oriented spec and change-management CLI for AI-assisted development.

---

## Skills

| Skill | Invocation | What it does |
|-------|-----------|-------------|
| `security-audit` | "audit `src/auth.py`" | AppSec review of a path, diff, or git ref range. Emits a structured report with a machine-readable `VERDICT` line. |
| `prepare-full-codebase-security-audit` | "prepare full project security audit" | Enumerates every source file, partitions into risk-ordered chunks, and generates an OpenSpec change whose tasks drive a full audit. Produces a plan only — does not run the audit itself. |
| `remediate-security-findings` | "remediate security findings" | Reads an audit report, maps each finding to a concrete fix, and generates an OpenSpec change (proposal + design + tasks) ready to implement. |
| `restore-openspec-audit-gate` | "restore openspec audit gate" | Re-applies the security gate to the OpenSpec-generated skills after `openspec update` overwrites them (see warning below). |
| `security-suite-overview` | — | Reference document only (no `SKILL.md`). Covers the full-project audit workflow, concurrency model, and resumability in detail. |

---

## Installation

Copy the skill folders into your agent's skills directory:

**Claude Code:**
```
.claude/skills/
├── security-audit/
├── prepare-full-codebase-security-audit/
├── remediate-security-findings/
├── restore-openspec-audit-gate/
└── security-suite-overview/
```

**Gemini / Codex:** same structure under `.gemini/skills/` and `.codex/skills/`.

Once in place, Claude Code picks up the skills automatically — no registration step required.

---

## Usage

### One-off audit (any project)

```
audit src/auth.py
audit main..HEAD
audit the last commit
```

The skill reads the relevant files, applies a threat-model lens, and emits a report. The final line is always:

```
**VERDICT: SAFE_TO_PROCEED | PROCEED_WITH_FIXES | BLOCK**
```

This line is machine-readable — other skills grep for it to gate workflows programmatically.

### Full-project audit

> ⚠️ **Token cost warning** — This workflow reads every source file in your project and calls `security-audit` once per chunk. On a medium-sized codebase (50–150 files) expect **15–30+ LLM calls** and significant token usage. Use it for a one-time security baseline or a periodic deep audit — **not** as part of your standard CI or PR workflow.

```
prepare full codebase security audit
```

This enumerates every auditable file, partitions them into risk-ordered chunks (highest-risk surface area first), and generates an OpenSpec change with one task per chunk. Then:

```
/opsx:apply full-codebase-security-audit
```

Works through each chunk, calling `security-audit` once per chunk and writing results to a timestamped run folder. A final merge task assembles everything into `findings-report.md`. See `security-suite-overview/README.md` for the full workflow diagram and resumability details.

### Remediate findings

After any audit that surfaces findings:

```
remediate security findings
```

Reads the audit report, filters to Critical/High/Medium findings, and generates an OpenSpec change with one task per distinct code fix — ready to implement immediately with `/opsx:apply`.

---

## OpenSpec integration

These skills are designed to work with [OpenSpec](https://github.com/Fission-AI/OpenSpec), a CLI for managing capability specs and change artifacts in AI-assisted development projects. OpenSpec structures work as *changes* — each with a proposal, design, tasks, and specs — that agents implement and archive.

### How the audit gate works

`security-audit` acts as a gate on every OpenSpec change archive. When you run `/opsx:archive` on a completed change, the skill automatically audits the files touched by that change before allowing archival:

- **BLOCK** (Critical/High findings at High confidence) → archival is blocked; findings surface for remediation.
- **PROCEED_WITH_FIXES** (Medium/Low findings) → findings are surfaced; user confirms before archival proceeds.
- **SAFE_TO_PROCEED** → archival continues; "✓ Security audit passed" is recorded in the archive summary.

Audit reports are written to `openspec/changes/<change-name>/security-audit.md` alongside the change's other artifacts (proposal, design, tasks), with a sidecar `security-audit.json` for programmatic consumption.

### Getting started with OpenSpec

```bash
npm install -g openspec
openspec init
```

`openspec init` scaffolds the `openspec/` directory in your project and generates the agent skill files (`.claude/skills/openspec-*.md`, etc.) that drive the change workflow. Once initialised, the typical flow is:

```
/opsx:propose add-user-authentication   # generates proposal + design + tasks
/opsx:apply add-user-authentication     # implements the tasks (with audit gate)
/opsx:archive add-user-authentication   # archives on SAFE_TO_PROCEED verdict
```

See the [OpenSpec documentation](https://github.com/Fission-AI/OpenSpec) for the full CLI reference.

---

## ⚠️ `openspec update` wipes the audit gate

**This is the most important operational note in this README.**

When you run `openspec update` to pull the latest OpenSpec CLI changes, it regenerates the agent skill files in your project — including `openspec-apply-change` and `openspec-archive-change`. This **overwrites the security audit gate** that was patched into those skills, silently removing the step that blocks archival on Critical/High findings.

After every `openspec update`, run:

```
restore openspec audit gate
```

This re-applies the audit gate patches to the freshly regenerated skill files. Until you do, the gate is not active and changes can be archived without an audit.

**How to make this stick permanently:** add a note to your `CLAUDE.md` (or equivalent project rules file):

```markdown
## After `openspec update`
Always run the `restore-openspec-audit-gate` skill immediately after running
`openspec update`. The update regenerates skill files and wipes the security
audit gate — the restore skill re-applies it.
```

The `restore-openspec-audit-gate` skill reads the current generated files and patches in the audit step non-destructively, so it is safe to run multiple times.

---

## Report format

Every `security-audit` run produces a markdown report with this structure:

```
# Security Review — <scope>

## 0. Coverage          ← what was audited, what was skipped
## 0.5. Assumptions     ← explicit trust assumptions
## 1. Executive Summary ← 3–6 sentences, leadership-readable
## 2. Top Critical Risks
## 3. Detailed Findings
   ### <Title>
   - Severity / Confidence / OWASP / CWE
   - Affected file:line
   - Description + exploitation scenario
   - Remediation snippet
## 4. Systemic Issues
## 5. Quick Wins
## 6. Longer-Term Improvements

**VERDICT: SAFE_TO_PROCEED | PROCEED_WITH_FIXES | BLOCK**
```

And a sidecar `security-audit.json`:

```json
{
  "verdict": "PROCEED_WITH_FIXES",
  "scope": "...",
  "generated_at": "2026-04-23T00:00:00Z",
  "findings": [
    { "id": "A", "severity": "Medium", "confidence": "High",
      "cwe": "CWE-284", "owasp": "A01:2021",
      "file": "src/api.py", "line": 84, "title": "..." }
  ],
  "coverage": { "in_scope": 4, "read_full": 4, "spot_checked": 0, "skipped": 0 }
}
```

---

## Verdict rules

| Condition | Verdict |
|-----------|---------|
| Any Critical finding at Confidence ≥ Medium | `BLOCK` |
| Any High finding at Confidence High | `BLOCK` |
| High at Low confidence, or Medium/Low only | `PROCEED_WITH_FIXES` |
| Nothing actionable, full coverage | `SAFE_TO_PROCEED` |
| Tier-1 files skipped due to context limits | `PROCEED_WITH_FIXES` at best — never `SAFE_TO_PROCEED` on incomplete coverage |

---

## License

MIT
