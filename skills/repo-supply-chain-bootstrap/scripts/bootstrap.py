#!/usr/bin/env python3
"""Apply baseline supply-chain settings and starter files to a GitHub repo with the gh CLI.
Prints each step first. Dry run unless you pass --apply. Safe to run again.

    python bootstrap.py owner/repo                          # show what it would do (--show prints the files)
    python bootstrap.py owner/repo --apply                  # settings, starter files, then the ruleset

One pass: it commits the starter files, waits (up to 8 minutes) for their workflows to report on
the default branch, then creates the default-branch ruleset requiring those checks. A required
check must have reported before it can be required, which is why it waits. If the wait times out,
run the same command again. It never touches secrets, tags or releases.

Options:
  --apply          execute (default is a dry run)
  --checks LIST    require these checks in the default-branch ruleset (comma-separated). The default is
                   "default": the checks the starter workflows define. The ruleset is created, or
                   updated in place if it exists
  --no-ruleset     do not create the ruleset
  --scorecard      also add .github/workflows/scorecard.yml
  --lefthook       also add lefthook.yml (pre-commit: gitleaks, actionlint, zizmor); each clone runs `lefthook install`
  --license ID     also add a LICENSE from GitHub's license list (mit, apache-2.0, ...); never defaulted
  --codeowner X    code owner for .github/CODEOWNERS: @user or @org/team. Defaults to the repo owner on a
                   personal account; required on an organization-owned repo
  --no-scaffold    settings only; do not add files (the ruleset is then skipped unless you pass --checks)
  --show           print the rendered files in the dry run

When the default branch is already protected, new files go on a branch and one PR is opened; the
ruleset is then left as it is until the PR has merged and the checks have reported.

Needs Python 3.11+ and gh (logged in, admin on the target). To change what it does:
settings are a table in steps/settings.py; starter files are in templates/; pinned action
versions are in steps/files.py; the ruleset is in steps/ruleset.py.
"""
import argparse
import sys

from lib import Run, api_get, die
from steps.files import apply_files
from steps.ruleset import apply_ruleset
from steps.settings import apply_settings


def parse_args():
    p = argparse.ArgumentParser(description="Apply baseline supply-chain settings and starter files to a GitHub repo.")
    p.add_argument("repo", metavar="OWNER/REPO")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--checks", default=None, metavar="LIST|default")
    p.add_argument("--no-ruleset", action="store_true")
    p.add_argument("--scorecard", action="store_true")
    p.add_argument("--lefthook", action="store_true")
    p.add_argument("--license", dest="license_id", default="", metavar="ID")
    p.add_argument("--codeowner", default="", metavar="@x")
    p.add_argument("--no-scaffold", dest="scaffold", action="store_false")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


def build_run(args):
    checks = args.checks if args.checks is not None else ("default" if args.scaffold else "")
    if args.no_ruleset:
        checks = ""
    run = Run(args.repo, args.apply, args.show, args.license_id, args.codeowner, args.scorecard, args.lefthook, args.scaffold, checks)
    run.info = api_get(f"repos/{args.repo}") or {}
    if not run.info:
        die(f"cannot read {args.repo}", 1)
    if run.codeowner and not run.codeowner.startswith("@"):
        die(f"--codeowner must start with @ (for example @{run.owner} or @{run.owner}/team)")
    if not run.codeowner and (api_get(f"users/{run.owner}") or {}).get("type") == "User":
        run.codeowner = f"@{run.owner}"  # personal account: the owner is the default code owner
    return run


def main():
    args = parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    run = build_run(args)
    mode = "APPLY" if run.apply else "dry run, pass --apply to execute"
    print(f"# {run.repo} ({run.info['visibility']}, default branch {run.branch}) ({mode})")

    apply_settings(run)
    files = apply_files(run)
    apply_ruleset(run, files_in_pr=files.pr_mode)

    print()
    if run.failed:
        print(f"{run.failed} step(s) failed, see FAILED lines above. Everything else was applied.")
    print(f"Still manual: secrets (gh secret set NAME --repo {run.repo}; GITLEAKS_LICENSE if the owner is an organization), "
          "build/release workflows, tagging a release.")
    return 1 if run.failed else 0


if __name__ == "__main__":
    sys.exit(main())
