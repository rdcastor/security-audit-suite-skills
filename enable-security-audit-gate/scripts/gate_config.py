#!/usr/bin/env python3
"""Add, check, replace or remove the security-audit gate in a project's openspec/config.yaml.

The gate is two entries of native OpenSpec operations guidance (OpenSpec >= 1.7):
operations.apply.guidance[] and operations.archive.guidance[]. The generated OpenSpec
apply/archive skills read them from `openspec instructions <op> --json`, and `openspec update`
never touches config.yaml, so the gate survives updates and exists only in projects that opt in.

    gate_config.py --project . --policy ask            # dry run: state + what would change
    gate_config.py --project . --policy ask --apply    # write (append/insert; comments preserved)
    gate_config.py --project . --check                 # exit 0 iff both entries present and current
    gate_config.py --project . --remove --apply        # take the gate out
    gate_config.py --print --policy autofix            # print the YAML block to paste by hand

States: absent, partial (one operation only), policy-mismatch (entries carry another policy than the
one asked for), outdated (entries are from an older suite version; --apply replaces them), present.
Without --policy the policy comes from gate_policy in .security-audit.yaml, else `ask` for --apply
and "whatever is configured" for --check.

The file is edited textually (comments and ordering survive) and re-parsed with PyYAML
afterwards; if the entries did not land, the original text is restored. Structures the
script will not touch (flow-style lists, anchors, a `guidance` that is not a list) exit 2.
Line endings of the original file are preserved.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

MARKER = "security-audit gate ("
OPS = ("apply", "archive")
POLICIES = ("ask", "autofix")

ENTRIES: dict[tuple[str, str], str] = {
    ("apply", "ask"): (
        "security-audit gate (apply, policy=ask): when the last task is marked complete and before "
        "suggesting archive, run the security-audit skill scoped to this change (Skill tool: "
        "skill=security-audit, args=<change-name>). BLOCK: do not suggest archive; surface the "
        "Critical/High findings, add remediation tasks to the tasks file, and pause for the user. "
        "PROCEED_WITH_FIXES: surface the findings and ask whether to fix now or defer before "
        "suggesting archive. SAFE_TO_PROCEED: add 'Security audit: passed' to the completion output."
    ),
    ("apply", "autofix"): (
        "security-audit gate (apply, policy=autofix): when the last task is marked complete and before "
        "suggesting archive, run the security-audit skill scoped to this change (Skill tool: "
        "skill=security-audit, args=<change-name>). Fix every open finding above Low inline, each with a "
        "regression test that fails on the old code, then re-run the skill in re-audit mode until it "
        "returns SAFE_TO_PROCEED or PROCEED_WITH_FIXES with only Low/Info findings open; record those "
        "Low/Info findings as tracked work for the next release (the project backlog or TODO) rather than "
        "pausing. Only an explicit, recorded user decision may leave a finding above Low unfixed. Add the "
        "final verdict to the completion output as 'Security audit: <verdict>'."
    ),
    ("archive", "ask"): (
        "security-audit gate (archive, policy=ask): before assessing delta specs or moving the change, "
        "run the security-audit skill scoped to this change (Skill tool: skill=security-audit, "
        "args=<change-name>), unless a SAFE_TO_PROCEED verdict for this change was produced earlier "
        "in this conversation and nothing changed since (cite it). BLOCK: stop; archive only on an "
        "explicit user override and record the override and its reason in the archive summary. "
        "PROCEED_WITH_FIXES: ask whether to fix now or archive with the findings noted. Always add a "
        "'Security audit: <verdict>' line to the archive summary."
    ),
    ("archive", "autofix"): (
        "security-audit gate (archive, policy=autofix): before assessing delta specs or moving the "
        "change, run the security-audit skill scoped to this change (Skill tool: skill=security-audit, "
        "args=<change-name>), unless a verdict for this change that already meets this gate was produced "
        "earlier in this conversation and nothing changed since (cite it). The gate is met by "
        "SAFE_TO_PROCEED, or by PROCEED_WITH_FIXES whose open findings are all Low/Info, recorded as "
        "tracked work for the next release. Any open finding above Low: fix it inline with a regression "
        "test and re-audit; archive with it unfixed only on an explicit user decision recorded in the "
        "archive summary. Always add a 'Security audit: <verdict>' line to the archive summary."
    ),
}


class Unsafe(Exception):
    """The file has a structure this script will not edit."""


def die(msg: str, code: int):
    print(msg, file=sys.stderr)
    sys.exit(code)


def load_yaml_module():
    try:
        import yaml  # type: ignore
    except ImportError:
        die("PyYAML is required (pip install pyyaml). Paste the block from --print by hand instead.", 5)
    return yaml


def yaml_block(policy: str) -> str:
    lines = ["operations:"]
    for op in OPS:
        lines += [f"  {op}:", "    guidance:", f"      - {json.dumps(ENTRIES[(op, policy)])}"]
    return "\n".join(lines) + "\n"


def find_config(project: Path) -> Path:
    for name in ("config.yaml", "config.yml"):
        p = project / "openspec" / name
        if p.is_file():
            return p
    die(f"no openspec/config.yaml under {project} (is this an OpenSpec project?)", 5)


def parse(yaml, text: str) -> dict:
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise Unsafe("top level of config.yaml is not a mapping")
    return data


def entry_policy(entry: str):
    m = re.search(r"policy=(\w+)", entry)
    return m.group(1) if m else None


def state(data: dict) -> dict:
    """Per-operation: is our entry present, which policy, is its text current, is the shape editable."""
    out: dict = {}
    ops = data.get("operations") or {}
    for op in OPS:
        node = ops.get(op) if isinstance(ops, dict) else None
        guidance = node.get("guidance") if isinstance(node, dict) else None
        ours = [g for g in (guidance or []) if isinstance(g, str) and MARKER in g]
        pol = entry_policy(ours[0]) if ours else None
        out[op] = {
            "present": bool(ours),
            "policy": pol,
            "current": bool(ours) and pol in POLICIES and ours[0] == ENTRIES[(op, pol)] and len(ours) == 1,
            "copies": len(ours),
            "guidance_is_list": guidance is None or isinstance(guidance, list),
            "foreign_entries": len([g for g in (guidance or []) if not (isinstance(g, str) and MARKER in g)]),
        }
    return out


def summarize(st: dict, want) -> str:
    if all(st[o]["present"] for o in OPS):
        pols = {st[o]["policy"] for o in OPS}
        if len(pols) != 1 or (want and pols != {want}):
            return "policy-mismatch"
        if not all(st[o]["current"] for o in OPS):
            return "outdated"
        return "present"
    if any(st[o]["present"] for o in OPS):
        return "partial"
    return "absent"


def configured_policy(st: dict):
    pols = {st[o]["policy"] for o in OPS if st[o]["present"]}
    return pols.pop() if len(pols) == 1 else None


# ---------------------------------------------------------------- textual editing

def split_lines(text: str):
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.split(nl), nl


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def is_blank_or_comment(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")


def block_end(lines, start: int, indent: int) -> int:
    """Index one past the last line belonging to the block whose header is at `start`."""
    i = start + 1
    last = start + 1
    while i < len(lines):
        if is_blank_or_comment(lines[i]):
            i += 1
            continue
        if indent_of(lines[i]) <= indent:
            break
        last = i + 1
        i += 1
    return last


def find_key(lines, key: str, indent: int, lo: int, hi: int):
    pat = re.compile(rf"^ {{{indent}}}{re.escape(key)}:\s*(#.*)?$")
    flow = re.compile(rf"^ {{{indent}}}{re.escape(key)}:\s*\S")
    for i in range(lo, hi):
        if pat.match(lines[i]):
            return i
        if flow.match(lines[i]):
            raise Unsafe(f"'{key}:' at line {i + 1} has an inline value; edit by hand")
    return None


def remove_ours(lines):
    return [l for l in lines if not (MARKER in l and l.lstrip().startswith("- "))]


def first_child_indent(lines, start: int, end: int, default: int) -> int:
    for i in range(start, end):
        if not is_blank_or_comment(lines[i]):
            return indent_of(lines[i])
    return default


def insert_entries(lines, policy: str, ops):
    lines = list(lines)
    for l in lines:
        if not is_blank_or_comment(l) and re.search(r":\s*[&*]\w", l):
            raise Unsafe("YAML anchors/aliases present; edit by hand")
    top = find_key(lines, "operations", 0, 0, len(lines))
    if top is None:
        block = yaml_block(policy).rstrip("\n").split("\n")
        while lines and lines[-1].strip() == "":
            lines.pop()
        return lines + [""] + block
    child = first_child_indent(lines, top + 1, block_end(lines, top, 0), 2)
    for op in ops:
        end = block_end(lines, top, 0)
        op_line = find_key(lines, op, child, top + 1, end)
        item = json.dumps(ENTRIES[(op, policy)])
        if op_line is None:
            lines[end:end] = [f"{' ' * child}{op}:", f"{' ' * (child + 2)}guidance:", f"{' ' * (child + 4)}- {item}"]
            continue
        op_end = block_end(lines, op_line, child)
        g_indent = first_child_indent(lines, op_line + 1, op_end, child + 2)
        g_line = find_key(lines, "guidance", g_indent, op_line + 1, op_end)
        if g_line is None:
            lines[op_line + 1:op_line + 1] = [f"{' ' * g_indent}guidance:", f"{' ' * (g_indent + 2)}- {item}"]
            continue
        g_end = block_end(lines, g_line, g_indent)
        item_indent = g_indent + 2
        for i in range(g_line + 1, g_end):
            if lines[i].lstrip().startswith("- "):
                item_indent = indent_of(lines[i])
                break
        lines[g_end:g_end] = [f"{' ' * item_indent}- {item}"]
    return lines


def prune_empty(yaml, lines, nl: str):
    """After removing our entries, drop guidance/op/operations keys that became empty."""
    for _ in range(6):
        data = parse(yaml, nl.join(lines))
        if "operations" not in data:
            return lines
        ops = data.get("operations")
        top = find_key(lines, "operations", 0, 0, len(lines))
        if top is None:
            return lines
        end = block_end(lines, top, 0)
        if not ops:
            del lines[top:end]
            while top < len(lines) and lines[top].strip() == "" and (top == 0 or lines[top - 1].strip() == ""):
                del lines[top]
            return lines
        child = first_child_indent(lines, top + 1, end, 2)
        changed = False
        for op in OPS:
            if op not in ops:
                continue
            node = ops[op]
            op_line = find_key(lines, op, child, top + 1, end)
            if op_line is None:
                continue
            op_end = block_end(lines, op_line, child)
            if not node:
                del lines[op_line:op_end]
                changed = True
                break
            if isinstance(node, dict) and "guidance" in node and not node["guidance"]:
                g_indent = first_child_indent(lines, op_line + 1, op_end, child + 2)
                g_line = find_key(lines, "guidance", g_indent, op_line + 1, op_end)
                if g_line is not None:
                    del lines[g_line:block_end(lines, g_line, g_indent)]
                    changed = True
                    break
        if not changed:
            return lines
    return lines


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="project root (contains openspec/)")
    ap.add_argument("--policy", choices=POLICIES, help="gate policy (default: gate_policy from .security-audit.yaml, else ask)")
    ap.add_argument("--apply", action="store_true", help="write the change (default is a dry run)")
    ap.add_argument("--check", action="store_true", help="exit 0 iff both entries are present and current (and match --policy if given)")
    ap.add_argument("--remove", action="store_true", help="remove the gate entries instead of adding them")
    ap.add_argument("--print", dest="print_block", action="store_true", help="print the YAML block and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable state on stdout")
    args = ap.parse_args()

    if args.print_block:
        sys.stdout.write(yaml_block(args.policy or "ask"))
        return 0

    yaml = load_yaml_module()
    project = Path(args.project).resolve()
    explicit = args.policy
    if explicit is None:
        prof = project / ".security-audit.yaml"
        if prof.is_file():
            try:
                pdata = yaml.safe_load(prof.read_text(encoding="utf-8")) or {}
                if pdata.get("gate_policy") in POLICIES:
                    explicit = pdata["gate_policy"]
            except Exception:
                pass
    policy = explicit or "ask"

    cfg = find_config(project)
    with cfg.open(encoding="utf-8", newline="") as fh:   # newline="" keeps CRLF visible so it can be preserved
        original = fh.read()
    try:
        st = state(parse(yaml, original))
    except Unsafe as e:
        die(f"UNSAFE: {e}", 2)
    except Exception as e:
        die(f"config.yaml does not parse: {e}", 5)

    if args.check:
        # A check asserts a policy only when one was asked for (flag or profile); otherwise it reports
        # whatever is configured, so a correctly configured project never fails for want of a flag.
        want = explicit
        summary = summarize(st, want)
        ok = summary == "present"
        report = {"config": str(cfg), "state": summary, "policy": configured_policy(st), "operations": st}
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            hint = "" if ok else "  (run with --apply to fix)"
            print(f"{summary} (policy={configured_policy(st) or 'none'}): {cfg}{hint}")
        return 0 if ok else 1

    want = None if args.remove else policy
    summary = summarize(st, want)
    report = {"config": str(cfg), "state": summary, "policy_wanted": policy, "operations": st}

    for op in OPS:
        if not st[op]["guidance_is_list"]:
            die(f"UNSAFE: operations.{op}.guidance is not a list; edit by hand:\n\n{yaml_block(policy)}", 2)

    lines, nl = split_lines(original)
    try:
        if args.remove:
            if summary == "absent":
                print(f"absent: nothing to remove in {cfg}")
                return 0
            new_lines = prune_empty(yaml, remove_ours(lines), nl)
            expect = "absent"
        else:
            if summary == "present":
                print(f"present (policy={policy}): {cfg} already carries both current entries; nothing to do")
                return 0
            base = remove_ours(lines) if summary in ("partial", "policy-mismatch", "outdated") else list(lines)
            new_lines = insert_entries(base, policy, list(OPS))
            expect = "present"
    except Unsafe as e:
        die(f"UNSAFE: {e}\nPlace the entries by hand:\n\n{yaml_block(policy)}", 2)

    new_text = nl.join(new_lines)
    if not new_text.endswith(nl):
        new_text += nl
    try:
        new_state = summarize(state(parse(yaml, new_text)), want)
    except Exception as e:
        die(f"the edited text would not parse ({e}); nothing written. Place the entries by hand:\n\n{yaml_block(policy)}", 2)
    if new_state != expect:
        die(f"edit did not produce the expected state ({new_state} != {expect}); nothing written", 1)

    diff = "".join(difflib.unified_diff(
        original.splitlines(True), new_text.splitlines(True),
        fromfile=f"{cfg.name} (current)", tofile=f"{cfg.name} ({'gate removed' if args.remove else 'with gate'})"))
    if not args.apply:
        print(f"{summary}: {cfg}\nDRY RUN, would apply:\n{diff}")
        if args.json:
            print(json.dumps(report, indent=2))
        return 0
    cfg.write_text(new_text, encoding="utf-8", newline="")
    verify = summarize(state(parse(yaml, cfg.read_text(encoding="utf-8"))), want)
    if verify != expect:
        cfg.write_text(original, encoding="utf-8", newline="")
        die(f"verification after write failed ({verify}); original restored", 1)
    print(f"{'removed' if args.remove else 'present'} (policy={policy}): wrote {cfg} (was {summary})\n{diff}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
