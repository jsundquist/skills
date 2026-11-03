"""SLSA: provenance that says where and how an artifact was built."""

from lib import SLSA, bad, check, ok

from checks.stacks.containers import has_dockerfile

PUBLISHING = r"docker/build-push-action|npm publish|twine upload|pypi-publish|goreleaser|gh release create"


def ships_artifacts(repo):
    return has_dockerfile(repo) or repo.ci_has(PUBLISHING) or bool(repo.api("releases?per_page=1"))


@check(SLSA, when=ships_artifacts)
def provenance(repo):
    found = repo.ci_has(r"attest-build-provenance|actions/attest|slsa-github-generator")
    return ok("provenance attestation") if found else bad("provenance attestation (not found)")
