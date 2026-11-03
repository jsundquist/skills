"""Starter files: rendered from templates/, created only when absent, never overwritten.

When the default branch is already protected, direct commits would be rejected, so new files
go on a work branch and one PR is opened instead.
"""
import base64
import re
from datetime import date
from pathlib import Path

from lib import api_get, api_send, gh_command

TEMPLATES = Path(__file__).resolve().parent.parent.parent / "templates"
WORK_BRANCH = "chore/supply-chain-bootstrap"

# Action versions. Each is resolved to a full commit SHA when the script runs, because the
# settings turn on "require actions pinned to a full SHA". Dependabot bumps them afterwards.
PINS = {
    "actions/checkout": "v7.0.1",
    "zizmorcore/zizmor-action": "v0.8.1",
    "gitleaks/gitleaks-action": "v3.0.0",
    "actions/dependency-review-action": "v5.0.0",
    "raven-actions/actionlint": "v2.2.0",
    "ossf/scorecard-action": "v2.5.0",
    "github/codeql-action": "v4.39.2",
}

PLACEHOLDER = re.compile(r"\{\{([a-z]+)(?::([^}\s]*))?\}\}")  # {{repo}} or {{pin:owner/repo[/path]}}; not ${{ expr }}
_sha_cache = {}


def resolve_sha(repo, tag):
    if (repo, tag) not in _sha_cache:
        commit = api_get(f"repos/{repo}/commits/{tag}")
        if not commit:
            raise ValueError(f"cannot resolve {repo}@{tag}")
        _sha_cache[(repo, tag)] = commit["sha"]
    return _sha_cache[(repo, tag)]


def render(run, template):
    values = {"repo": run.repo, "branch": run.branch, "codeowner": run.codeowner,
              "publish": "true" if run.is_public else "false"}  # Scorecard publishes results only for public repos

    def replace(m):
        kind, arg = m.group(1), m.group(2)
        if arg is None:
            return values[kind]
        repo = "/".join(arg.split("/")[:2])
        if repo not in PINS:
            raise ValueError(f"no pinned version for {repo}")
        sha = resolve_sha(repo, PINS[repo])
        return {"pin": f"{arg}@{sha} # {PINS[repo]}", "sha": sha, "ver": PINS[repo].lstrip("v")}[kind]

    return PLACEHOLDER.sub(replace, template.read_text(encoding="utf-8"))


def branch_is_protected(run):
    rulesets = api_get(f"repos/{run.repo}/rulesets") or []
    active = any(r.get("target") == "branch" and r.get("enforcement") == "active" for r in rulesets)
    return active or api_get(f"repos/{run.repo}/branches/{run.branch}/protection") is not None


class Files:
    """Creates files on the default branch, or on a work branch when the default branch is protected."""

    def __init__(self, run):
        self.run = run
        self.pr_mode = branch_is_protected(run)
        self.branch_ready = False
        self.added = 0

    def exists(self, path):
        refs = [self.run.branch] + ([WORK_BRANCH] if self.pr_mode else [])
        return any(api_get(f"repos/{self.run.repo}/contents/{path}?ref={ref}") is not None for ref in refs)

    def ensure_work_branch(self):
        if self.branch_ready:
            return True
        sha = (api_get(f"repos/{self.run.repo}/git/ref/heads/{self.run.branch}") or {}).get("object", {}).get("sha")
        ok, err = api_send("POST", f"repos/{self.run.repo}/git/refs", {"ref": f"refs/heads/{WORK_BRANCH}", "sha": sha})
        if not ok and "already exists" not in err.lower():
            self.run.fail(f"could not create {WORK_BRANCH}: {err}")
            return False
        self.branch_ready = True
        return True

    def put(self, path, body):
        run = self.run
        if self.exists(path):
            print(f"= {path} exists, left alone")
            return
        target = WORK_BRANCH if self.pr_mode else run.branch
        where = f" (on {WORK_BRANCH}, via PR)" if self.pr_mode else ""
        print(f"+ create {path}{where}")
        if run.show:
            print("\n".join(f"    | {line}" for line in body.splitlines()))
        if not run.apply or (self.pr_mode and not self.ensure_work_branch()):
            return
        ok, err = api_send("PUT", f"repos/{run.repo}/contents/{path}", {
            "message": f"chore(security): add {path}",
            "content": base64.b64encode(body.encode("utf-8")).decode("ascii"),
            "branch": target})
        if ok:
            self.added += 1
        else:
            run.fail(err)

    def open_pr(self):
        run = self.run
        if not self.pr_mode:
            return
        if not run.apply:
            print(f"({run.branch} is protected: any new files would go on {WORK_BRANCH} and open a PR)")
        elif self.added:
            run.do("open a pull request for the new files", lambda: gh_command([
                "pr", "create", "-R", run.repo, "--head", WORK_BRANCH, "--base", run.branch,
                "--title", "chore(security): add supply-chain starter files",
                "--body", "Files added by supply-chain-audit bootstrap. Merge once the checks pass."]))
        else:
            print("(no new files to propose)")


def scaffold(run, files, template_dir):
    for template in sorted(p for p in template_dir.rglob("*") if p.is_file()):
        rel = template.relative_to(template_dir).as_posix()
        if rel == ".github/CODEOWNERS" and not run.codeowner:
            print(f"! skipping {rel}: {run.repo} is owned by an organization; pass --codeowner @user-or-@org/team")
            continue
        try:
            files.put(rel, render(run, template))
        except ValueError as err:
            run.fail(f"could not render {rel}: {err}")


def add_license(run, files):
    lic = api_get(f"licenses/{run.license_id}")
    if not lic:
        run.fail(f"unknown license id '{run.license_id}' (see: gh api licenses --jq '.[].key')")
        return
    owner = api_get(f"users/{run.owner}") or {}
    body = lic["body"].replace("[year]", str(date.today().year)).replace("[fullname]", owner.get("name") or run.owner)
    files.put("LICENSE", body)


def apply_files(run):
    """Returns the Files object so later steps know whether a PR is pending."""
    files = Files(run)
    if run.scaffold:
        print("\n# Starter files (pinned action SHAs are resolved now)")
        scaffold(run, files, TEMPLATES / "default")
        if run.scorecard:
            scaffold(run, files, TEMPLATES / "scorecard")
        if run.lefthook:
            scaffold(run, files, TEMPLATES / "lefthook")
    if run.license_id:
        print()
        add_license(run, files)
    files.open_pr()
    return files
