import argparse
import unittest
from unittest import mock

import bootstrap
from helpers import FakeApi, make_run, quiet
from steps import settings


class SettingsTest(unittest.TestCase):
    def apply(self, run, api):
        with quiet(), mock.patch.object(settings, "api_send", api.api_send):
            settings.apply_settings(run)

    def test_dry_run_changes_nothing(self):
        run = make_run()
        run.apply = False
        api = FakeApi()
        self.apply(run, api)
        self.assertEqual(api.sent, [])

    def test_apply_sends_every_row(self):
        api = FakeApi()
        self.apply(make_run(), api)
        self.assertEqual(len(api.sent), len(settings.SETTINGS))
        self.assertTrue(all(method in ("PUT", "PATCH") for method, _, _ in api.sent))

    def test_the_hardening_settings_ask_for_the_right_values(self):
        api = FakeApi()
        self.apply(make_run(), api)
        bodies = {endpoint: body for _, endpoint, body in api.sent if body}
        self.assertTrue(bodies["repos/o/r/actions/permissions"]["sha_pinning_required"])
        self.assertEqual(bodies["repos/o/r/actions/permissions/workflow"]["default_workflow_permissions"], "read")
        self.assertFalse(bodies["repos/o/r/actions/permissions/workflow"]["can_approve_pull_request_reviews"])

    def test_every_failed_call_is_counted(self):
        run = make_run()
        self.apply(run, FakeApi(send_ok=False))
        self.assertEqual(run.failed, len(settings.SETTINGS))


class BuildRunTest(unittest.TestCase):
    ARGS = dict(repo="o/r", apply=False, show=False, license_id="", codeowner="", scorecard=False, lefthook=False,
                scaffold=True, checks=None, no_ruleset=False)

    def build(self, owner_type="User", **overrides):
        args = argparse.Namespace(**{**self.ARGS, **overrides})
        info = {"default_branch": "main", "visibility": "public"}
        api = FakeApi(get={"users/o": {"type": owner_type}, "repos/o/r": info})
        with mock.patch.object(bootstrap, "api_get", api.api_get):
            return bootstrap.build_run(args)

    def test_ruleset_is_on_by_default(self):
        self.assertEqual(self.build().checks, "default")

    def test_no_scaffold_or_no_ruleset_skips_it(self):
        self.assertEqual(self.build(scaffold=False).checks, "")
        self.assertEqual(self.build(no_ruleset=True).checks, "")

    def test_explicit_checks_are_kept_even_without_scaffold(self):
        self.assertEqual(self.build(scaffold=False, checks="a,b").checks, "a,b")

    def test_personal_account_defaults_the_code_owner_to_the_owner(self):
        self.assertEqual(self.build().codeowner, "@o")

    def test_organization_has_no_default_code_owner(self):
        self.assertEqual(self.build(owner_type="Organization").codeowner, "")

    def test_code_owner_must_start_with_an_at_sign(self):
        with quiet(), self.assertRaises(SystemExit) as caught:
            self.build(codeowner="someone")
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
