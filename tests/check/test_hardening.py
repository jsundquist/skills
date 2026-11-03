import unittest

from checks.hardening import run_lines, workflow_hygiene, workflow_tooling
from helpers import FakeRepo, messages

SHA = "a" * 40

INJECTION = """\
steps:
  - run: echo "${{ github.event.pull_request.title }}"
  - name: block
    run: |
      echo one
      echo "${{ inputs.name }}"
    env:
      TITLE: ${{ github.event.pull_request.title }}
"""


class RunLinesTest(unittest.TestCase):
    def test_one_line_and_block_runs_are_returned(self):
        lines = [line.strip() for line in run_lines(INJECTION)]
        self.assertIn('echo "${{ github.event.pull_request.title }}"', lines)
        self.assertIn("echo one", lines)
        self.assertIn('echo "${{ inputs.name }}"', lines)

    def test_a_sibling_key_after_a_block_is_not_part_of_the_run(self):
        self.assertFalse(any("TITLE" in line for line in run_lines(INJECTION)))


class WorkflowHygieneTest(unittest.TestCase):
    def hygiene(self, text):
        return workflow_hygiene(FakeRepo({".github/workflows/a.yml": text}))

    def test_no_workflows_is_a_gap(self):
        self.assertEqual(messages(workflow_hygiene(FakeRepo()), "bad"), ["no workflows"])

    def test_clean_workflow_has_no_warnings(self):
        text = f"permissions: {{}}\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@{SHA} # v1\n      - uses: ./local\n"
        self.assertEqual(messages(self.hygiene(text), "warn"), [])

    def test_unpinned_action_is_reported_with_its_name(self):
        results = self.hygiene("permissions: {}\nsteps:\n  - uses: actions/checkout@v4\n")
        self.assertEqual(len([r for r in results if "not pinned" in r.message]), 1)
        self.assertIn("actions/checkout@v4", [r for r in results if "not pinned" in r.message][0].detail)

    def test_missing_permissions_block_is_reported(self):
        self.assertTrue(any("no permissions block" in m for m in messages(self.hygiene("jobs: {}\n"), "warn")))

    def test_expression_in_run_is_reported_but_the_same_in_env_is_not(self):
        flagged = any("injection" in m for m in messages(self.hygiene("permissions: {}\n" + INJECTION), "warn"))
        self.assertTrue(flagged)
        safe = "permissions: {}\nsteps:\n  - run: echo \"$T\"\n    env:\n      T: ${{ github.event.pull_request.title }}\n"
        self.assertFalse(any("injection" in m for m in messages(self.hygiene(safe), "warn")))


class WorkflowToolingTest(unittest.TestCase):
    def test_missing_tools_are_gaps_and_present_ones_are_ok(self):
        repo = FakeRepo({".github/workflows/a.yml": "steps:\n  - uses: zizmorcore/zizmor-action@x\n    with:\n      persist-credentials: false\n"})
        results = workflow_tooling(repo)
        self.assertIn("zizmor", messages(results, "ok"))
        self.assertIn("actionlint (not found)", messages(results, "bad"))


if __name__ == "__main__":
    unittest.main()
