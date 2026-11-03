"""Artifact hardening: how builds run, and what the workflows are allowed to do.
Container-specific checks are in checks/stacks/containers.py."""
import re

from lib import HARDENING, bad, check, info, ok, warn


def run_lines(text):
    """Lines that belong to `run:` steps, one-line or block."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)(-\s+)?run:\s*(.*)$", lines[i])
        i += 1
        if not m:
            continue
        key_col = len(m.group(1)) + len(m.group(2) or "")
        rest = m.group(3)
        if rest and not rest.startswith(("|", ">")):
            yield rest
            continue
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > key_col):
            yield lines[i]
            i += 1


@check(HARDENING)
def workflow_hygiene(repo):
    if not repo.workflows:
        return bad("no workflows")
    out = [ok(f"{len(repo.workflows)} workflow files")]
    for path, text in repo.workflows.items():
        uses = re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", text)
        unpinned = [u for u in uses if not u.startswith(("./", "docker://")) and not re.search(r"@[0-9a-f]{40}$", u)]
        if unpinned:
            out.append(warn(f"{path}: actions not pinned to a full SHA", *unpinned))
        if not re.search(r"(?m)^\s*permissions:", text):
            out.append(warn(f"{path}: no permissions block (inherits the default)"))
        if any(re.search(r"\$\{\{\s*(github\.event\.|github\.head_ref|inputs\.)", line) for line in run_lines(text)):
            out.append(warn(f"{path}: expression inside a run: step (injection risk, pass it through env:)"))
        if "pull_request_target" in text:
            out.append(info(f"{path}: uses pull_request_target (check it never checks out PR code)"))
    return out


@check(HARDENING, when=lambda repo: bool(repo.workflows))
def workflow_tooling(repo):
    wanted = [
        ("checkout with persist-credentials: false", r"persist-credentials: *false"),
        ("zizmor", r"zizmor"),
        ("actionlint", r"actionlint"),
        ("gitleaks in CI", r"gitleaks"),
    ]
    return [ok(label) if repo.ci_has(p) else bad(f"{label} (not found)") for label, p in wanted]
