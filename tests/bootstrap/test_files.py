import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import FakeApi, make_run, quiet
from steps import files

SHA = "f" * 40


class RenderTest(unittest.TestCase):
    def render(self, text, **run_overrides):
        run = make_run(**run_overrides)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(files, "resolve_sha", return_value=SHA):
            template = Path(tmp) / "t.yml"
            template.write_text(text, encoding="utf-8")
            return files.render(run, template)

    def test_pin_becomes_a_full_sha_with_a_version_comment(self):
        out = self.render("uses: {{pin:actions/checkout}}\n")
        self.assertEqual(out, f"uses: actions/checkout@{SHA} # {files.PINS['actions/checkout']}\n")

    def test_pin_keeps_the_path_after_the_repo(self):
        out = self.render("uses: {{pin:github/codeql-action/upload-sarif}}\n")
        self.assertTrue(out.startswith(f"uses: github/codeql-action/upload-sarif@{SHA} # "))

    def test_plain_placeholders_are_filled_in(self):
        out = self.render("{{repo}} {{branch}} {{codeowner}} {{publish}}")
        self.assertEqual(out, "o/r main @o true\n".strip())

    def test_publish_is_false_for_a_private_repo(self):
        run_text = "{{publish}}"
        run = make_run()
        run.info["visibility"] = "private"
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "t"
            template.write_text(run_text, encoding="utf-8")
            self.assertEqual(files.render(run, template), "false")

    def test_github_expressions_are_left_alone(self):
        text = "group: ${{ github.ref }} ${{ secrets.X }}\n"
        self.assertEqual(self.render(text), text)

    def test_an_unpinned_action_is_an_error(self):
        with self.assertRaises(ValueError):
            self.render("{{pin:someone/unknown-action}}")

    def test_every_shipped_template_renders_with_no_placeholder_left(self):
        for template in sorted(files.TEMPLATES.rglob("*")):
            if not template.is_file():
                continue
            with self.subTest(template=str(template.relative_to(files.TEMPLATES))), mock.patch.object(files, "resolve_sha", return_value=SHA):
                out = files.render(make_run(), template)
                self.assertNotRegex(out, files.PLACEHOLDER)


class PutTest(unittest.TestCase):
    def files_for(self, run, protected, api):
        with mock.patch.object(files, "branch_is_protected", return_value=protected), \
                mock.patch.object(files, "api_get", api.api_get), mock.patch.object(files, "api_send", api.api_send):
            return files.Files(run)

    def put(self, run, protected, api, path="SECURITY.md"):
        f = self.files_for(run, protected, api)
        with quiet(), mock.patch.object(files, "api_get", api.api_get), mock.patch.object(files, "api_send", api.api_send):
            f.put(path, "body\n")
        return f

    def test_dry_run_writes_nothing(self):
        api = FakeApi()
        run = make_run()
        run.apply = False
        self.put(run, False, api)
        self.assertEqual(api.sent, [])

    def test_existing_file_is_left_alone(self):
        api = FakeApi(get={"contents/SECURITY.md": {"type": "file"}})
        self.put(make_run(), False, api)
        self.assertEqual(api.sent, [])

    def test_unprotected_branch_gets_a_direct_commit(self):
        api = FakeApi()
        f = self.put(make_run(), False, api)
        method, endpoint, body = api.sent[0]
        self.assertEqual((method, endpoint, body["branch"]), ("PUT", "repos/o/r/contents/SECURITY.md", "main"))
        self.assertEqual(f.added, 1)

    def test_protected_branch_creates_a_work_branch_first_and_commits_there(self):
        api = FakeApi(get={"git/ref/heads/main": {"object": {"sha": "abc"}}})
        self.put(make_run(), True, api)
        self.assertEqual(api.sent[0][:2], ("POST", "repos/o/r/git/refs"))
        self.assertEqual(api.sent[0][2]["ref"], f"refs/heads/{files.WORK_BRANCH}")
        self.assertEqual(api.sent[1][2]["branch"], files.WORK_BRANCH)

    def test_a_failed_commit_is_counted(self):
        run = make_run()
        api = FakeApi(send_ok=False)
        self.put(run, False, api)
        self.assertEqual(run.failed, 1)

    def test_codeowners_is_skipped_without_a_code_owner(self):
        run = make_run()
        run.codeowner = ""
        api = FakeApi()
        f = self.files_for(run, False, api)
        with quiet() as out, mock.patch.object(files, "resolve_sha", return_value=SHA), \
                mock.patch.object(files, "api_get", api.api_get), mock.patch.object(files, "api_send", api.api_send):
            files.scaffold(run, f, files.TEMPLATES / "default")
        self.assertIn("skipping .github/CODEOWNERS", out.getvalue())
        self.assertNotIn(".github/CODEOWNERS", [e[1].split("contents/")[-1] for e in api.sent])


if __name__ == "__main__":
    unittest.main()
