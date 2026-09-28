# Gate guidance: the entries, the hooks, and why they are shaped this way

`scripts/gate_config.py` is the authoritative source of the entry text (`gate_config.py --print --policy ask|autofix` prints the block below). This file explains them and holds the hook snippets.

## How OpenSpec consumes the entries

`openspec instructions apply --change <name> --json` and `openspec instructions archive --change <name> --json` return `operationGuidance`, an array of the strings under `operations.<op>.guidance` in `openspec/config.yaml` (OpenSpec 1.7 or newer; only `apply` and `archive` are valid operation ids, and only `guidance` is a valid key under each). The generated `openspec-apply-change` and `openspec-archive-change` skills say, in their own text, to "read and consider every entry, and follow entries that are applicable and compatible with the built-in workflow", to keep guidance separate from CLI-controlled state, and never to use it to bypass a blocked state or skip a prompt. The gate entries are written to fit inside those limits: they add a step and a user confirmation; they do not remove any built-in check.

Each entry is a single line. The CLI flattens control characters when it prints guidance as text, so a multi-line entry would be squashed anyway.

## The entries

```yaml
operations:
  apply:
    guidance:
      - "security-audit gate (apply, policy=ask): when the last task is marked complete and before suggesting archive, run the security-audit skill scoped to this change (Skill tool: skill=security-audit, args=<change-name>). BLOCK: do not suggest archive; surface the Critical/High findings, add remediation tasks to the tasks file, and pause for the user. PROCEED_WITH_FIXES: surface the findings and ask whether to fix now or defer before suggesting archive. SAFE_TO_PROCEED: add 'Security audit: passed' to the completion output."
  archive:
    guidance:
      - "security-audit gate (archive, policy=ask): before assessing delta specs or moving the change, run the security-audit skill scoped to this change (Skill tool: skill=security-audit, args=<change-name>), unless a SAFE_TO_PROCEED verdict for this change was produced earlier in this conversation and nothing changed since (cite it). BLOCK: stop; archive only on an explicit user override and record the override and its reason in the archive summary. PROCEED_WITH_FIXES: ask whether to fix now or archive with the findings noted. Always add a 'Security audit: <verdict>' line to the archive summary."
```

`policy=autofix` swaps the reaction to a non-SAFE verdict: remediate every actionable finding inline with a regression test each, re-run `security-audit` in re-audit mode until it returns SAFE_TO_PROCEED, never archive on a non-SAFE verdict without an explicit override recorded in the summary, and turn deferred Low/Info items into tracked work. Print the exact text with `gate_config.py --print --policy autofix`.

The prefix `security-audit gate (` is the marker the script uses to find, replace, and remove its own entries. Keep it if you edit an entry by hand.

## Hard check: `scripts/check_verdict.py`

Reads `<changeRoot>/security-audit.json` (written by `security-audit` when it runs as the gate) and exits:

| Exit | Meaning |
|---|---|
| 0 | verdict `SAFE_TO_PROCEED` and the audit is not stale |
| 1 | verdict `BLOCK` or `PROCEED_WITH_FIXES` (`--allow-low` accepts the latter when every open finding is Low or Info, the "Lows never hold a release" policy; `--allow-fixes` accepts it unconditionally) |
| 2 | in `--from-hook` mode: any failure, because Claude Code blocks a tool call on exit 2 |
| 3 | no sidecar for the change |
| 4 | stale: HEAD moved past the sidecar's `commit` with changes outside `openspec/`, or `--strict` and the tree is dirty |
| 5 | usage error |

Modes: `--change <name>` (explicit), `--staged` (git pre-commit), `--from-hook` (Claude Code PreToolUse). `--root <dir>` points at the OpenSpec root when it is not the cwd.

### git pre-commit

```sh
#!/bin/sh
# Refuse to commit an archived change whose security audit is missing or not SAFE.
python scripts/check_security_verdict.py --staged || exit 1
```

Copy `check_verdict.py` to `scripts/check_security_verdict.py` (or the project's `.claude/hooks/` when Claude Code is used) so the path stays repo-relative. Use `--allow-fixes` if the project archives on PROCEED_WITH_FIXES after the user's acknowledgement.

### Claude Code PreToolUse hook (project `.claude/settings.json`)

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/check_security_verdict.py --from-hook"
          }
        ]
      }
    ]
  }
}
```

Claude Code runs the command from the project root with the tool call as JSON on stdin. The script exits 0 for any Bash command that is not an archive, so the hook is silent in normal work; on a blocked archive it prints the reason to stderr, which Claude Code shows to the agent. If the archive command cannot be parsed (an interactive `openspec archive` with no name) the script does not block, and says so on stderr.

### OpenSpec `beforeArchive` (future)

When Fission-AI/OpenSpec#1910 lands, the same script is the hook command, for example `python scripts/check_security_verdict.py --change "$CHANGE"` with whatever variable the release documents.

## Placing entries by hand

When `gate_config.py` exits 2 (flow-style `guidance: [...]`, YAML anchors, or a `guidance` value that is not a list), paste the block above into `openspec/config.yaml` under the existing `operations:` key, keeping one entry per operation, then run `gate_config.py --check`.
