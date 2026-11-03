#!/usr/bin/env python3
"""Read-only supply-chain audit of one GitHub repository, using the gh CLI.

    python audit.py OWNER/REPO               # full report, ending with a summary of six areas
    python audit.py OWNER/REPO --gaps        # only warnings and gaps
    python audit.py OWNER/REPO --strict      # exit 1 when any area has a gap

Needs Python 3.11+ and gh (logged in, with admin on the target for the settings calls).
Add a check: write a function in checks/<area>.py and decorate it with @check(AREA).
Support another language or tool: add a Stack in checks/stacks/__init__.py.
"""
import argparse
import sys

from lib import AREAS, Repo, area_status, run_checks

# Importing a module registers its checks. Order here is the order within each area.
from checks import golden_path, hardening, dependencies, repositories, sbom, slsa  # noqa: F401
from checks.stacks import containers, node, python  # noqa: F401

ICONS = {"ok": "✅", "warn": "⚠️ ", "bad": "❌", "info": "ℹ️ "}
LABELS = {"met": "✅ met", "partial": "⚠️  partial", "gap": "❌ gap", "n/a": "n/a (nothing of this kind in the repo)"}


def main():
    parser = argparse.ArgumentParser(description="Read-only supply-chain audit of a GitHub repository.")
    parser.add_argument("repo", metavar="OWNER/REPO")
    parser.add_argument("--gaps", action="store_true", help="show only warnings and gaps")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any area has a gap")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    repo = Repo(args.repo)
    if not repo.info:
        print(f"cannot read {args.repo} (is gh logged in, and does the repo exist?)")
        return 2

    results = run_checks(repo)
    print(f"# Supply-chain audit: {repo.name} ({repo.branch})")
    for area in AREAS:
        print(f"\n## {area}")
        if area_status(results[area]) == "n/a":
            print("n/a (nothing of this kind in the repo)")
            continue
        shown = [r for r in results[area] if not args.gaps or r.status in ("warn", "bad")]
        if not shown:
            print("no gaps")
        for r in shown:
            print(f"{ICONS[r.status]} {r.message}")
            for line in r.detail:
                print(f"     {line}")

    print("\n## Summary by area")
    statuses = {area: area_status(results[area]) for area in AREAS}
    for area in AREAS:
        print(f"{area:<34} {LABELS[statuses[area]]}")
    return 1 if args.strict and "gap" in statuses.values() else 0


if __name__ == "__main__":
    sys.exit(main())
