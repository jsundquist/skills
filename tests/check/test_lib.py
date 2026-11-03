import unittest
from unittest import mock

import lib
from helpers import FakeRepo
from lib import Check, area_status, bad, info, ok, warn


class AreaStatusTest(unittest.TestCase):
    def test_a_gap_beats_everything(self):
        self.assertEqual(area_status([ok("a"), warn("b"), bad("c")]), "gap")

    def test_warning_without_gap_is_partial(self):
        self.assertEqual(area_status([ok("a"), warn("b")]), "partial")

    def test_only_ok_is_met(self):
        self.assertEqual(area_status([ok("a"), info("b")]), "met")

    def test_nothing_or_only_info_is_not_applicable(self):
        self.assertEqual(area_status([]), "n/a")
        self.assertEqual(area_status([info("a")]), "n/a")


class RunChecksTest(unittest.TestCase):
    def run_with(self, checks):
        with mock.patch.object(lib, "CHECKS", checks):
            return lib.run_checks(FakeRepo())

    def test_check_that_does_not_apply_leaves_its_area_empty(self):
        results = self.run_with([Check(lib.SBOM, lambda repo: ok("x"), when=lambda repo: False)])
        self.assertEqual(results[lib.SBOM], [])
        self.assertEqual(area_status(results[lib.SBOM]), "n/a")

    def test_a_check_may_return_one_result_or_a_list_or_nothing(self):
        results = self.run_with([
            Check(lib.SLSA, lambda repo: ok("one")),
            Check(lib.SLSA, lambda repo: [ok("two"), bad("three")]),
            Check(lib.SLSA, lambda repo: None),
        ])
        self.assertEqual([r.message for r in results[lib.SLSA]], ["one", "two", "three"])

    def test_a_crashing_check_becomes_a_warning_and_the_rest_still_run(self):
        def boom(repo):
            raise RuntimeError("nope")
        results = self.run_with([Check(lib.HARDENING, boom), Check(lib.HARDENING, lambda repo: ok("still ran"))])
        self.assertEqual([r.status for r in results[lib.HARDENING]], ["warn", "ok"])
        self.assertIn("nope", results[lib.HARDENING][0].message)


class RepoTextTest(unittest.TestCase):
    def test_a_tool_mentioned_only_in_a_comment_does_not_count(self):
        repo = FakeRepo({".github/workflows/a.yml": "# run zizmor here someday\njobs: {}\n"})
        self.assertFalse(repo.ci_has("zizmor"))

    def test_a_tool_used_in_a_step_counts(self):
        repo = FakeRepo({".github/workflows/a.yml": "steps:\n  - uses: zizmorcore/zizmor-action@abc\n"})
        self.assertTrue(repo.ci_has("zizmor"))

    def test_build_commands_cover_workflows_and_dockerfiles_and_skip_excluded_lines(self):
        repo = FakeRepo({
            ".github/workflows/a.yml": "steps:\n  - run: uv sync\n  - run: uv sync --frozen\n",
            "Dockerfile": "RUN uv sync --locked\n# RUN uv sync\n",
        })
        self.assertEqual(repo.build_commands(r"\buv sync\b", unless=r"--frozen|--locked"), ["- run: uv sync"])


if __name__ == "__main__":
    unittest.main()
