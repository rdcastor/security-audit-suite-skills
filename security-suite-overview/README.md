# Security Audit Suite: how the pieces fit

Four skills. `security-audit` is the engine; the other three set it up, scale it up, and act on its output. This document covers the gate mechanism, the full-project workflow, the concurrency model, resumability, and remediation. It is reference material, not a skill (no `SKILL.md`).

## Skills

| Skill | Role |
|---|---|
| `security-audit` | Standalone AppSec review of a path, diff, ref range, or OpenSpec change. Emits a report ending in `**VERDICT: <TOKEN>**` and a `security-audit.json` sidecar (finding IDs, severity, confidence, commit). Per-change gate engine and per-chunk engine for full-project runs. |
| `enable-security-audit-gate` | Per-project opt-in. Writes the gate into `openspec/config.yaml` as `operations.apply.guidance` / `operations.archive.guidance`; optionally wires `check_verdict.py` as a git or Claude Code hook; migrates projects off the 1.x inline patch. |
| `prepare-full-codebase-security-audit` | Manual only. Enumerates every source file, partitions into risk-ordered chunks (15 files or fewer), generates an OpenSpec change whose tasks run `security-audit` per chunk and merge the results. Plan only; the audit runs in `/opsx:apply`. |
| `remediate-security-findings` | Reads a `security-audit.json` or a merged `findings-report.json`, maps open Critical/High/Medium findings to tasks, and generates an OpenSpec change ready for `/opsx:apply`. |

## The gate

```
openspec/config.yaml                     openspec instructions apply|archive --json
  operations:                    ──►        operationGuidance: [ "security-audit gate (apply, ...)", ... ]
    apply.guidance:   [gate]                        │
    archive.guidance: [gate]                        ▼
                                         openspec-apply-change / openspec-archive-change (generated skills)
                                           "read and consider every entry, follow the applicable ones"
                                                    │
                                                    ▼
                                         Skill(security-audit, args=<change>)  ──►  <changeRoot>/security-audit.md + .json
                                                    │                                          │
                                                    ▼                                          ▼
                                         BLOCK / PROCEED_WITH_FIXES / SAFE        check_verdict.py (optional hard hook)
```

- The entries are project configuration, so `openspec update` never removes them and a project without them has no gate.
- Guidance is advisory by OpenSpec's design. `check_verdict.py` makes it enforceable where the project wants that: a git pre-commit hook (`--staged`), a Claude Code PreToolUse hook on `openspec archive` (`--from-hook`, exit 2 blocks), and OpenSpec's own `beforeArchive` once lifecycle hooks exist (Fission-AI/OpenSpec#1910 is open at the time of writing).
- Two policies: `ask` (default; findings are surfaced, the user decides) and `autofix` (remediate inline, re-audit until SAFE, only an explicit override archives on a non-SAFE verdict).
- OpenSpec's `openspec-verify-change` is spec conformance, not security review; the two are complementary.

## Full-project workflow

```
/prepare-full-codebase-security-audit
        │
        ▼
openspec/changes/full-codebase-security-audit/
├── proposal.md · design.md · specs/security-findings-report/spec.md
└── tasks.md   ← one group per chunk + consolidation
        │
        ▼
/opsx:apply
        ├── 1.1  create findings/<timestamp>/  (path lives in context only)
        ├── 2.x  security-audit → findings/<timestamp>/chunk-01.md + chunk-01.json
        ├── 3.x  security-audit → findings/<timestamp>/chunk-02.md + chunk-02.json
        ├── ...
        └── N.x  merge → findings/<timestamp>/findings-report.md + findings-report.json
                         (IDs prefixed C<NN>-, e.g. C03-F2)
```

## Concurrency

Concurrent `security-audit` invocations are the norm: the gate runs per change while a full-project run may be in flight.

| Concern | How it is handled |
|---|---|
| Shared output files | Never written. Each run gets its own `findings/<timestamp>/`; each change gets `<changeRoot>/security-audit.*`; ad-hoc reports get `.security-audit/<timestamp>-<slug>.*`. |
| Run state | Conversation context only; no marker file on disk. |
| Output path priority | Caller-specified path always wins. Chunk tasks always pass one. |

Rule for future changes: anything that introduces shared mutable state on disk is rejected unless it uses a per-run-scoped path.

## Resumability

1. Resume `/opsx:apply` in a new session.
2. Task 1.1 scans `findings/` for a subfolder with chunk files but no `findings-report.md`: that is the incomplete run. One match continues automatically; several match, the user picks.
3. Chunk tasks already marked `[x]` are skipped; the run resumes at the first unchecked chunk.

## Re-audits

`security-audit.json` records the commit the audit ran at. A re-audit diffs from that commit, carries unchanged findings forward (`status: carried`), marks fixed ones `resolved`, and continues the ID sequence. That is what keeps repeated gates cheap, and what `check_verdict.py` uses to call an audit stale when HEAD moved past it with code changes.

## Remediation

After any audit with open findings:

1. `remediate-security-findings` (reads the sidecar or the merged report).
2. `/opsx:apply <remediation change>`, whose last tasks are regression tests, the project's own checks, and a re-audit that must come back SAFE.
3. The gate runs again at archive, scoped to the remediation change.

Keep each remediation change to a coherent set of findings (a severity tier or a surface area) so the archive gate stays focused.
