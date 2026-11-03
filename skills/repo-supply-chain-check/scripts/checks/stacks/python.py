"""Python specifics: uv's release cutoff and locked installs, and hash-pinned requirements for pip."""
import re

from lib import DEPENDENCIES, check, ok, warn


def uses_uv(repo):
    return repo.has_file(r"(^|/)uv\.lock$")


def uses_pip_requirements(repo):
    return repo.has_file(r"(^|/)requirements.*\.txt$") and not uses_uv(repo)


@check(DEPENDENCIES, when=uses_uv)
def uv_hardening(repo):
    config = repo.read("pyproject.toml") + "\n" + repo.read("uv.toml")
    out = [
        ok("uv: exclude-newer set") if re.search(r"^\s*exclude-newer\s*=", config, re.M)
        else warn("uv: exclude-newer not set in pyproject.toml or uv.toml (a rolling cutoff such as \"7 days\" needs a recent uv)"),
    ]
    unlocked = repo.build_commands(r"\buv sync\b", unless=r"--frozen|--locked")
    if unlocked:
        out.append(warn("uv: `uv sync` without --frozen or --locked can change the lock in CI", *unlocked[:5]))
    elif repo.build_lines:
        out.append(ok("uv: installs in CI and Dockerfiles use --frozen or --locked"))
    return out


@check(DEPENDENCIES, when=uses_pip_requirements)
def pip_hashes(repo):
    unhashed = [p for p in repo.files(r"(^|/)requirements.*\.txt$") if "--hash=" not in repo.read(p)]
    if unhashed:
        return warn("pip: requirements without hashes (pip-compile --generate-hashes, then pip install --require-hashes)", *unhashed)
    return ok("pip: requirements files carry hashes")
