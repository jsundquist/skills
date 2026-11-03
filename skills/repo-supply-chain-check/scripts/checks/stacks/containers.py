"""Container specifics: Dockerfile content, and the scan/sign/attest steps around the image build."""
import re

from lib import HARDENING, bad, check, ok, warn

DOCKERFILE = r"(^|/)Dockerfile"


def has_dockerfile(repo):
    return repo.has_file(DOCKERFILE)


@check(HARDENING, when=has_dockerfile)
def image_pipeline(repo):
    steps = [
        ("Trivy scan", r"trivy"),
        ("signing (cosign / sigstore)", r"cosign|sigstore"),
        ("attestations (provenance / SBOM)", r"actions/attest|attest-build-provenance|attest-sbom"),
        ("image push in CI", r"push: *true|docker/build-push-action"),
    ]
    return [ok(label) if repo.ci_has(p) else bad(f"{label} (not found)") for label, p in steps]


@check(HARDENING, when=has_dockerfile)
def dockerfiles(repo):
    out = []
    for path in repo.files(DOCKERFILE):
        body = repo.read(path)
        stages = set()
        for m in re.finditer(r"(?im)^FROM\s+(?:--\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", body):
            image, stage = m.group(1), m.group(2)
            if "@sha256:" in image:
                out.append(ok(f"{path}: base {image} pinned by digest"))
            elif image != "scratch" and image not in stages:
                out.append(warn(f"{path}: base image not pinned by digest: {image}"))
            if stage:
                stages.add(stage)
        users = re.findall(r"(?im)^USER\s+(\S+)", body)
        if users and users[-1] not in ("root", "0"):
            out.append(ok(f"{path}: runs as non-root USER"))
        else:
            out.append(warn(f"{path}: no non-root USER (fine if the base image already runs non-root; confirm with docker inspect)"))
        if "org.opencontainers.image.source" in body:
            out.append(ok(f"{path}: image.source label"))
        else:
            out.append(warn(f"{path}: no org.opencontainers.image.source label"))
        if re.search(r"apt-get (upgrade|dist-upgrade)|apk upgrade", body):
            out.append(warn(f"{path}: OS upgrade at build time (makes the digest-pinned base non-reproducible)"))
    return out
