---
name: prepare-full-codebase-security-audit
description: Enumerate every auditable source file in the project, partition them into risk-ordered chunks, and produce a complete OpenSpec change (proposal, design, specs, tasks) that drives a full-codebase security audit using the security-audit skill. Audit-only — no remediation. MUST be triggered manually and explicitly by the user — never invoked automatically or as a side-effect of another workflow.
license: MIT
metadata:
  author: rdcastor
  version: "1.0"
---

> # ⚠️ TOKEN COST WARNING
>
> **This skill is expensive to run.** A full-codebase audit reads every source file in the project and calls the `security-audit` skill once per chunk. On a medium-sized codebase (50–150 files), expect **15–30+ LLM calls** and significant token usage across the full `/opsx:apply` run.
>
> **This is not part of a standard development workflow.** Use it for:
> - A one-time security baseline before a hardening sprint or major release
> - A periodic deep audit (e.g. quarterly), not per-change
>
> For per-change security review, use the `security-audit` skill directly. It is lightweight, scoped, and gates every OpenSpec archive automatically.
>
> **Do not run this on every PR or as part of CI.** You will burn through your token budget.

---

Prepare the project for a full-codebase security audit by enumerating every source file, partitioning them into focused risk-ordered chunks, and generating an OpenSpec change whose tasks drive the `security-audit` skill over each chunk.

This skill produces a plan and deliverable structure only — it does **not** run the audit itself. When implementation starts (`/opsx:apply`), each task runs one audit pass and writes a findings file; a final merge task assembles `findings-report.md`.

## Trigger requirement

**This skill MUST only run when the user explicitly invokes it by name** (e.g. `/prepare-full-codebase-security-audit`, "run the prepare-full-codebase-security-audit skill", "prepare the full codebase security audit"). Do **not** invoke this skill automatically, as a sub-step of another skill, or because the conversation touches security topics. If there is any ambiguity about whether the user is explicitly requesting this skill, ask before proceeding.

## Concurrency model

**Concurrent security-audit runs are the norm, not the outlier.** The `security-audit` skill gates every OpenSpec change, so multiple audit runs will routinely be in flight simultaneously across different threads and sessions. Every design decision in this skill and any skill it coordinates with **must treat concurrency as the default case**, not an edge case to handle gracefully after the fact.

Consequences:
- **Nothing is written to a shared file to track run state.** The active run folder path lives in conversation context only — it is thread-local by definition.
- **Each run gets its own timestamped output folder** (`findings/<timestamp>/`) so runs never share, overwrite, or read each other's output.
- **Resumability is derived from disk state, not a marker file** — scan `findings/` for an incomplete run (chunk files present, no `findings-report.md`) rather than reading a shared pointer.
- **Any future change to this skill or `security-audit` that introduces shared mutable state on disk must be rejected** unless it uses a per-run-scoped path (e.g. `findings/<timestamp>/...`).

## When to use

- User explicitly asks to prepare or plan a full-codebase security audit
- User wants every line of code reviewed before a major release or hardening sprint
- User wants a repeatable, resumable audit workflow rather than a one-shot pass

## Steps

### 1. Derive the change name

Default name: `full-codebase-security-audit`

If the user supplied a custom name or scope description, convert it to kebab-case and use that instead.

Check whether `openspec/changes/<name>/` already exists:

```bash
ls openspec/changes/<name>/ 2>/dev/null
```

If it exists, ask the user whether to continue the existing change or start fresh. If starting fresh, append a `-v2` suffix (or increment).

---

### 2. Enumerate auditable files

Run the following to collect all auditable source files. Print the full list so it can be referenced in later steps.

```bash
find . -type f \( \
  -name "*.py" -o \
  -name "*.sh"  -o \
  -name "*.bat" -o \
  -name "*.html" -o \
  -name "*.js"  -o \
  -name "*.ts"  -o \
  -name "*.tsx" -o \
  -name "*.jsx" -o \
  -name "*.go"  -o \
  -name "*.rs"  -o \
  -name "*.java" -o \
  -name "*.rb"  -o \
  -name "*.yaml" -o \
  -name "*.yml" -o \
  -name "*.toml" -o \
  -name "*.cfg"  -o \
  -name "*.ini"  -o \
  -name "*.ipynb" \
\) | grep -v -E \
  "(node_modules|venv|__pycache__|\.git|\.openspec|openspec/changes|dist/|build/|target/|\.next/)" \
| sort
```

Also collect config JSON that is not raw data:

```bash
find . -name "*.json" \
  -not -path "*/venv/*" \
  -not -path "*/__pycache__/*" \
  -not -path "*/.git/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/dist/*" \
  -not -path "*/build/*" \
  | sort
```

Record the total file count. This becomes the "N files in scope" number in the proposal.

**Exclude and document** any directories that are clearly not auditable source code for this project (e.g. vendored third-party code, auto-generated files, raw data dumps, model weight directories). List every exclusion and its reason in the proposal's Non-Goals section.

