"""Shared pieces for bootstrap: the gh helpers and the Run context.

Every change goes through Run.do(), which prints the step and only performs it with --apply.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field


def _gh(args, stdin=None):
    return subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=120)


def api_get(endpoint):
    """GET a GitHub API endpoint. Returns parsed JSON, or None when gh fails (404, 403, ...)."""
    p = _gh(["api", endpoint])
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout) if p.stdout.strip() else {}
    except ValueError:
        return None


def api_send(method, endpoint, body=None):
    """PUT/PATCH/POST with a JSON body. Returns (ok, error_text)."""
    args = ["api", "-X", method, endpoint]
    if body is not None:
        args += ["--input", "-"]
    p = _gh(args, stdin=json.dumps(body) if body is not None else None)
    return p.returncode == 0, (p.stderr or p.stdout).strip()[:300]


def gh_command(args):
    """Run any other gh command. Returns (ok, error_text)."""
    p = _gh(args)
    return p.returncode == 0, (p.stderr or p.stdout).strip()[:300]


@dataclass
class Run:
    repo: str
    apply: bool = False
    show: bool = False
    license_id: str = ""
    codeowner: str = ""
    scorecard: bool = False
    lefthook: bool = False
    scaffold: bool = True
    checks: str = ""
    failed: int = 0
    info: dict = field(default_factory=dict)

    @property
    def owner(self):
        return self.repo.split("/")[0]

    @property
    def branch(self):
        return self.info["default_branch"]

    @property
    def is_public(self):
        return self.info["visibility"] == "public"

    def do(self, description, action):
        """Print a step; perform it only with --apply. `action` returns (ok, error_text)."""
        print(f"+ {description}")
        if not self.apply:
            return True
        ok, err = action()
        if not ok:
            self.fail(err)
        return ok

    def fail(self, message):
        print(f"  FAILED: {message}")
        self.failed += 1


def die(message, code=2):
    print(message)
    sys.exit(code)
