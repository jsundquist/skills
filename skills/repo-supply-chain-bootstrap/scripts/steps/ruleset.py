"""The default-branch ruleset: no deletion, no force-push, PR with review, required status checks."""
import json
import time

from lib import api_get, api_send

NAME = "Protect default branch"
DEFAULT_CHECKS = "zizmor,actionlint,gitleaks,dependency-review,dependabot-coverage"  # jobs in the starter workflows
WAIT_SECONDS = 480  # how long to wait for the starter workflows to report on the default branch
POLL_SECONDS = 15


def has_codeowners(run):
    paths = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
    return bool(run.codeowner) or any(api_get(f"repos/{run.repo}/contents/{p}") is not None for p in paths)


def build(run, checks, with_codeowners):
    return {
        "name": NAME,
        "target": "branch",
        "enforcement": "active",
        # The admin role may bypass for pull requests only, so a solo owner can still merge their own PR.
        # With a second maintainer, delete this entry and raise the approval count.
        "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": with_codeowners,
                "require_last_push_approval": True,
                "required_review_thread_resolution": False}},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [{"context": c} for c in checks]}},
        ],
    }


def reported_checks(run):
    runs = api_get(f"repos/{run.repo}/commits/{run.branch}/check-runs?per_page=100") or {}
    return {c["name"] for c in runs.get("check_runs", [])}


def wait_for_checks(run, checks):
    """Wait until every check has reported on the default branch. Returns the ones still missing."""
    deadline = time.monotonic() + WAIT_SECONDS
    last = None
    while True:
        reported = reported_checks(run)
        missing = [c for c in checks if c not in reported]
        if not missing or time.monotonic() >= deadline:
            return missing
        if missing != last:
            print(f"  waiting for checks to report on {run.branch}: {' '.join(missing)}", flush=True)
            last = missing
        time.sleep(POLL_SECONDS)


def apply_ruleset(run, files_in_pr=False):
    print()
    if not run.checks:
        print("(ruleset skipped: pass --checks default or a list to create it)")
        return
    checks = (DEFAULT_CHECKS if run.checks == "default" else run.checks).split(",")
    reported = reported_checks(run)
    missing = [c for c in checks if c not in reported]
    if missing and files_in_pr:
        # The workflows are not on the default branch until the PR merges, so there is nothing to wait for
        print(f"! ruleset left as it is: {' '.join(missing)} will report once the PR merges. Run bootstrap again then.")
        return
    if missing and run.apply:
        # A required check that never reports blocks every PR, so wait for it
        missing = wait_for_checks(run, checks)
        if missing:
            print(f"! skipped the ruleset: not reported on {run.branch} after {WAIT_SECONDS // 60} minutes: {' '.join(missing)}")
            print(f"  Check the workflow runs (gh run list -R {run.repo}), then run bootstrap again; it picks up where it stopped.")
            run.failed += 1
            return
    elif missing:
        print(f"! {' '.join(missing)} not reported on {run.branch} yet (--apply waits up to {WAIT_SECONDS // 60} minutes for them)")
    with_codeowners = has_codeowners(run)
    if not with_codeowners:
        print("! no CODEOWNERS: the ruleset will not require code-owner review")
    body = build(run, checks, with_codeowners)
    existing = next((r["id"] for r in api_get(f"repos/{run.repo}/rulesets") or [] if r["name"] == NAME), None)
    method, endpoint = ("PUT", f"repos/{run.repo}/rulesets/{existing}") if existing else ("POST", f"repos/{run.repo}/rulesets")
    print(json.dumps(body, indent=2))
    run.do(f"{'update' if existing else 'create'} ruleset '{NAME}'  [{method} {endpoint}]", lambda: api_send(method, endpoint, body))
