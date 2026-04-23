# Security Audit Skills

Two skills form the full-project security audit workflow: `prepare-full-codebase-security-audit` and `security-audit`. This document covers how they fit together, the concurrency model, and how resumability works.

---

## Skills in this suite

### `security-audit`
A standalone AppSec review skill. Accepts a file path, directory, git ref range, or explicit file list. Emits a structured report ending in `**VERDICT: SAFE_TO_PROCEED | PROCEED_WITH_FIXES | BLOCK**`. Used directly for per-change gates (every OpenSpec archive triggers it) and as the per-chunk engine inside a full-project audit.

### `prepare-full-codebase-security-audit`
**Manual invocation only** — never triggered automatically. Enumerates every auditable source file in the project, partitions them into risk-ordered chunks (≤15 files each), and generates a complete OpenSpec change (`proposal.md`, `design.md`, `specs/`, `tasks.md`) whose tasks drive `security-audit` over each chunk. Produces a plan; does not run the audit itself.

---

## Workflow

```
/prepare-full-codebase-security-audit
        │
        ▼
openspec/changes/full-codebase-security-audit/
├── proposal.md
├── design.md
├── specs/security-findings-report/spec.md
└── tasks.md  ← 15 chunk tasks + consolidation
        │
        ▼
/opsx:apply
        │
        ├── Task 1.1: create findings/<timestamp>/
        ├── Task 2.x: security-audit → findings/<timestamp>/chunk-01.md
        ├── Task 3.x: security-audit → findings/<timestamp>/chunk-02.md
        ├── ...
        └── Task 17.x: merge → findings/<timestamp>/findings-report.md
```

The prepare skill produces the scaffold. `/opsx:apply` works through the tasks, calling `security-audit` once per chunk and writing each result to the timestamped run folder. The final consolidation task merges all chunk files into a single `findings-report.md`.

---

## Concurrency

**Concurrent `security-audit` invocations are the norm, not the outlier.** The skill gates every OpenSpec change archive, so multiple instances will be running simultaneously across threads at any given time.

The design accounts for this at every layer:

| Concern | How it's handled |
|---------|-----------------|
| Shared output files | Never written. Each run gets its own `findings/<timestamp>/` folder. |
| Run state tracking | Lives in conversation context only — thread-local by definition. No marker file on disk. |
| Default fallback paths | `.security-audit.md` and `openspec/changes/<name>/security-audit.md` are only used for standalone, non-chunked invocations with no explicit output path. |
| Output path priority | Caller-specified path always wins over defaults. Chunked audit tasks always supply an explicit path. |

**Rule for future changes:** any modification to these skills that introduces shared mutable state on disk must be rejected unless it uses a per-run-scoped path (e.g. `findings/<timestamp>/...`).

---

## Timestamped run folders

Each full-project audit run writes to its own folder:

```
openspec/changes/full-codebase-security-audit/findings/
├── YYYY-MM-DD-HHMMSS/
│   ├── chunk-01.md      ← API layer & auth
│   ├── chunk-02.md      ← Business logic & data processing
│   ├── ...
│   ├── chunk-15.md      ← test suites (optional)
│   └── findings-report.md   ← merged, severity-sorted
└── YYYY-MM-DD-HHMMSS/
    ├── chunk-01.md
    └── ...              ← second run, pre-remediation re-audit
```

The timestamp is generated once in task 1.1 and carried forward in conversation context for the duration of the run. It is never written to a shared file.

Remediation changes reference a specific report by its full path:
```
openspec/changes/full-codebase-security-audit/findings/YYYY-MM-DD-HHMMSS/findings-report.md
```

---

## Resumability

If a session is interrupted mid-audit:

1. Resume `/opsx:apply` in a new session.
2. Task 1.1 scans `findings/` for a subfolder that contains chunk files but **no** `findings-report.md`. That is the incomplete run.
3. If exactly one incomplete run exists, it continues automatically.
4. If multiple incomplete runs exist, it asks which to continue before proceeding.

Already-completed chunk tasks (marked `[x]` in `tasks.md`) are skipped. The resumed session picks up from the first unchecked chunk task.

---

## Chunk ordering (risk-based)

Chunks are audited highest-risk first so blockers surface before lower-value passes consume context:

| Chunks | Surface area | Risk |
|--------|-------------|------|
| 01–02 | API layer, LLM & retrieval pipeline | Critical |
| 03–04 | Database layer, subprocess/IPC servers | High |
| 05 | External API integrations | High |
| 06–09 | Data pipelines, utilities, migrations, shell scripts | Medium |
| 10–11 | Infrastructure config, frontend | Medium |
| 12–14 | Training, notebooks, misc | Low |
| 15 | Test suites | Low (optional) |

---

## Output format

Each `chunk-NN.md` uses the `security-audit` skill's standard report format (Coverage → Executive Summary → Findings → Verdict). The final `findings-report.md` prepends a summary table:

| Chunk | Surface Area | Files | Critical | High | Medium | Low | Info |
|-------|-------------|-------|----------|------|--------|-----|------|
| 01 | API layer & auth | 4 | 1 | 2 | 0 | 1 | 0 |
| ... | | | | | | | |

Findings within each chunk section are sorted Critical → High → Medium → Low → Info.

---

## Using findings for remediation

After a full audit completes, the `findings-report.md` is the input spec for all remediation work. The typical flow:

1. Review `findings/<timestamp>/findings-report.md`
2. Run `/opsx:propose` describing the remediation scope (e.g. "fix all Critical and High findings from the 2026-04-23 audit")
3. The resulting OpenSpec change's proposal references the findings report by path
4. Implement via `/opsx:apply` — the `security-audit` gate will run again before archival, scoped to the changed files

Each remediation change should fix a coherent set of findings (e.g. by severity tier or surface area) rather than all findings at once, so the audit gate on archival remains focused.
