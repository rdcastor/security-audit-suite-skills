#!/usr/bin/env python3
"""Hard check on a security-audit verdict: exit 0 only when a change's sidecar says SAFE_TO_PROCEED.

The `security-audit` skill writes `<changeRoot>/security-audit.json` when it runs as an OpenSpec
gate. This script turns that file into an enforceable stop for whichever hook system the project
uses. OpenSpec's guidance is advisory; this is the part that can say no.

    check_verdict.py --change <name> [--root <openspec project root>] [--allow-low | --allow-fixes] [--strict]
    check_verdict.py --staged            # git pre-commit: every staged openspec/changes/archive/*/security-audit.json
    check_verdict.py --from-hook         # Claude Code PreToolUse (Bash): tool call JSON on stdin

--allow-low accepts PROCEED_WITH_FIXES when every open finding is Low or Info (the "Lows never hold a
release" policy); --allow-fixes accepts PROCEED_WITH_FIXES unconditionally.

Exit codes: 0 pass; 1 verdict not accepted; 2 (--from-hook only) any failure, so Claude Code blocks;
3 no sidecar; 4 stale audit (HEAD moved past the audited commit with changes outside openspec/,
or --strict with a dirty tree); 5 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SAFE = "SAFE_TO_PROCEED"
FIXES = "PROCEED_WITH_FIXES"
NON_BLOCKING = ("Low", "Info")


class Options:
    def __init__(self, allow_fixes: bool = False, allow_low: bool = False, strict: bool = False):
        self.allow_fixes = allow_fixes
        self.allow_low = allow_low
        self.strict = strict


def git(root: Path, *args: str):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def change_root(root: Path, name: str) -> Path:
    """Ask the CLI for changeRoot (store-aware); fall back to openspec/changes/<name>."""
    try:
        r = subprocess.run(["openspec", "status", "--change", name, "--json"], cwd=str(root),
                           capture_output=True, text=True, check=False, shell=(sys.platform == "win32"))
        if r.returncode == 0:
            cr = json.loads(r.stdout).get("changeRoot")
            if cr:
                return Path(cr)
    except (OSError, ValueError):
        pass
    return root / "openspec" / "changes" / name


def evaluate(sidecar_text: str, root: Path, opts: Options, label: str):
    try:
        data = json.loads(sidecar_text)
    except ValueError as e:
        return 5, f"{label}: sidecar is not valid JSON ({e})"
    verdict = data.get("verdict")
    open_findings = [f for f in data.get("findings", []) if f.get("status", "open") == "open"]
    accepted_how = ""
    if verdict == SAFE:
        pass
    elif verdict == FIXES and opts.allow_fixes:
        accepted_how = " (fixes allowed)"
    elif verdict == FIXES and opts.allow_low and all(f.get("severity") in NON_BLOCKING for f in open_findings):
        accepted_how = f" (accepted: {len(open_findings)} open finding(s), all Low/Info)"
    elif verdict in (FIXES, "BLOCK"):
        blocking = [f for f in open_findings if f.get("severity") not in NON_BLOCKING]
        return 1, (f"{label}: verdict {verdict} with {len(open_findings)} open finding(s), "
                   f"{len(blocking)} above Low; fix and re-audit, or override explicitly")
    else:
        return 5, f"{label}: unrecognised verdict {verdict!r}"
    audited = data.get("commit")
    head = git(root, "rev-parse", "HEAD")
    if audited and head and audited != head:
        moved = git(root, "diff", "--name-only", f"{audited}..{head}")
        if moved is None:
            return 4, f"{label}: audited commit {audited[:10]} is not in this history; re-audit"
        code = [p for p in moved.splitlines() if p and not p.startswith("openspec/")]
        if code:
            return 4, f"{label}: stale audit ({audited[:10]} -> {head[:10]} changed {len(code)} file(s) outside openspec/); re-audit"
    if opts.strict:
        dirty = git(root, "status", "--porcelain")
        if dirty:
            return 4, f"{label}: --strict and the working tree is dirty; commit or re-audit"
    return 0, f"{label}: {verdict}{accepted_how}"


def check_change(root: Path, name: str, opts: Options):
    sidecar = change_root(root, name) / "security-audit.json"
    if not sidecar.is_file():
        return 3, f"{name}: no security-audit.json at {sidecar}; run the security-audit skill for this change"
    return evaluate(sidecar.read_text(encoding="utf-8"), root, opts, name)


def check_staged(root: Path, opts: Options):
    status = git(root, "diff", "--cached", "--name-status", "-M")
    if status is None:
        return 5, "not a git repository"
    archived: dict = {}
    for line in status.splitlines():
        parts = line.split("\t")
        path = parts[-1]
        m = re.match(r"^openspec/changes/archive/([^/]+)/(.*)$", path)
        if m and parts[0][0] in "ARC":
            archived.setdefault(m.group(1), False)
            if m.group(2) == "security-audit.json":
                archived[m.group(1)] = True
    if not archived:
        return 0, "no archived change staged"
    worst, msgs = 0, []
    for name, has in sorted(archived.items()):
        if not has:
            worst = max(worst, 3)
            msgs.append(f"{name}: archived without security-audit.json")
            continue
        blob = git(root, "show", f":openspec/changes/archive/{name}/security-audit.json")
        code, msg = evaluate(blob or "", root, opts, name)
        worst = max(worst, code)
        msgs.append(msg)
    return worst, "\n".join(msgs)


ARCHIVE_CMD = re.compile(r"openspec\s+archive(?:\s+--?[\w-]+(?:[= ]\S+)?)*\s+[\"']?([A-Za-z0-9._-]+)[\"']?")
ARCHIVE_MV = re.compile(r"\bmv\s+[\"']?\S*?openspec[\\/]changes[\\/]([A-Za-z0-9._-]+)[\"']?\s+[\"']?\S*archive[\\/]")


def check_from_hook(root: Path, opts: Options):
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0, "no tool-call JSON on stdin; not blocking"
    if payload.get("tool_name") != "Bash":
        return 0, "not a Bash call"
    cmd = str((payload.get("tool_input") or {}).get("command", ""))
    m = ARCHIVE_CMD.search(cmd) or ARCHIVE_MV.search(cmd)
    if not m:
        if re.search(r"openspec\s+archive\b", cmd):
            return 0, "openspec archive without a change name: cannot check, not blocking"
        return 0, "not an archive command"
    name = m.group(1)
    if name in ("archive", "--yes", "--skip-specs"):
        return 0, "could not extract a change name; not blocking"
    code, msg = check_change(root, name, opts)
    return (0, msg) if code == 0 else (2, "security-audit gate: " + msg)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--change", help="change name to check")
    ap.add_argument("--staged", action="store_true", help="git pre-commit mode")
    ap.add_argument("--from-hook", action="store_true", help="Claude Code PreToolUse mode (tool call on stdin)")
    ap.add_argument("--root", default=".", help="OpenSpec project root (default: cwd)")
    ap.add_argument("--allow-fixes", action="store_true", help="accept PROCEED_WITH_FIXES unconditionally")
    ap.add_argument("--allow-low", action="store_true", help="accept PROCEED_WITH_FIXES when every open finding is Low or Info")
    ap.add_argument("--strict", action="store_true", help="also fail when the working tree is dirty")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    opts = Options(allow_fixes=args.allow_fixes, allow_low=args.allow_low, strict=args.strict)
    if args.from_hook:
        code, msg = check_from_hook(root, opts)
    elif args.staged:
        code, msg = check_staged(root, opts)
    elif args.change:
        code, msg = check_change(root, args.change, opts)
    else:
        ap.print_usage(sys.stderr)
        return 5
    print(msg, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
