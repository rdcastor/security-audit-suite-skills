# `.security-audit.yaml`: optional per-project profile

Place it at the repository root to tune the suite for one project. Every key is optional; no file means defaults. Explicit arguments a caller passes to a skill win over the profile, and the profile wins over defaults.

```yaml
version: 1

# Paths (gitignore-style globs, relative to the repo root) that are never audited:
# vendored code, generated files, data dumps, model weights.
exclude_paths:
  - "vendor/**"
  - "data/**"
  - "**/*.min.js"

# Paths that are always Tier 1 (read in full) even in a large scope: prompt builders,
# tool definitions, retrieval pipelines, anything that turns untrusted text into model input.
llm_sensitive_paths:
  - "backend/prompts/**"
  - "backend/tools/**"

# Optional dependency allow-list. When present, a new direct dependency that is not listed
# is reported (Medium, Confidence High) so unexpected additions get noticed.
allowed_deps:
  - fastapi
  - pymongo

# OWASP Top 10 edition to cite: 2021 (default) or 2025.
owasp_year: 2021

# How the OpenSpec gate reacts to a non-SAFE verdict. Mirrors the policy chosen when
# enable-security-audit-gate wrote openspec/config.yaml; keep the two in agreement.
#   ask     - surface findings and ask the user whether to fix now, defer, or override (default)
#   autofix - remediate actionable findings inline, re-audit until SAFE_TO_PROCEED, and never
#             archive on a non-SAFE verdict without an explicit, recorded override
gate_policy: ask

# Where ad-hoc reports go (no OpenSpec change, no caller-specified path) when they are too
# long to return inline.
report_dir: .security-audit
```

## How each skill uses it

| Key | security-audit | prepare-full-codebase-security-audit | remediate-security-findings | enable-security-audit-gate |
|---|---|---|---|---|
| `exclude_paths` | dropped from scope; listed under Coverage, Skipped | dropped from enumeration; listed in the proposal's Non-Goals | no | no |
| `llm_sensitive_paths` | always Tier 1 | promoted to a Critical-tier chunk | no | no |
| `allowed_deps` | unexpected new dependencies become findings | no | no | no |
| `owasp_year` | OWASP mapping edition | no | edition in the findings table | no |
| `gate_policy` | reported in the OpenSpec section | no | no | default for `--policy` |
| `report_dir` | ad-hoc report location | no | no | no |

The profile is a hint for scoping and triage. It never suppresses a finding in a file that was audited, and an `exclude_paths` entry that hides a Tier-1 file is itself worth a line in section 0.5.
