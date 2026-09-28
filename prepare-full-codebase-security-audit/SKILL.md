---
name: prepare-full-codebase-security-audit
description: "Enumerate every auditable source file in the project, partition them into risk-ordered chunks, and produce a complete OpenSpec change (proposal, design, specs, tasks) whose tasks drive the security-audit skill over each chunk and merge the results into one findings report. Audit-only, no remediation. MUST be triggered manually and explicitly by the user by name ('prepare the full codebase security audit', '/prepare-full-codebase-security-audit'); never run it automatically, as a side effect of another workflow, or in a project that has not enabled the security-audit suite."
license: MIT
metadata:
  author: rdcastor
  version: "1.1"
---

> # TOKEN COST WARNING
>
> **This skill is expensive to run.** A full-codebase audit reads every source file in the project and calls the `security-audit` skill once per chunk. On a medium-sized codebase (50 to 150 files) expect **15 to 30+ LLM calls** and significant token usage across the full `/opsx:apply` run.
>
> **This is not part of a standard development workflow.** Use it for a one-time security baseline before a hardening sprint or major release, or a periodic deep audit (quarterly, say), never per change and never in CI. For per-change review the `security-audit` skill alone is the right tool: it is scoped, cheap, and runs as the OpenSpec gate in projects that enabled it.

---

Prepare the project for a full-codebase security audit by enumerating every source file, partitioning them into focused risk-ordered chunks, and generating an OpenSpec change whose tasks drive the `security-audit` skill over each chunk.

This skill produces a plan and deliverable structure only. It does **not** run the audit. When implementation starts (`/opsx:apply`), each task runs one audit pass and writes a findings file plus its JSON sidecar; a final merge task assembles `findings-report.md` and `findings-report.json`, which `remediate-security-findings` reads.

## Trigger requirement

Run only when the user explicitly invokes this skill by name. Do not invoke it automatically, as a sub-step of another skill, or because the conversation touches security topics. If it is at all unclear whether the user is asking for this skill, ask before proceeding. The suite is opt-in per project (see `security-audit/SKILL.md`); a manual request by name is that opt-in for this run.

## Concurrency model

Concurrent `security-audit` runs are the norm, not the exception: the skill gates OpenSpec changes in enabled projects while a full-project run is in flight. Every design decision here treats concurrency as the default case:
- Nothing is written to a shared file to track run state. The active run folder path lives in conversation context only.
- Each run gets its own timestamped output folder (`findings/<timestamp>/`), so runs never share, overwrite, or read each other's output.
- Resumability is derived from disk state: scan `findings/` for an incomplete run (chunk files present, no `findings-report.md`) rather than reading a shared pointer.
- Any future change to this skill or to `security-audit` that introduces shared mutable state on disk must be rejected unless it uses a per-run-scoped path.

## Steps

### 1. Derive the change name

Default: `full-codebase-security-audit`. If the user supplied a custom name or scope description, convert it to kebab-case and use that.

Confirm the project has an OpenSpec root first (`openspec list --json` returns a `root` object); if it does not, stop and say so rather than letting a command create `openspec/` as a side effect. Then check whether `openspec/changes/<name>/` already exists. If it does, ask the user whether to continue the existing change or start fresh (suffix `-v2`, incrementing).

### 2. Enumerate auditable files

Use git as the enumerator: it respects `.gitignore`, so virtual environments, build output, and data dumps drop out by construction.

```bash
{ git ls-files; git ls-files --others --exclude-standard; } \
  | grep -E '\.(py|sh|bat|ps1|html|js|ts|tsx|jsx|go|rs|java|rb|php|yaml|yml|toml|cfg|ini|ipynb|json|sql)$|(^|/)(Dockerfile|Makefile|docker-compose[^/]*)$' \
  | grep -v -E '(^|/)(openspec/changes|dist|build|target|\.next|vendor|third_party|node_modules)(/|$)' \
  | sort
```

Outside git, fall back to `find` with the same extensions, excluding `node_modules`, `.venv`, `venv`, `__pycache__`, `.git`, `dist`, `build`, `target`, `.next`, `vendor`.

Apply `exclude_paths` from `.security-audit.yaml` if the project has one, and drop anything that is clearly not auditable source for this project (vendored third-party code, generated files, raw data, model weights). Record the total file count (the "N files in scope" number in the proposal) and list every exclusion with its reason in the proposal's Non-Goals.

### 3. Classify files into surface-area chunks

Assign each file to exactly one chunk, using this table as a starting point and adapting it to the actual project: drop chunks that do not apply, promote a dedicated auth service to its own chunk, and put paths listed under `llm_sensitive_paths` in the project profile into a Critical-tier chunk of their own.