---

### 3. Classify files into surface-area chunks

Assign each enumerated file to exactly one chunk using the table below as a starting point. **Adapt the chunk definitions to fit the actual project structure** — if the project has no ML training code, skip chunk 12; if it has a dedicated auth service, promote it to its own chunk. The goal is coherent surface areas, not rigid adherence to this template.

| Chunk | Surface Area | Risk Tier | Files to include |
|-------|-------------|-----------|-----------------|
| 01 | API layer & auth | Critical | Entry-point request handlers, auth middleware, session management, rate-limit config, startup checks |
| 02 | Business logic & data processing | Critical | Core application logic, data transformation pipelines, any LLM/AI prompt assembly |
| 03 | Database layer | High | Database clients, ORM/query-builder code, connection pool config, DB-backed logging sinks |
| 04 | Subprocess & IPC servers | High | Any module calling `subprocess`, `os.system`, `Popen`, `exec`; IPC servers (e.g. MCP, gRPC, workers) |
| 05 | External API integrations | High | Third-party API clients, HTTP client wrappers, outbound webhook handlers, OAuth flows |
| 06 | Data pipeline scripts | Medium | ETL/pipeline scripts that ingest, transform, or publish data |
| 07 | Shared utilities | Medium | Shared helpers used across the codebase (path resolution, serialisation, client wrappers) |
| 08 | Migration & admin scripts | Medium | One-shot or operator-run scripts (migrations, data rebuilds, index admin, seed scripts) |
| 09 | Shell & deployment scripts | Medium | `.bat`, `.sh`, deploy/sync/CI scripts |
| 10 | Infrastructure config | Medium | Docker Compose, Dockerfiles, `.env.example`, CI YAML, Kubernetes manifests |
| 11 | Frontend | Medium | HTML/JS/TS/JSX/TSX UI code |
| 12 | ML / offline workloads | Low | ML training, model evaluation, vector indexing (if present) |
| 13 | Notebooks | Low | Jupyter notebooks (audit cell code as script) |
| 14 | Misc scripts | Low | Small standalone scripts that don't fit other categories |
| 15 | Test suites (optional) | Low | Unit/integration/E2E tests; check for hardcoded creds and insecure fixtures |

Rules:
- **No chunk should exceed 15 files.** If a chunk is larger, split it (e.g. Chunk 06a / 06b).
- **No file appears in more than one chunk.**
- If a file is very large on its own (>500 lines of security-sensitive code), treat it as a solo chunk.
- Record any file you decide to **exclude** and document why.

---

### 4. Create the OpenSpec change

```bash
openspec new change "<name>"
```

Then check status:

```bash
openspec status --change "<name>" --json
```

---

### 5. Generate artifacts in dependency order

Use **TodoWrite** to track progress through each artifact. Get instructions for each artifact before writing it:

```bash
openspec instructions <artifact-id> --change "<name>" --json
```

#### 5a. `proposal.md`

Write using this structure:

```markdown
## Why

<1–2 sentences: the project has no documented security baseline; this change
establishes one before [hardening / release / feature work]. Audit-only — no
code is modified.>

## What Changes

- Enumerate all <N> auditable source files across <surface list>
- Partition into <M> risk-ordered audit chunks (≤15 files each)
- Execute the `security-audit` skill on each chunk; write `findings/chunk-NN.md` per pass
- Assemble all per-chunk results into `findings-report.md` with a severity summary table
- No source file is modified — this change produces report artifacts only

## Capabilities

### New Capabilities

- `security-findings-report`: A consolidated findings document covering every
  audited file. Each finding records severity, CWE, file/line, description, and
  reproduction note. Serves as the input spec for all future remediation changes.

### Modified Capabilities

<!-- none -->

## Impact

- **Files read (not modified):** every file enumerated in step 2 (N files)
- **New artifacts produced:** `findings/chunk-NN.md` (one per chunk) + `findings-report.md`
- **No runtime behavior changes**
- **Dependency:** `security-audit` skill at `.claude/skills/security-audit/`
```

#### 5b. `design.md`

Write using this structure:

```markdown
## Context

<Brief: how many files, how many chunks, why chunked by surface area rather
than directory.>

## Goals / Non-Goals

**Goals:**
- 100% file coverage across all <M> chunks
- Single consolidated findings report with per-finding severity, CWE, file/line
- Risk-ordered execution (highest-exposure code first)

**Non-Goals:**
- Remediation — no code is modified
- Auditing vendored code, auto-generated files, raw data, or build artifacts
- Dynamic analysis / runtime testing

## Decisions

### Chunk-by-surface-area, not directory

**Why:** Same directory often mixes risk levels. Surface-area grouping keeps
the reviewer's mental model consistent per pass.

### Risk-ordered execution

**Why:** Critical-path API and business logic code is reviewed first so blockers
surface before lower-value passes consume context.

### One findings file per chunk, merged at the end

**Why:** Allows passes to be done independently and resumed if interrupted.
Merge is mechanical — no re-audit required.

### Findings schema (per entry)

```
### [SEVERITY] <Title> — <file>:<line>
**CWE**: CWE-XXX
**Severity**: Critical | High | Medium | Low | Info
**File**: `path/to/file.py` line N
**Description**: ...
**Reproduction**: ...
**Chunk**: N
```

## Chunk Manifest

<Insert the full chunk table from step 3 here, with every file listed under
its chunk.>

## Risks / Trade-offs

- Large single files → treated as solo chunks
- Notebook findings use cell-index references, not line numbers
- Static analysis only — no dynamic coverage
- `.env` (live secrets) excluded; `.env.example` audited for format hints

## Open Questions

- Include test suites? (Chunk 15, optional — may contain hardcoded fixtures)
- Exclude auto-generated / vendored directories? (Tentative: yes)
```

#### 5c. `specs/security-findings-report/spec.md`

Write five requirements (each with ≥1 scenario using `####` headers):

1. **Audit chunk execution** — every chunk runs the skill; output written to `findings/chunk-NN.md`
2. **Per-chunk findings file** — schema enforced; "No findings" written for clean chunks
3. **Consolidated findings report** — summary table + severity-sorted findings
4. **Audit scope completeness** — all chunks run before merge; skips documented
5. **No code modification** — `git diff` outside the change dir is clean after the full audit

#### 5d. `tasks.md`

Generate one task group per chunk plus a Preparation group and a Consolidation group:

```markdown
## 1. Preparation

- [ ] 1.1 Check `findings/` for any subfolder with chunk files but no `findings-report.md` — if found, ask user whether to continue that run or start fresh. Otherwise generate a new timestamp (`YYYY-MM-DD-HHMMSS`), create `findings/<timestamp>/`, and carry the path in context for all subsequent tasks (do not write it to any file on disk)
- [ ] 1.2 Confirm `security-audit` skill is present at `.claude/skills/security-audit/SKILL.md`

## 2. Chunk 01 — <Surface Area>

- [ ] 2.1 Run `security-audit` on: <file1>, <file2>, ...; write output to `findings/<timestamp>/chunk-01.md` (path from context)
- [ ] 2.2 Confirm `findings/<timestamp>/chunk-01.md` was written (write "No findings" if clean)

## 3. Chunk 02 — <Surface Area>

- [ ] 3.1 Run `security-audit` on: <file list>; write output to `findings/<timestamp>/chunk-02.md` (path from context)
- [ ] 3.2 Confirm `findings/<timestamp>/chunk-02.md` was written

... (one group per chunk) ...

## N. Consolidation

- [ ] N.1 Verify all chunk files exist under `findings/<timestamp>/` (path from context; if context was lost, scan `findings/` for the incomplete run folder — the one with chunks but no `findings-report.md`)
- [ ] N.2 Write `findings/<timestamp>/findings-report.md` — top-level summary table (chunk, surface, file count, Critical/High/Medium/Low/Info counts)
- [ ] N.3 Append per-chunk sections sorted Critical → Info within each section
- [ ] N.4 Verify `git diff` shows zero changes outside `openspec/changes/<name>/`
```

Each chunk task group number = chunk index + 1 (to leave group 1 for Preparation).

---

### 6. Verify all artifacts are done

```bash
openspec status --change "<name>"
```

All four artifacts (`proposal`, `design`, `specs`, `tasks`) must show `done`.

---

### 7. Report to the user

Summarize:

- Change location: `openspec/changes/<name>/`
- Total files in scope: N
- Chunks: M (list surface area + file count per chunk)
- Excluded: list any files excluded and why
- Estimated token cost: rough estimate based on chunk count ("~20 LLM calls for M chunks")
- How to start: "Run `/opsx:apply` to begin working through the audit tasks."

---

## Guardrails

- **Manual invocation only**: this skill MUST NOT be invoked automatically, proactively, or as a sub-step of another skill. Only proceed when the user has explicitly and unambiguously requested it by name.
- **Audit-only**: at no point should a source file outside `openspec/changes/<name>/` be modified.
- **No chunk over 15 files**: split if needed rather than producing an oversized single pass.
- **Every file accounted for**: each enumerated file must appear in exactly one chunk or the exclusions list.
- **Do not run the security-audit skill during this skill** — this skill only produces the plan; execution happens via `/opsx:apply`.
- **Adapt the chunk table to the project**: do not rigidly apply the default chunk definitions if the project structure doesn't match. Create, merge, or rename chunks to reflect actual surface areas.
- If the project already has a prior `findings-report.md` from an earlier audit pass, note it in the proposal and consider whether re-audit mode in the `security-audit` skill applies (pass the prior report path).
