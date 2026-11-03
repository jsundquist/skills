"""SBOM: an inventory of the components in what you build."""
from lib import SBOM, bad, check, ok

from checks.stacks import detected

SBOM_TOOLS = r"sbom|cyclonedx|syft|cdxgen|dependency-snapshot|spdx"


@check(SBOM, when=lambda repo: any(s.name != "github-actions" for s in detected(repo)))
def sbom_generation(repo):
    return ok("SBOM generation") if repo.ci_has(SBOM_TOOLS) else bad("SBOM generation (not found)")