| Chunk | Surface area | Risk tier | Files to include |
|---|---|---|---|
| 01 | API layer and auth | Critical | Entry-point request handlers, auth middleware, session management, rate-limit config, startup checks |
| 02 | Business logic and data processing | Critical | Core application logic, data transformation pipelines, any LLM/AI prompt assembly and tool definitions |
| 03 | Database layer | High | Database clients, ORM/query-builder code, connection pool config, DB-backed logging sinks |
| 04 | Subprocess and IPC servers | High | Any module calling `subprocess`, `os.system`, `Popen`, `exec`; IPC servers (MCP, gRPC, workers) |
| 05 | External API integrations | High | Third-party API clients, HTTP client wrappers, outbound webhook handlers, OAuth flows |
| 06 | Data pipeline scripts | Medium | ETL/pipeline scripts that ingest, transform, or publish data |
| 07 | Shared utilities | Medium | Helpers used across the codebase (path resolution, serialisation, client wrappers) |
| 08 | Migration and admin scripts | Medium | One-shot or operator-run scripts (migrations, data rebuilds, index admin, seeds) |
| 09 | Shell and deployment scripts | Medium | `.bat`, `.sh`, `.ps1`, deploy/sync/CI scripts |
| 10 | Infrastructure config | Medium | Docker Compose, Dockerfiles, `.env.example`, CI YAML, Kubernetes manifests |
| 11 | Frontend | Medium | HTML/JS/TS/JSX/TSX UI code |
| 12 | ML / offline workloads | Low | Training, evaluation, vector indexing (if present) |
| 13 | Notebooks | Low | Jupyter notebooks (audit cell code as script) |
| 14 | Misc scripts | Low | Small standalone scripts that fit nowhere else |
| 15 | Test suites (optional) | Low | Unit/integration/E2E tests; hard-coded credentials and insecure fixtures |

Rules: no chunk over 15 files (split into 06a / 06b); no file in more than one chunk; a single file with more than ~500 lines of security-sensitive code is a solo chunk; every excluded file is listed with a reason.

### 4. Create the OpenSpec change

```bash
openspec new change "<name>"
openspec status --change "<name>" --json
```

### 5. Generate artifacts in dependency order

Track progress with a todo list, one item per artifact. Before writing each artifact, fetch its instructions so the project's own `rules` and `context` from `openspec/config.yaml` apply:

```bash
openspec instructions <artifact-id> --change "<name>" --json
```

#### 5a. `proposal.md`

```markdown
## Why

<1–2 sentences: the project has no documented security baseline; this change establishes one
before [hardening / release / feature work]. Audit-only: no code is modified.>

## What Changes

- Enumerate all <N> auditable source files across <surface list>
- Partition into <M> risk-ordered audit chunks (15 files or fewer each)
- Run the `security-audit` skill on each chunk; write `findings/<timestamp>/chunk-NN.md` (+ `.json`) per pass
- Merge all per-chunk results into `findings-report.md` and `findings-report.json` with a severity summary table
- No source file is modified; this change produces report artifacts only

## Capabilities

### New Capabilities

- `security-findings-report`: a consolidated findings document covering every audited file. Each finding
  records ID, severity, confidence, CWE, file/line, description, and exploitation note. It is the input
  spec for remediation changes (`remediate-security-findings`).

### Modified Capabilities

<!-- none -->

## Impact

- **Files read (not modified):** every file enumerated in step 2 (N files)
- **New artifacts:** `findings/<timestamp>/chunk-NN.md` + `.json` (one pair per chunk), `findings-report.md`, `findings-report.json`
- **No runtime behavior changes**
- **Dependency:** the `security-audit` skill, installed globally (`~/.claude/skills/security-audit/`) or in the project (`.claude/skills/security-audit/`)
```

#### 5b. `design.md`

```markdown
## Context

<How many files, how many chunks, why chunked by surface area rather than directory.>

## Goals / Non-Goals

**Goals:** 100% file coverage across all <M> chunks; one consolidated report with per-finding severity,
confidence, CWE, file/line; risk-ordered execution (highest-exposure code first).

**Non-Goals:** remediation (no code is modified); auditing vendored code, generated files, raw data, or
build artifacts; dynamic analysis / runtime testing.

## Decisions

### Chunk by surface area, not directory
Same directory often mixes risk levels. Surface-area grouping keeps the reviewer's mental model consistent per pass.

### Risk-ordered execution
Critical-path API and business logic are reviewed first so blockers surface before lower-value passes consume context.

### One findings file (and sidecar) per chunk, merged at the end
Passes can run independently and resume if interrupted. The merge is mechanical: no re-audit.

### Finding IDs
Within a chunk the skill numbers findings `F1`, `F2`, ...; the merge prefixes them with the chunk
(`C03-F2`) so IDs stay unique in the consolidated report and in `findings-report.json`.

## Chunk Manifest

<The full chunk table from step 3 with every file listed under its chunk.>

## Risks / Trade-offs

- Large single files are solo chunks
- Notebook findings use cell-index references, not line numbers
- Static analysis only
- `.env` (live secrets) is excluded; `.env.example` is audited for format hints; secret values are never copied into reports

## Open Questions

- Include test suites? (Chunk 15, optional)
- Exclude auto-generated / vendored directories? (Tentative: yes)
```

