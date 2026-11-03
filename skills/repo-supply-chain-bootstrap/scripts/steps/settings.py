"""Repository settings. Each row is one API call: add a row to turn on another setting."""
from lib import api_send

# (what it does, HTTP method, path under repos/OWNER/REPO, JSON body)
SETTINGS = [
    ("secret scanning, push protection, Dependabot security updates", "PATCH", "", {"security_and_analysis": {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
        "dependabot_security_updates": {"status": "enabled"}}}),
    ("Dependabot alerts", "PUT", "vulnerability-alerts", None),
    ("read-only GITHUB_TOKEN, Actions cannot approve PRs", "PUT", "actions/permissions/workflow", {
        "default_workflow_permissions": "read", "can_approve_pull_request_reviews": False}),
    ("require actions pinned to a full SHA", "PUT", "actions/permissions", {
        "enabled": True, "allowed_actions": "all", "sha_pinning_required": True}),
    ("private vulnerability reporting (pairs with SECURITY.md)", "PUT", "private-vulnerability-reporting", None),
    # Accepted on an empty repo, but scans nothing until there is code in a supported language
    ("CodeQL default setup", "PATCH", "code-scanning/default-setup", {"state": "configured", "query_suite": "default"}),
    ("delete branches on merge", "PATCH", "", {"delete_branch_on_merge": True}),
]


def apply_settings(run):
    for label, method, path, body in SETTINGS:
        endpoint = f"repos/{run.repo}/{path}".rstrip("/")
        run.do(f"{label}  [{method} {endpoint}]", lambda m=method, e=endpoint, b=body: api_send(m, e, b))
