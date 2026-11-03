"""Golden path: the controls GitHub itself enforces, so security is automatic rather than optional."""
from lib import GOLDEN_PATH, bad, check, info, ok, warn


@check(GOLDEN_PATH)
def repo_settings(repo):
    sa = repo.security_and_analysis
    perm = repo.api("actions/permissions") or {}
    token = repo.api("actions/permissions/workflow") or {}
    pvr = repo.api("private-vulnerability-reporting") or {}

    def enabled(key):
        return (sa.get(key) or {}).get("status") == "enabled"

    settings = [
        ("secret scanning", enabled("secret_scanning")),
        ("push protection", enabled("secret_scanning_push_protection")),
        ("Dependabot security updates", enabled("dependabot_security_updates")),
        ("Dependabot alerts", repo.api_ok("vulnerability-alerts")),
        ("Actions require actions pinned to a full SHA", perm.get("sha_pinning_required") is True),
        ("default GITHUB_TOKEN is read-only", token.get("default_workflow_permissions") == "read"),
        ("Actions cannot approve PRs", token.get("can_approve_pull_request_reviews") is False),
        ("private vulnerability reporting", pvr.get("enabled") is True),
    ]
    out = [info(f"visibility: {repo.info.get('visibility', 'unknown')}")]
    out += [ok(label) if value else bad(f"{label} (off, or not readable with this token)") for label, value in settings]

    codeql = repo.api("code-scanning/default-setup") or {}
    languages = ", ".join(codeql.get("languages") or [])
    if codeql.get("state") != "configured":
        out.append(bad(f"CodeQL default setup: {codeql.get('state', 'unknown')}"))
    elif languages:
        out.append(ok(f"CodeQL default setup: {languages}"))
    else:
        out.append(warn("CodeQL default setup is on but covers no languages yet (nothing is scanned until the repo has supported code)"))
    return out


@check(GOLDEN_PATH)
def default_branch_protection(repo):
    summaries = repo.api("rulesets") or []
    rulesets = [repo.api(f"rulesets/{r['id']}") or {} for r in summaries
                if r.get("target") == "branch" and r.get("enforcement") == "active"]
    classic = repo.api(f"branches/{repo.branch}/protection")
    if not rulesets and not classic:
        return bad(f"no active ruleset and no branch protection on {repo.branch}")

    out = []
    rule_types = set()   # what the branch enforces, from rulesets and classic protection together
    required_checks = 0
    for rs in rulesets:
        rules = rs.get("rules", [])
        rule_types |= {r["type"] for r in rules}
        detail = [f"rules: {', '.join(r['type'] for r in rules)}"]
        for r in rules:
            params = r.get("parameters") or {}
            if r["type"] == "required_status_checks":
                contexts = [c["context"] for c in params.get("required_status_checks", [])]
                required_checks += len(contexts)
                detail.append(f"required checks: {', '.join(contexts)}  strict: {params.get('strict_required_status_checks_policy')}")
            if r["type"] == "pull_request":
                detail.append(f"required approvals: {params.get('required_approving_review_count')}")
        out.append(info(f"ruleset {rs.get('name')} (bypass actors: {len(rs.get('bypass_actors', []))})", *detail))
    if classic:
        checks = (classic.get("required_status_checks") or {}).get("checks") or []
        required_checks += len(checks)
        if classic.get("required_pull_request_reviews"):
            rule_types.add("pull_request")
        if not (classic.get("allow_force_pushes") or {}).get("enabled"):
            rule_types.add("non_fast_forward")
        if not (classic.get("allow_deletions") or {}).get("enabled"):
            rule_types.add("deletion")
        out.append(info("classic branch protection", f"enforce_admins: {(classic.get('enforce_admins') or {}).get('enabled')}"))

    b = repo.branch
    out.append(ok(f"{b} requires a pull request") if "pull_request" in rule_types else bad(f"{b} does not require a pull request"))
    out.append(ok(f"{b} blocks force-push") if "non_fast_forward" in rule_types else bad(f"{b} allows force-push"))
    out.append(ok(f"{b} blocks deletion") if "deletion" in rule_types else bad(f"{b} can be deleted"))
    out.append(ok(f"{b} requires {required_checks} status check(s)") if required_checks else bad(f"{b} requires no status checks"))
    return out


@check(GOLDEN_PATH)
def policy_files(repo):
    out = []
    out.append(ok("SECURITY.md") if repo.has_file(r"^(\.github/|docs/)?SECURITY\.md$") else bad("SECURITY.md"))
    out.append(ok("LICENSE") if repo.has_file(r"^LICENSE") else warn("no LICENSE"))
    out.append(ok("CODEOWNERS") if repo.has_file(r"(^|/)CODEOWNERS$") else info("no CODEOWNERS (fine for a solo repo)"))
    hooks = repo.has_file(r"(^|/)(lefthook|\.pre-commit-config)\.ya?ml$|^\.husky/")
    out.append(ok("pre-commit hooks present") if hooks else warn("no pre-commit hooks (bootstrap --lefthook adds a lefthook.yml)"))
    return out


@check(GOLDEN_PATH)
def open_alerts(repo):
    out = []
    for label, path in (("code scanning", "code-scanning/alerts"), ("secret scanning", "secret-scanning/alerts")):
        alerts = repo.api(f"{path}?state=open&per_page=100")
        if alerts is None:
            out.append(warn(f"{label} alerts: unknown (disabled, or no analysis yet)"))
        elif alerts:
            out.append(warn(f"{label} alerts open: {len(alerts)}"))
        else:
            out.append(ok(f"{label} alerts: 0"))
    return out


@check(GOLDEN_PATH)
def activity(repo):
    """Context only: releases, secret names (never values), and recent failures."""
    out = []
    releases = [r["tag_name"] for r in repo.api("releases?per_page=3") or []]
    out.append(info(f"releases: {', '.join(releases)}") if releases else info("no GitHub releases"))
    secrets = (repo.api("actions/secrets") or {}).get("secrets", [])
    if secrets:
        out.append(info("Actions secrets (names only)", *[f"{s['name']} (updated {s['updated_at'][:10]})" for s in secrets]))
    runs = (repo.api(f"actions/runs?branch={repo.branch}&per_page=10") or {}).get("workflow_runs", [])
    failed = sum(1 for r in runs if r.get("conclusion") == "failure")
    out.append(info(f"failed runs among the last {len(runs)} on {repo.branch}: {failed}"))
    return out