#### 5c. `specs/security-findings-report/spec.md`

Five requirements, each with at least one `#### Scenario:`:

1. **Audit chunk execution**: every chunk runs the skill; output written to `findings/<timestamp>/chunk-NN.md` and `chunk-NN.json`.
2. **Per-chunk findings file**: the skill's report format is used; "No findings" is written for a clean chunk, still with a sidecar.
3. **Consolidated findings report**: summary table plus severity-sorted findings in `findings-report.md`; merged findings array with `chunk` field in `findings-report.json`.
4. **Audit scope completeness**: every chunk has run before the merge; skips are documented.
5. **No code modification**: `git status` outside the change directory is unchanged after the full audit.

#### 5d. `tasks.md`

One task group per chunk plus Preparation and Consolidation. OpenSpec asks each task to say how its completion is verified; the "confirm the file exists" tasks are that.

```markdown
## 1. Preparation

- [ ] 1.1 Check `findings/` for a subfolder with chunk files but no `findings-report.md`. If found, ask the user whether to continue that run or start fresh. Otherwise generate a new timestamp (`YYYY-MM-DD-HHMMSS`), create `findings/<timestamp>/`, and carry the path in conversation context for all later tasks (never write it to a file)
- [ ] 1.2 Confirm the `security-audit` skill is reachable (`~/.claude/skills/security-audit/SKILL.md` or `.claude/skills/security-audit/SKILL.md`)

## 2. Chunk 01 — <Surface Area>

- [ ] 2.1 Run `security-audit` on: <file1>, <file2>, ...; output path `findings/<timestamp>/chunk-01.md` (path from context)
- [ ] 2.2 Verify `findings/<timestamp>/chunk-01.md` and `chunk-01.json` exist (write "No findings" if clean)

## 3. Chunk 02 — <Surface Area>

- [ ] 3.1 Run `security-audit` on: <file list>; output path `findings/<timestamp>/chunk-02.md`
- [ ] 3.2 Verify `findings/<timestamp>/chunk-02.md` and `chunk-02.json` exist

... (one group per chunk) ...

## N. Consolidation

- [ ] N.1 Verify every chunk file exists under `findings/<timestamp>/` (if context was lost, scan `findings/` for the run with chunks but no `findings-report.md`)
- [ ] N.2 Write `findings/<timestamp>/findings-report.md`: summary table (chunk, surface area, file count, Critical/High/Medium/Low/Info counts) followed by each chunk's section, findings sorted Critical → Info, IDs prefixed `C<NN>-`
- [ ] N.3 Write `findings/<timestamp>/findings-report.json`: `{"verdict": <worst chunk verdict>, "generated_at": ..., "commit": ..., "chunks": [...], "findings": [every chunk finding with "id": "C<NN>-F<k>" and "chunk": NN]}`
- [ ] N.4 Verify `git status --porcelain` shows no changes outside `openspec/changes/<name>/`
```

Chunk task group number = chunk index + 1 (group 1 is Preparation).

### 6. Verify all artifacts are done

```bash
openspec status --change "<name>"
```

All four artifacts (`proposal`, `design`, `specs`, `tasks`) must show `done`.

### 7. Report to the user

- Change location: `openspec/changes/<name>/`
- Files in scope: N; chunks: M (surface area and file count per chunk)
- Exclusions and why
- Estimated cost: roughly one LLM call per chunk plus the merge
- How to start: `/opsx:apply <name>`; how to use the result: `remediate-security-findings` reads `findings/<timestamp>/findings-report.json`

## Guardrails

- **Manual invocation only**: never automatic, proactive, or a sub-step of another skill.
- **Audit-only**: no source file outside `openspec/changes/<name>/` is modified, here or during apply.
- **No chunk over 15 files**; **every file in exactly one chunk or the exclusions list**.
- **Do not run `security-audit` during this skill**: this skill produces the plan; execution happens in `/opsx:apply`.
- **Adapt the chunk table to the project**: create, merge, or rename chunks to match real surface areas.
- If a prior `findings-report.json` exists from an earlier run, note it in the proposal and pass it to the chunk tasks so `security-audit` can run in re-audit mode against it.
