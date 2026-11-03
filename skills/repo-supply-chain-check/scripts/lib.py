"""Shared pieces for the audit: the gh helper, the Repo context, results, and the check registry.

A check is a function that takes a Repo and returns one Result or a list of them.
Register it under one of the six areas with @check(AREA). Pass when=<function> to run it
only for repos where the function returns True; an area where no check ran is "n/a".
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from functools import cached_property

HARDENING = "Artifact hardening"
DEPENDENCIES = "Dependency management"
REPOSITORIES = "Artifact repositories"
SBOM = "SBOM"
SLSA = "SLSA"
GOLDEN_PATH = "Golden path (enforced controls)"
AREAS = [HARDENING, DEPENDENCIES, REPOSITORIES, SBOM, SLSA, GOLDEN_PATH]


# ---------------------------------------------------------------- results

@dataclass(frozen=True)
class Result:
    status: str  # ok | warn | bad | info
    message: str
    detail: tuple = ()


def ok(message, *detail):
    return Result("ok", message, detail)


def warn(message, *detail):
    return Result("warn", message, detail)


def bad(message, *detail):
    return Result("bad", message, detail)


def info(message, *detail):
    return Result("info", message, detail)


# ---------------------------------------------------------------- registry

@dataclass
class Check:
    area: str
    fn: object
    when: object = None


CHECKS: list[Check] = []


def check(area, when=None):
    def register(fn):
        CHECKS.append(Check(area, fn, when))
        return fn
    return register


def run_checks(repo):
    """Run every registered check. Returns {area: [Result]}; an area with no applicable check is empty."""
    results = {area: [] for area in AREAS}
    for c in CHECKS:
        if c.when and not c.when(repo):
            continue
        try:
            out = c.fn(repo)
        except Exception as exc:  # one broken check must not hide the rest
            out = warn(f"check {c.fn.__name__} failed: {exc}")
        if out is None:
            continue
        results[c.area].extend(out if isinstance(out, list) else [out])
    return results


def area_status(results):
    """met | partial | gap | n/a for the results of one area."""
    statuses = {r.status for r in results}
    if "bad" in statuses:
        return "gap"
    if "warn" in statuses:
        return "partial"
    if "ok" in statuses:
        return "met"
    return "n/a"


# ---------------------------------------------------------------- gh

def _gh(args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", timeout=60)


def api(endpoint, *flags):
    """GET a GitHub API endpoint. Returns parsed JSON, or None when gh fails (404, 403, ...)."""
    p = _gh(["api", endpoint, *flags])
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout) if p.stdout.strip() else {}
    except ValueError:
        return None


def api_ok(endpoint):
    """True when the endpoint answers 2xx (for settings that return 204 with no body)."""
    return _gh(["api", endpoint, "--silent"]).returncode == 0


def raw_file(repo, path, ref):
    p = _gh(["api", "-H", "Accept: application/vnd.github.raw+json", f"repos/{repo}/contents/{path}?ref={ref}"])
    return p.stdout if p.returncode == 0 else ""


# ---------------------------------------------------------------- the repo being audited

class Repo:
    def __init__(self, name):
        self.name = name
        self.owner = name.split("/")[0]
        self._files = {}

    def api(self, path, *flags):
        return api(f"repos/{self.name}/{path}", *flags)

    def api_ok(self, path):
        return api_ok(f"repos/{self.name}/{path}")

    @cached_property
    def info(self):
        return api(f"repos/{self.name}") or {}

    @property
    def branch(self):
        return self.info.get("default_branch", "main")

    @property
    def security_and_analysis(self):
        return self.info.get("security_and_analysis") or {}

    @cached_property
    def tree(self):
        data = self.api(f"git/trees/{self.branch}?recursive=1") or {}
        return [t["path"] for t in data.get("tree", []) if t["type"] == "blob"]

    def files(self, pattern):
        """Paths in the repo matching a regex (case-insensitive)."""
        return [p for p in self.tree if re.search(pattern, p, re.I)]

    def has_file(self, pattern):
        return bool(self.files(pattern))

    def read(self, path):
        """Text of a file on the default branch; empty string when missing."""
        if path not in self._files:
            self._files[path] = raw_file(self.name, path, self.branch)
        return self._files[path]

    @cached_property
    def workflows(self):
        return {p: self.read(p) for p in self.files(r"^\.github/workflows/.*\.ya?ml$")}

    @cached_property
    def workflow_text(self):
        """All workflow files joined, with full-line comments removed so a mention in a comment doesn't count."""
        lines = (line for text in self.workflows.values() for line in text.splitlines())
        return "\n".join(line for line in lines if not line.lstrip().startswith("#"))

    @cached_property
    def build_lines(self):
        """Non-comment lines of workflows and Dockerfiles: where installs actually happen."""
        texts = list(self.workflows.values()) + [self.read(p) for p in self.files(r"(^|/)Dockerfile")]
        return [line.strip() for t in texts for line in t.splitlines() if not line.lstrip().startswith("#")]

    def build_commands(self, pattern, unless=None):
        """Build/CI lines matching a regex, minus those that also match `unless`."""
        return [line for line in self.build_lines if re.search(pattern, line) and not (unless and re.search(unless, line))]

    def ci_has(self, pattern):
        return bool(re.search(pattern, self.workflow_text, re.I))
