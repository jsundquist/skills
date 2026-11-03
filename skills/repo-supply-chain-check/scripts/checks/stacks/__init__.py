"""Language and tool specifics live here, one entry per stack.

To support another ecosystem, add a Stack to STACKS. The generic dependency checks
(Dependabot coverage, lockfile committed, vulnerability audit in CI) pick it up on their own.
Checks that only make sense for one stack go in their own module next to this file.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stack:
    name: str
    detect: str            # regex over repo paths: the stack is "present" when a path matches
    dependabot: tuple      # Dependabot package-ecosystem names that cover it
    lockfile: str = ""     # regex for a lock file; empty when the stack has none
    lock_required: bool = False  # missing lock file is a gap (True) or a warning (False)
    audit: str = ""        # regex for the CI tools that audit its dependencies


STACKS = [
    Stack("node", r"(^|/)package\.json$", ("npm",),
          lockfile=r"(^|/)(pnpm-lock\.yaml|package-lock\.json|yarn\.lock)$", lock_required=True,
          audit=r"pnpm audit|npm audit|yarn audit|osv-scanner"),
    Stack("python", r"(^|/)(pyproject\.toml|requirements.*\.txt|Pipfile|poetry\.lock|uv\.lock)$", ("pip", "uv"),
          lockfile=r"(^|/)(uv\.lock|poetry\.lock|Pipfile\.lock|requirements.*\.txt)$",
          audit=r"pip-audit|osv-scanner|safety check"),
    Stack("containers", r"(^|/)Dockerfile", ("docker",)),
    Stack("github-actions", r"^\.github/workflows/.*\.ya?ml$", ("github-actions",)),
]


def detected(repo):
    """The stacks present in this repo."""
    return [s for s in STACKS if repo.has_file(s.detect)]
