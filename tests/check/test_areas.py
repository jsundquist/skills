import unittest

from checks import dependencies, golden_path
from helpers import FakeRepo, messages

ACTIONS_ONLY = """\
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    cooldown:
      default-days: 7
  - package-ecosystem: "npm"
    directory: /
"""

RULES = [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {"required_approving_review_count": 1}},
    {"type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": True, "required_status_checks": [{"context": "zizmor"}]}},
]


class DependabotTest(unittest.TestCase):
    def test_cooldown_is_read_per_ecosystem(self):
        repo = FakeRepo({".github/dependabot.yml": ACTIONS_ONLY})
        self.assertEqual(dependencies.dependabot_ecosystems(repo), {"github-actions": True, "npm": False})

    def test_no_config_is_a_gap_unless_renovate_is_used(self):
        self.assertEqual(dependencies.update_automation(FakeRepo()).status, "bad")
        self.assertEqual(dependencies.update_automation(FakeRepo({"renovate.json": "{}"})).status, "ok")

    def test_ecosystem_without_cooldown_is_a_gap_and_uncovered_stack_is_a_warning(self):
        repo = FakeRepo({".github/dependabot.yml": ACTIONS_ONLY, "pyproject.toml": "[project]\n"})
        out = dependencies.update_automation(repo)
        self.assertIn("no cooldown on: npm", messages(out, "bad"))
        self.assertTrue(any("python" in m for m in messages(out, "warn")))


class LockfileTest(unittest.TestCase):
    def test_missing_lock_is_a_gap_for_node_and_a_warning_for_python(self):
        out = dependencies.lockfiles(FakeRepo({"package.json": "{}", "pyproject.toml": ""}))
        self.assertEqual(messages(out, "bad"), ["node: no lock file committed"])
        self.assertEqual(messages(out, "warn"), ["python: no lock file committed"])

    def test_present_locks_are_ok(self):
        out = dependencies.lockfiles(FakeRepo({"package.json": "", "pnpm-lock.yaml": "", "pyproject.toml": "", "uv.lock": ""}))
        self.assertEqual(messages(out, "ok"), ["node: lock file committed", "python: lock file committed"])


class BranchProtectionTest(unittest.TestCase):
    def protection(self, **api_data):
        return golden_path.default_branch_protection(FakeRepo(api_data=api_data))

    def test_no_protection_at_all_is_one_gap(self):
        self.assertEqual(messages(self.protection(), "bad"), ["no active ruleset and no branch protection on main"])

    def test_full_ruleset_passes_every_verdict(self):
        out = self.protection(rulesets=[{"id": 1, "target": "branch", "enforcement": "active"}],
                              **{"rulesets/1": {"name": "r", "rules": RULES, "bypass_actors": []}})
        self.assertEqual(messages(out, "bad"), [])
        self.assertIn("main requires 1 status check(s)", messages(out, "ok"))

    def test_ruleset_without_a_pull_request_rule_is_flagged(self):
        rules = [r for r in RULES if r["type"] != "pull_request"]
        out = self.protection(rulesets=[{"id": 1, "target": "branch", "enforcement": "active"}],
                              **{"rulesets/1": {"name": "r", "rules": rules, "bypass_actors": []}})
        self.assertEqual(messages(out, "bad"), ["main does not require a pull request"])

    def test_disabled_rulesets_do_not_count(self):
        out = self.protection(rulesets=[{"id": 1, "target": "branch", "enforcement": "disabled"}])
        self.assertTrue(messages(out, "bad")[0].startswith("no active ruleset"))

    def test_classic_protection_is_understood(self):
        classic = {"required_pull_request_reviews": {"required_approving_review_count": 1}, "allow_force_pushes": {"enabled": False},
                   "allow_deletions": {"enabled": False}, "required_status_checks": {"checks": [{"context": "a"}]}}
        out = self.protection(**{"branches/main/protection": classic})
        self.assertEqual(messages(out, "bad"), [])


class RepoSettingsTest(unittest.TestCase):
    GOOD = {
        "actions/permissions": {"sha_pinning_required": True},
        "actions/permissions/workflow": {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False},
        "private-vulnerability-reporting": {"enabled": True},
        "vulnerability-alerts": {},
        "code-scanning/default-setup": {"state": "configured", "languages": ["python"]},
    }
    INFO = {"security_and_analysis": {
        "secret_scanning": {"status": "enabled"}, "secret_scanning_push_protection": {"status": "enabled"},
        "dependabot_security_updates": {"status": "enabled"}}}

    def test_everything_on_has_no_gaps(self):
        out = golden_path.repo_settings(FakeRepo(api_data=self.GOOD, info=self.INFO))
        self.assertEqual(messages(out, "bad"), [])

    def test_unpinned_actions_setting_is_a_gap(self):
        data = {**self.GOOD, "actions/permissions": {"sha_pinning_required": False}}
        out = golden_path.repo_settings(FakeRepo(api_data=data, info=self.INFO))
        self.assertEqual(len(messages(out, "bad")), 1)
        self.assertIn("pinned to a full SHA", messages(out, "bad")[0])


if __name__ == "__main__":
    unittest.main()
