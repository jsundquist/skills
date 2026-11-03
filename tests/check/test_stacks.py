import unittest

from checks.stacks import containers, detected, node, python
from helpers import FakeRepo, messages

WF = ".github/workflows/ci.yml"


class DetectionTest(unittest.TestCase):
    def test_stacks_are_found_from_file_names(self):
        repo = FakeRepo({"package.json": "{}", "app/Dockerfile": "FROM x", WF: "jobs: {}", "README.md": ""})
        self.assertEqual([s.name for s in detected(repo)], ["node", "containers", "github-actions"])

    def test_an_empty_repo_has_no_stacks(self):
        self.assertEqual(detected(FakeRepo({"README.md": ""})), [])


class NpmTest(unittest.TestCase):
    def test_bare_npm_project_gets_three_warnings(self):
        repo = FakeRepo({"package-lock.json": "{}", WF: "steps:\n  - run: npm install\n"})
        out = node.npm_hardening(repo)
        self.assertEqual([r.status for r in out], ["warn", "warn", "warn"])
        self.assertEqual(out[2].detail, ("- run: npm install",))

    def test_configured_npm_project_is_clean(self):
        repo = FakeRepo({"package-lock.json": "{}", ".npmrc": "min-release-age=7\nignore-scripts=true\n",
                         WF: "steps:\n  - run: npm ci\n"})
        self.assertEqual([r.status for r in node.npm_hardening(repo)], ["ok", "ok", "ok"])

    def test_global_installs_are_not_flagged(self):
        repo = FakeRepo({"package-lock.json": "{}", "Dockerfile": "RUN npm install -g pnpm\n"})
        self.assertNotIn("warn", [r.status for r in node.npm_hardening(repo)][2:])


class YarnTest(unittest.TestCase):
    def test_yarn_berry_settings(self):
        good = FakeRepo({"yarn.lock": "", ".yarnrc.yml": "npmMinimalAgeGate: 7d\nenableScripts: false\n"})
        bare = FakeRepo({"yarn.lock": "", ".yarnrc.yml": "nodeLinker: node-modules\n"})
        self.assertEqual([r.status for r in node.yarn_hardening(good)], ["ok", "ok"])
        self.assertEqual([r.status for r in node.yarn_hardening(bare)], ["warn", "warn"])

    def test_yarn_classic_has_no_release_age_setting(self):
        out = node.yarn_hardening(FakeRepo({"yarn.lock": ""}))
        self.assertIn("no release-age", out[0].message)


class PnpmTest(unittest.TestCase):
    def test_missing_cooldown_is_a_gap(self):
        out = node.pnpm_hardening(FakeRepo({"pnpm-lock.yaml": "", "pnpm-workspace.yaml": "allowBuilds: {}\n"}))
        self.assertEqual([r.status for r in out], ["bad", "ok"])

    def test_configured_pnpm_is_clean(self):
        out = node.pnpm_hardening(FakeRepo({"pnpm-lock.yaml": "", "pnpm-workspace.yaml": "minimumReleaseAge: 10080\nallowBuilds: {}\n"}))
        self.assertEqual([r.status for r in out], ["ok", "ok"])


class PythonTest(unittest.TestCase):
    def test_uv_without_cutoff_or_locked_installs_warns(self):
        repo = FakeRepo({"uv.lock": "", "pyproject.toml": "[project]\n", WF: "steps:\n  - run: uv sync\n"})
        self.assertEqual([r.status for r in python.uv_hardening(repo)], ["warn", "warn"])

    def test_hardened_uv_is_clean(self):
        repo = FakeRepo({"uv.lock": "", "pyproject.toml": '[tool.uv]\nexclude-newer = "7 days"\n',
                         WF: "steps:\n  - run: uv sync --frozen\n"})
        self.assertEqual([r.status for r in python.uv_hardening(repo)], ["ok", "ok"])

    def test_pip_requirements_need_hashes_unless_uv_is_used(self):
        self.assertEqual(python.pip_hashes(FakeRepo({"requirements.txt": "flask==3\n"})).status, "warn")
        self.assertEqual(python.pip_hashes(FakeRepo({"requirements.txt": "flask==3 \\\n --hash=sha256:ab\n"})).status, "ok")
        self.assertFalse(python.uses_pip_requirements(FakeRepo({"requirements.txt": "", "uv.lock": ""})))


class DockerfileTest(unittest.TestCase):
    DOCKERFILE = (
        "FROM node:22@sha256:abc AS build\n"
        "FROM build AS test\n"
        "FROM --platform=$BUILDPLATFORM golang:1.22 AS compile\n"
        "FROM nginx:1.27\n"
        "LABEL org.opencontainers.image.source=https://example\n"
        "USER 101\n"
    )

    def test_digest_stage_alias_platform_flag_and_user(self):
        out = containers.dockerfiles(FakeRepo({"Dockerfile": self.DOCKERFILE}))
        self.assertIn("Dockerfile: base node:22@sha256:abc pinned by digest", messages(out, "ok"))
        warned = messages(out, "warn")
        self.assertIn("Dockerfile: base image not pinned by digest: golang:1.22", warned)
        self.assertIn("Dockerfile: base image not pinned by digest: nginx:1.27", warned)
        self.assertNotIn("Dockerfile: base image not pinned by digest: build", warned)
        self.assertIn("Dockerfile: runs as non-root USER", messages(out, "ok"))

    def test_final_user_root_is_flagged(self):
        out = containers.dockerfiles(FakeRepo({"Dockerfile": "FROM x@sha256:1\nUSER app\nUSER root\n"}))
        self.assertTrue(any("no non-root USER" in m for m in messages(out, "warn")))

    def test_os_upgrade_is_flagged(self):
        out = containers.dockerfiles(FakeRepo({"Dockerfile": "FROM x@sha256:1\nRUN apt-get upgrade -y\n"}))
        self.assertTrue(any("OS upgrade" in m for m in messages(out, "warn")))


if __name__ == "__main__":
    unittest.main()
