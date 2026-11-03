import unittest
from unittest import mock

from helpers import FakeApi, make_run, quiet
from steps import ruleset


class BuildTest(unittest.TestCase):
    def test_body_has_the_four_rules_and_the_requested_checks(self):
        body = ruleset.build(make_run(), ["a", "b"], True)
        self.assertEqual([r["type"] for r in body["rules"]], ["deletion", "non_fast_forward", "pull_request", "required_status_checks"])
        checks = body["rules"][3]["parameters"]
        self.assertEqual([c["context"] for c in checks["required_status_checks"]], ["a", "b"])
        self.assertTrue(checks["strict_required_status_checks_policy"])

    def test_code_owner_review_follows_whether_a_codeowners_file_exists(self):
        self.assertTrue(ruleset.build(make_run(), ["a"], True)["rules"][2]["parameters"]["require_code_owner_review"])
        self.assertFalse(ruleset.build(make_run(), ["a"], False)["rules"][2]["parameters"]["require_code_owner_review"])

    def test_admin_may_bypass_for_pull_requests_only(self):
        self.assertEqual(ruleset.build(make_run(), ["a"], True)["bypass_actors"],
                         [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}])


class WaitTest(unittest.TestCase):
    def test_waits_until_every_check_has_reported(self):
        seen = [set(), {"a"}, {"a", "b"}]
        with mock.patch.object(ruleset, "reported_checks", side_effect=seen), mock.patch.object(ruleset.time, "sleep") as sleep, \
                mock.patch.object(ruleset, "WAIT_SECONDS", 1000), quiet():
            self.assertEqual(ruleset.wait_for_checks(make_run(), ["a", "b"]), [])
        self.assertEqual(sleep.call_count, 2)

    def test_gives_up_after_the_deadline_and_returns_what_is_missing(self):
        with mock.patch.object(ruleset, "reported_checks", return_value={"a"}), mock.patch.object(ruleset, "WAIT_SECONDS", 0), quiet():
            self.assertEqual(ruleset.wait_for_checks(make_run(), ["a", "b"]), ["b"])

    def test_makes_one_api_call_per_poll_not_one_per_check(self):
        with mock.patch.object(ruleset, "reported_checks", return_value={"a", "b", "c"}) as polls, quiet():
            ruleset.wait_for_checks(make_run(), ["a", "b", "c"])
        self.assertEqual(polls.call_count, 1)


class ApplyRulesetTest(unittest.TestCase):
    def apply(self, run, reported, api=None, files_in_pr=False, wait=None):
        api = api or FakeApi(get={"rulesets": [], "CODEOWNERS": {"type": "file"}})
        patches = [mock.patch.object(ruleset, "reported_checks", return_value=set(reported)),
                   mock.patch.object(ruleset, "api_get", api.api_get), mock.patch.object(ruleset, "api_send", api.api_send)]
        if wait is not None:
            patches.append(mock.patch.object(ruleset, "wait_for_checks", return_value=wait))
        with quiet() as out:
            for p in patches:
                p.start()
            try:
                ruleset.apply_ruleset(run, files_in_pr=files_in_pr)
            finally:
                mock.patch.stopall()
        return api, out.getvalue()

    def test_creates_the_ruleset_once_all_checks_have_reported(self):
        run = make_run(checks="default")
        api, _ = self.apply(run, ruleset.DEFAULT_CHECKS.split(","))
        self.assertEqual([(m, e) for m, e, _ in api.sent], [("POST", "repos/o/r/rulesets")])

    def test_updates_in_place_when_the_ruleset_already_exists(self):
        run = make_run(checks="default")
        api = FakeApi(get={"/rulesets": [{"id": 9, "name": ruleset.NAME}], "CODEOWNERS": {"type": "file"}})
        api, _ = self.apply(run, ruleset.DEFAULT_CHECKS.split(","), api)
        self.assertEqual([(m, e) for m, e, _ in api.sent], [("PUT", "repos/o/r/rulesets/9")])

    def test_timeout_skips_the_ruleset_and_counts_a_failure(self):
        run = make_run(checks="default")
        api, out = self.apply(run, [], wait=["gitleaks"])
        self.assertEqual(api.sent, [])
        self.assertEqual(run.failed, 1)
        self.assertIn("skipped the ruleset", out)

    def test_files_that_went_in_by_pr_leave_the_ruleset_alone_without_failing(self):
        run = make_run(checks="default")
        api, out = self.apply(run, [], files_in_pr=True)
        self.assertEqual(api.sent, [])
        self.assertEqual(run.failed, 0)
        self.assertIn("once the PR merges", out)

    def test_no_checks_means_no_ruleset(self):
        run = make_run(checks="")
        api, _ = self.apply(run, [])
        self.assertEqual(api.sent, [])

    def test_dry_run_with_unreported_checks_does_not_wait_or_send(self):
        run = make_run(checks="default")
        run.apply = False
        api, out = self.apply(run, [])
        self.assertEqual(api.sent, [])
        self.assertIn("not reported", out)


if __name__ == "__main__":
    unittest.main()
