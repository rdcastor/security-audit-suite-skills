# Security Audit Suite — Claude Code Skills

A set of agent skills that add a structured AppSec review layer to an AI-assisted development workflow. Works standalone on any codebase, and plugs into [OpenSpec](https://github.com/Fission-AI/OpenSpec) as a per-project gate that runs before a change is archived, using OpenSpec's own configuration rather than patched files.

**Install once, enable per project.** The skills can live in your user-level skills folder, but nothing audits anything until a project opts in.

---

## Skills

| Skill | Invocation | What it does |
|---|---|---|
| `security-audit` | "audit `src/auth.py`", "audit `main..HEAD`", or as the OpenSpec gate | AppSec review of a path, diff, ref range, or OpenSpec change. Structured report ending in a machine-readable `**VERDICT: ...**` line, plus a `security-audit.json` sidecar. |
| `enable-security-audit-gate` | "enable the security audit gate" | Opts one project in: writes the gate into `openspec/config.yaml` (`operations.apply.guidance` / `operations.archive.guidance`), optionally installs a hard verdict hook, migrates off the 1.x inline patch. `--remove` opts out. |
| `prepare-full-codebase-security-audit` | "prepare full codebase security audit" (manual only) | Enumerates every source file, partitions into risk-ordered chunks, generates an OpenSpec change whose tasks drive a full audit and merge the results. Plan only; expensive to run. |
| `remediate-security-findings` | "remediate security findings" | Reads an audit sidecar or a merged findings report and generates an OpenSpec change (proposal + design + tasks) that fixes the open findings. |
| `security-suite-overview` | reference only | How the pieces fit: the gate, the full-project workflow, concurrency, resumability. |

---

## Requirements

- An agent that loads skills from a skills folder (Claude Code; Codex and Gemini use the same `SKILL.md` layout).
- For the OpenSpec gate: OpenSpec **1.7 or newer** (`operations` guidance). Keep it current: `npm install -g @fission-ai/openspec@latest`.
- Python 3.9+ with PyYAML for `enable-security-audit-gate/scripts/gate_config.py`. `check_verdict.py` needs only the standard library.

---

## Installation

**Global (recommended):** copy or link the four skill folders into your user-level skills directory, for example `~/.claude/skills/`. Each folder is self-contained (`SKILL.md`, `scripts/`, `references/`).

```
~/.claude/skills/
├── security-audit/
├── enable-security-audit-gate/
├── prepare-full-codebase-security-audit/
└── remediate-security-findings/
```

**Project-local:** the same folders under `.claude/skills/` (Claude Code), `.codex/skills/`, or `.gemini/skills/`. Do not keep both a global and a project copy; they drift.

Installing does not turn anything on. `security-audit` runs when you ask for an audit by name, and as a gate only in projects that enabled it.

---

## Enabling the gate in a project

```
enable the security audit gate
```

The skill runs `scripts/gate_config.py`, which adds two entries to the project's `openspec/config.yaml`:

```yaml
operations:
  apply:
    guidance:
      - "security-audit gate (apply, policy=ask): when the last task is marked complete and before suggesting archive, run the security-audit skill ..."
  archive:
    guidance:
      - "security-audit gate (archive, policy=ask): before assessing delta specs or moving the change, run the security-audit skill ..."
```

Comments and ordering in the file are preserved; running it twice is a no-op; `--remove` takes the entries out. Two policies:

- `ask` (default): findings are surfaced; the user decides whether to fix, defer, or override.
- `autofix`: actionable findings are remediated inline with regression tests, the change is re-audited until SAFE, and only an explicit recorded override archives on a non-SAFE verdict.

Why this is the right place: `openspec instructions apply|archive --json` returns these entries as `operationGuidance`, and the generated `openspec-apply-change` / `openspec-archive-change` skills read and follow them. `openspec update` regenerates skill files but never touches `config.yaml`, so the gate survives updates. A project without the entries has no gate.

### Making it enforceable

OpenSpec guidance is advisory by design. `enable-security-audit-gate/scripts/check_verdict.py` reads the audit sidecar and exits non-zero unless the verdict is `SAFE_TO_PROCEED` (or `PROCEED_WITH_FIXES` with only Low/Info findings open, under `--allow-low`) and the audit is not stale. Wire it as:

- a **git pre-commit hook** (`--staged`): refuses to commit an archived change without a SAFE sidecar;
- a **Claude Code PreToolUse hook** (`--from-hook`): refuses `openspec archive <name>` (and the equivalent `mv`) with exit 2;
- OpenSpec's **`beforeArchive`** hook once lifecycle hooks exist ([Fission-AI/OpenSpec#1910](https://github.com/Fission-AI/OpenSpec/issues/1910) is the open request).

Snippets are in `enable-security-audit-gate/references/gate-guidance.md`. Copy the script into the project first so the hook path is repo-relative.

---

## Usage

### One-off audit (any project)

```
audit src/auth.py
audit main..HEAD
audit the last commit
```

The skill enumerates the scope (working tree included), greps for sinks first, reads the files in full, and emits a report whose last line is always:

```
**VERDICT: SAFE_TO_PROCEED | PROCEED_WITH_FIXES | BLOCK**
```

Long reports are written to `.security-audit/<timestamp>-<scope>.md` with a `.json` sidecar; add `.security-audit/` to `.gitignore`.

### Full-project audit

> **Token cost warning.** This reads every source file and calls `security-audit` once per chunk: on a 50 to 150 file codebase expect 15 to 30+ LLM calls. Use it for a one-time baseline or a periodic deep audit, never per PR or in CI.

```
prepare full codebase security audit
/opsx:apply full-codebase-security-audit
```

Each chunk task writes `findings/<timestamp>/chunk-NN.md` and `.json`; the final task merges them into `findings-report.md` and `findings-report.json` (IDs prefixed `C<NN>-`). See `security-suite-overview/README.md` for the workflow and resumability.

### Remediate findings

```
remediate security findings
```

Reads the sidecar (or the merged report), filters to open Critical/High/Medium findings, and generates an OpenSpec change with one task per fix, a regression test per finding, the project's own checks, and a closing re-audit that must come back SAFE.

---

## Project profile (optional)

A `.security-audit.yaml` at the repo root tunes the suite for one project: `exclude_paths`, `llm_sensitive_paths` (always read in full), `allowed_deps`, `owasp_year`, `gate_policy`, `report_dir`. Documented in `security-audit/references/project-profile.md`.

---

## Report format

```
# Security Review — <scope>

## 0. Coverage          ← what was audited, skipped, triaged; commit and tree state
## 0.5. Assumptions     ← explicit trust assumptions and context gaps
## 1. Executive Summary
## 2. Top Critical Risks
## 3. Detailed Findings
   ### F1 — <Title>
   - Severity / Confidence / OWASP / CWE
   - Affected file:line
   - Description, exploitation scenario, remediation snippet
## 4. Systemic Issues
## 5. Quick Wins
## 6. Longer-Term Improvements

**VERDICT: SAFE_TO_PROCEED | PROCEED_WITH_FIXES | BLOCK**
```

Sidecar `security-audit.json`:

```json
{
  "skill_version": "2.0",
  "verdict": "PROCEED_WITH_FIXES",
  "scope": "...",
  "commit": "9f3c...",
  "dirty": true,
  "generated_at": "2026-09-28T00:00:00Z",
  "findings": [
    { "id": "F1", "severity": "Medium", "confidence": "High", "cwe": "CWE-284", "owasp": "A01:2021",
      "file": "src/api.py", "line": 84, "title": "...", "status": "open" }
  ],
  "coverage": { "in_scope": 4, "read_full": 4, "spot_checked": 0, "skipped": 0 }
}
```

Secret values found in code are never copied into a report or sidecar.

---

## Verdict rules

| Condition | Verdict |
|---|---|
| Any Critical finding at Confidence Medium or High | `BLOCK` |
| Any High finding at Confidence High | `BLOCK` |
| High at Low confidence, or Medium/Low only | `PROCEED_WITH_FIXES` |
| Nothing actionable (Info only), full coverage | `SAFE_TO_PROCEED` |
| Tier-1 files skipped for context limits | `PROCEED_WITH_FIXES` at best; never `SAFE_TO_PROCEED` on incomplete coverage |

---

## Migrating from 1.x

1.x patched the gate directly into the generated `openspec-apply-change` / `openspec-archive-change` files and shipped `restore-openspec-audit-gate` to re-apply it after every `openspec update`. That skill is gone; the patch is not needed.

1. Install 2.0 (replace the four folders; delete `restore-openspec-audit-gate/` everywhere it was copied).
2. In each project that used the gate: run `enable-security-audit-gate`, then `openspec update` to regenerate the skill files cleanly. The gate now comes from `config.yaml`.
3. Remove any "run restore-openspec-audit-gate after openspec update" note from the project's rules file.

Reports and sidecars from 1.x are readable by 2.0; re-audits of them fall back to a full pass because they carry no commit.

---

## License

MIT
