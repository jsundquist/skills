# Stack-specific supply-chain items

The generic checklist is in `checklist.md`. Read only the section for a stack the repo actually uses (`audit.py` detects them from the files in the repo). `R` is `OWNER/REPO`. Add a section here, and a `Stack` entry in `scripts/checks/stacks/__init__.py`, to support another ecosystem.

## Node (npm, pnpm, yarn)

Every Node package manager runs a package's install scripts and accepts a brand-new release by default. Each spells the controls differently. Set them in the repo root.

- [ ] Lockfile committed and installed in CI in a way that fails when it is out of date: `npm ci`, `pnpm install --frozen-lockfile`, `yarn install --immutable`
- [ ] Vulnerability audit in CI: `pnpm audit`, `npm audit`, `yarn npm audit`, or `osv-scanner`

| | Release-age cooldown | Install scripts |
|---|---|---|
| **pnpm** | `minimumReleaseAge` in `pnpm-workspace.yaml` (minutes) | `allowBuilds` (or `onlyBuiltDependencies`) lists the only packages allowed to run them |
| **npm** | `min-release-age=7` in `.npmrc` (days; needs npm 11.10+, off by default) | `ignore-scripts=true` in `.npmrc` |
| **yarn 4** | `npmMinimalAgeGate: 7d` in `.yarnrc.yml` (needs Yarn 4.10+) | `enableScripts: false` in `.yarnrc.yml` |
| **yarn 1** | none; move to Yarn 4 or another manager | `ignore-scripts true` in `.yarnrc` |

Units differ: npm counts days, pnpm counts minutes. The cooldown is not a complete defence; a compromised release that stays published for longer than the cooldown still gets through.

Audited by `scripts/checks/stacks/node.py`. The audit also flags `npm install` (instead of `npm ci`) in workflows and Dockerfiles.

## Python (uv, pip)

- [ ] **uv:** `uv.lock` committed; CI and Dockerfiles use `uv sync --frozen` (or `--locked`) so the lock cannot change during a build
- [ ] **uv:** `exclude-newer` under `[tool.uv]` in `pyproject.toml` (or `uv.toml`), a rolling cutoff such as `"7 days"` (an older uv may only accept a fixed timestamp)
- [ ] **pip:** requirements files carry hashes (`pip-compile --generate-hashes` or `uv pip compile --generate-hashes`) and install with `pip install --require-hashes`
- [ ] Vulnerability audit in CI: `pip-audit` or `osv-scanner`

Audited by `scripts/checks/stacks/python.py`.

## Containers (Docker)

- [ ] Multi-stage build; base image pinned by digest
- [ ] Runs as a non-root `USER` (or the base image already does)
- [ ] No OS upgrade at build time (`apt-get upgrade`, `apk upgrade`): it defeats the digest pin
- [ ] `org.opencontainers.image.source` label, so GHCR links the package to the repo
- [ ] Trivy gate on HIGH and CRITICAL fixable findings, scanning the image that will be pushed
- [ ] Push by digest and record the digest as a job output
- [ ] Sign by digest with cosign keyless; signing in its own job
- [ ] Provenance and SBOM attached as attestations; verify before deploy
- [ ] Registry (GHCR): package linked to the repo, visibility chosen, old untagged versions pruned (keep what signatures reference), deployments reference the digest

Audited by `scripts/checks/stacks/containers.py` and `scripts/checks/repositories.py`.

```bash
# Does the image carry provenance and an SBOM attestation? (prints nothing off a terminal; read the exit code)
gh attestation verify oci://ghcr.io/OWNER/IMAGE@sha256:DIGEST --owner OWNER --predicate-type https://slsa.dev/provenance/v1
gh attestation verify oci://ghcr.io/OWNER/IMAGE@sha256:DIGEST --owner OWNER --predicate-type https://cyclonedx.org/bom

cosign verify ghcr.io/OWNER/IMAGE@sha256:DIGEST \
  --certificate-identity 'https://github.com/OWNER/REPO/.github/workflows/release.yml@refs/heads/main' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com

# Digest of a tag, and of a base image
docker buildx imagetools inspect ghcr.io/OWNER/IMAGE:TAG
docker buildx imagetools inspect nginxinc/nginx-unprivileged:1.30-alpine-slim

# GHCR packages (needs: gh auth refresh -s read:packages)
gh api 'users/OWNER/packages?package_type=container' --jq '.[] | [.name, .visibility, .repository.full_name] | @tsv'
gh api 'users/OWNER/packages/container/IMAGE/versions?per_page=100' \
  --jq '.[] | [.id, .created_at[:10], (.metadata.container.tags | join(","))] | @tsv'
# Package visibility and "manage Actions access" are only in the web UI:
#   https://github.com/users/OWNER/packages/container/IMAGE/settings
```

## Kubernetes and GitOps (Argo CD)

- [ ] The cluster enforces what CI promises: Pod Security Admission, an image-digest check, a signature check
- [ ] Deploy only through git and Argo CD, with no manual `kubectl apply`
- [ ] Manifests reference images by digest, not `latest` or a moving tag

## GitHub Actions and libraries you publish

```bash
SHA=$(git rev-parse HEAD)                    # a commit on main that is already green
gh release create v1.0.0 -R R --target "$SHA" --title v1.0.0 --notes "what changed"
# Moving major tag (v1) for consumers who want automatic patches; consumers still pin the commit SHA
gh api -X POST repos/R/git/refs -f ref=refs/tags/v1 -f sha="$SHA"                    # first time
gh api -X PATCH repos/R/git/refs/tags/v1 -f sha="$SHA" -F force=true                 # later moves
gh release list -R R
```
