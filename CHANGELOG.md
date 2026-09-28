# Changelog

## 2.0.0 (2026-09-28)

The gate moves into OpenSpec's native per-project configuration. Nothing is patched into generated files any more.

### Added
- `enable-security-audit-gate`: per-project opt-in. Writes `operations.apply.guidance` and `operations.archive.guidance` into `openspec/config.yaml` (OpenSpec 1.7 or newer), with `ask` or `autofix` policy; comment-preserving, idempotent, reversible (`scripts/gate_config.py`).
- `scripts/check_verdict.py`: hard verdict check on the audit sidecar for git pre-commit (`--staged`), Claude Code PreToolUse (`--from-hook`, exit 2 blocks `openspec archive`), and OpenSpec `beforeArchive` once lifecycle hooks ship. Detects stale audits by comparing the sidecar's commit with HEAD.
- `security-audit/references/sinks.md`: per-language sink grep checklist used before reading.
- `security-audit/references/project-profile.md`: the `.security-audit.yaml` profile (`exclude_paths`, `llm_sensitive_paths`, `allowed_deps`, `owasp_year`, `gate_policy`, `report_dir`).
- This changelog.

### Changed
- `security-audit` 2.0: explicit per-project opt-in rule; secret values are never copied into reports; every candidate is verified against source, sink and reachability before it becomes a finding; severity and confidence rubrics; `Info` level; stable finding IDs (`F1`, `F2`, ...) in headings and sidecar; sidecar gains `skill_version`, `commit`, `dirty` and per-finding `status`; re-audit mode diffs from the recorded commit; ad-hoc long reports go to `.security-audit/<timestamp>-<slug>.md` instead of one shared root file; OWASP LLM Top 10 mapping for LLM findings; static-only guardrail.
- `prepare-full-codebase-security-audit` 1.1: enumerates with `git ls-files` (+ untracked, not ignored) instead of `find`; honours `exclude_paths` and `llm_sensitive_paths`; skill-location check accepts a global install; chunk tasks write sidecars and the merge produces `findings-report.json` with `C<NN>-F<k>` IDs; fetches per-artifact instructions so project rules apply.
- `remediate-security-findings` 1.1: also reads merged `findings-report.json`; skips `resolved` findings; keeps IDs verbatim; verification tasks use the project's own checks instead of `py_compile`; regression test per finding and a re-audit that must come back SAFE.
- README and overview rewritten for the config-based gate; install is global, enable is per project.

### Removed
- `restore-openspec-audit-gate`. It patched the generated `openspec-apply-change` / `openspec-archive-change` files and could not reconstruct the archive gate after `openspec update` had wiped it (it pointed at the wiped file for the canonical text). Replaced by `enable-security-audit-gate`; see "Migrating from 1.x" in the README.

## 1.1 (security-audit only)

- Trailing `**VERDICT: <TOKEN>**` line, working-tree-inclusive scope enumeration, triage tiers and Coverage section, LLM/prompt-injection class, file overflow with JSON sidecar, re-audit mode, Confidence field, graduated verdict policy.

## 1.0

- Initial suite: `security-audit`, `prepare-full-codebase-security-audit`, `remediate-security-findings`, `restore-openspec-audit-gate`, overview.
