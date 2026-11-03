"""Artifact repositories: where built artifacts are published, and who can see them.
Today this covers container images on GHCR; other registries would be added here."""
from lib import REPOSITORIES, api, check, info, ok, warn

from checks.stacks.containers import has_dockerfile


@check(REPOSITORIES, when=has_dockerfile)
def ghcr_packages(repo):
    kind = "orgs" if repo.info.get("owner", {}).get("type") == "Organization" else "users"
    packages = api(f"{kind}/{repo.owner}/packages?package_type=container&per_page=100")
    if packages is None:
        return info("could not list GHCR packages (needs: gh auth refresh -s read:packages)")
    mine = [p for p in packages if (p.get("repository") or {}).get("full_name") == repo.name]
    if not mine:
        return warn("a Dockerfile exists but no GHCR package is linked to this repo")
    out = [ok("images are published to GHCR", *[f"{p['name']}  {p['visibility']}" for p in mine])]
    if any(p["visibility"] == "public" for p in mine):
        out.append(warn("a package is public: confirm that is intended"))
    return out
