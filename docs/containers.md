# Stack: containers (GHCR)

Extra steps for a repository that publishes a **container image** to GitHub Container Registry. This is outside the language-independent [golden path](golden-path.md), the same way npm or pip specifics are. Do the golden path first. Come back here only if the repo ships an image.

Assumes the golden path through layer 5 is in place (protected tags, pinned actions, `GITHUB_TOKEN` publishing). Commands use the same `(repo)` placeholder and the [`gh` CLI](https://cli.github.com/). Where you deploy the image, such as a Kubernetes cluster, is out of scope.

Status: **draft**. Moved out of the golden path unchanged apart from renumbering. The release workflow has not been run end to end.

## 1. Dockerfile hygiene

**Why.** The image is built from what the Dockerfile says, so a floating base or a build-time upgrade changes the artifact without any commit.

**Apply.** In the `Dockerfile`:

- Multi-stage build, so build tools stay out of the final image.
- Base image pinned **by digest**, with the tag kept as a comment: `FROM nginxinc/nginx-unprivileged:1.30-alpine-slim@sha256:...`. Find the digest with `docker buildx imagetools inspect nginxinc/nginx-unprivileged:1.30-alpine-slim`.
- A non-root `USER`, or a base image that already runs as non-root.
- No `apt-get upgrade` or `apk upgrade`: it defeats the digest pin.
- Strict installs (golden path 3.4), such as `npm ci`.
- A label that links the package to the repo:

  ```dockerfile
  LABEL org.opencontainers.image.source="https://github.com/(repo)"
  ```

Add the `docker` ecosystem to Dependabot (golden path 3.5) so the digest-pinned base image gets update PRs.

**Verify.**

```bash
grep -nE '^FROM' Dockerfile                                  # every FROM has @sha256:
grep -nE '^USER|apt-get upgrade|apk upgrade' Dockerfile
```


## 2. The release workflow: build, scan, attest, tag

**Why.** One pipeline turns a protected tag into an image you can prove. It is built once and pushed by digest, and the digest is what everything after it uses. The pushed image is the one that gets scanned, attested and tagged. Provenance is signed by GitHub (Sigstore) as part of the attestation, so there is no separate signing step.

The scan runs **at release time** because a CVE can be published between the merge and the release. A scan that passed on the PR may not pass today.

**Apply.** Commit `.github/workflows/release.yml` in a PR. Replace `(repo)` with the lowercase `OWNER/REPO`, because image names must be lowercase.

```yaml
name: release

on:
  push:
    tags: ["v*.*.*"]

permissions: {}

env:
  IMAGE: ghcr.io/(repo)

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write # push to GHCR
    outputs:
      digest: ${{ steps.push.outputs.digest }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069 # v4.4.1
      - uses: docker/login-action@8aa5831fb8d48d8f76594c7ddde61ae58019f550 # v4.8.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: push
        uses: docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc # v7.4.0
        with:
          context: .
          # Pushed by digest, with no tag yet. Provenance comes from the attest job.
          outputs: type=image,name=${{ env.IMAGE }},push-by-digest=true,name-canonical=true,push=true
          provenance: false
          sbom: false

  scan:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: read
    steps:
      - uses: docker/login-action@8aa5831fb8d48d8f76594c7ddde61ae58019f550 # v4.8.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Install OSV-Scanner
        env:
          OSV_VERSION: v2.7.0
          OSV_SHA256: 160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b
        run: |
          curl -fsSL -o osv-scanner "https://github.com/google/osv-scanner/releases/download/${OSV_VERSION}/osv-scanner_linux_amd64"
          echo "${OSV_SHA256}  osv-scanner" | sha256sum --check
          chmod +x osv-scanner
      - name: Scan the pushed image
        env:
          DIGEST: ${{ needs.build.outputs.digest }}
        run: ./osv-scanner scan image "${IMAGE}@${DIGEST}"

  attest:
    needs: [build, scan]
    runs-on: ubuntu-latest
    permissions:
      id-token: write # request the signing certificate
      attestations: write
      packages: write # store the attestation next to the image
    steps:
      - uses: docker/login-action@8aa5831fb8d48d8f76594c7ddde61ae58019f550 # v4.8.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2
        with:
          subject-name: ${{ env.IMAGE }}
          subject-digest: ${{ needs.build.outputs.digest }}
          push-to-registry: true

  publish:
    needs: [build, attest]
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069 # v4.4.1
      - uses: docker/login-action@8aa5831fb8d48d8f76594c7ddde61ae58019f550 # v4.8.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Tag the attested digest
        env:
          DIGEST: ${{ needs.build.outputs.digest }}
          TAG: ${{ github.ref_name }}
        run: docker buildx imagetools create --tag "${IMAGE}:${TAG}" "${IMAGE}@${DIGEST}"
```

Notes:

- **This is the one place `needs:` is correct.** The rule against chaining applies to required checks, where a skipped job counts as passing. These jobs are not required checks, and each depends on the digest or the scan result before it. A failed scan stops the release.
- **Least privilege per job.** Only `attest` can request a signing identity (`id-token`, `attestations`). Only `build`, `attest` and `publish` can write packages.
- **If the scan fails**, an untagged image stays in GHCR but is never attested or tagged, so it never looks like a release. Fix the dependency and cut a new tag. To accept a finding you have judged harmless, OSV-Scanner reads an `osv-scanner.toml` with `[[IgnoredVulns]]` entries that take an `id`, a `reason` and an `ignoreUntil` date. Pass it with `--config`.
- OSV-Scanner fails on any finding it reports. It has no documented severity or "fixable only" filter, so expect to triage.
- The OSV binary is pinned by version and SHA-256, and Dependabot will not bump it. Update both together when you review pins.
- Everything outside the OSV install is pinned to a full SHA with a version comment, so Dependabot moves it.

**Cut a release.** This is the container flow: the release carries no assets, so it is fine to publish it at once even with immutable releases on (golden path 5.3).

```bash
gh release create v0.1.0 -R (repo) --target main --title v0.1.0 --notes "what changed"
```

**Verify.**

```bash
gh run list -R (repo) --workflow release.yml --limit 3
docker buildx imagetools inspect ghcr.io/(repo):v0.1.0     # note the digest
```

**Make required.** Not applicable: it runs on a tag.

**Not verified yet.** This workflow has not been run end to end. In particular, check that `provenance: false` leaves a plain image manifest, that `docker` can pull the digest for the OSV scan, and that `actions/attest` with only a subject creates SLSA build provenance, as its README says.


## 3. Verify before you use it

**Why.** Attestation only matters if something checks it. Refer to the image by digest, and verify the digest was built by your release workflow from your repo.

**Apply / Verify.**

```bash
DIGEST=sha256:...    # from section 2
gh attestation verify oci://ghcr.io/(repo)@$DIGEST --repo (repo) \
  --signer-workflow (repo)/.github/workflows/release.yml \
  --predicate-type https://slsa.dev/provenance/v1
```

The exit code is the answer: 0 means verified. Reference the image by digest, not by a tag, wherever it runs. Enforcing this check automatically where the image runs, such as a cluster admission policy, is outside this document.

**Skip when.** You do not consume your own images. Anyone else who does can run the same command.

## 4. Recommended: SBOM

**Why.** A list of what is inside the image, signed to the digest, so you can answer "does this release contain package X?" later without unpacking it.

**Apply.** Add two steps to the `attest` job, after the login step. Syft reads the image from the registry. Pinned to the commit for `v0.24.3`:

```yaml
      - uses: anchore/sbom-action@66cbf4bc1f1c0d2edc94016e65bc221b6bb0ad6c # v0.24.3
        with:
          image: ${{ env.IMAGE }}@${{ needs.build.outputs.digest }}
          registry-username: ${{ github.actor }}
          registry-password: ${{ secrets.GITHUB_TOKEN }}
          format: cyclonedx-json
          output-file: sbom.cdx.json
          upload-artifact: false
      - uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2
        with:
          subject-name: ${{ env.IMAGE }}
          subject-digest: ${{ needs.build.outputs.digest }}
          sbom-path: sbom.cdx.json
          push-to-registry: true
```

**Verify.**

```bash
gh attestation verify oci://ghcr.io/(repo)@$DIGEST --repo (repo) --predicate-type https://cyclonedx.org/bom
```

**Skip when.** You do not need to answer "what is inside this release?". Optional, not baseline.

## 5. GHCR package settings and retention

**Why.** The registry is where the artifact lives. The label from section 1 links the package to the repo. Pruning old versions can delete what your attestations reference.

**Apply.** Package visibility and "manage Actions access" are only in the web UI: `https://github.com/users/OWNER/packages/container/IMAGE/settings`. Confirm the package is linked to `(repo)`, and set the visibility you want.

**Verify.**

```bash
gh auth refresh -s read:packages
gh api 'users/OWNER/packages?package_type=container' --jq '.[] | [.name, .visibility, .repository.full_name] | @tsv'
gh api 'users/OWNER/packages/container/IMAGE/versions?per_page=100' --jq '.[] | [.id, .created_at[:10], (.metadata.container.tags | join(","))] | @tsv'
```

Do not prune "untagged" versions by hand or by script without checking: attestations are stored as untagged entries, and the section 2 scan failures leave untagged images too. Keep anything a release digest refers to.


## 6. Rescan the latest released image weekly

**Why.** The scan in section 2 covers the moment of release. A CVE published a month later affects the image you are running. A scheduled scan of the latest released tag closes that gap. It is a report, not a gate: a red run means "the released image has a known vulnerability".

**Apply.** Commit `.github/workflows/image-rescan.yml`. It reuses the OSV-Scanner install from section 2. Replace `(repo)` with the lowercase `OWNER/REPO`.

```yaml
name: image-rescan

on:
  schedule:
    - cron: "17 7 * * 1" # Mondays at 07:17 UTC
  workflow_dispatch:

permissions: {}

env:
  IMAGE: ghcr.io/(repo)

jobs:
  rescan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: read
    steps:
      - uses: docker/login-action@8aa5831fb8d48d8f76594c7ddde61ae58019f550 # v4.8.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Install OSV-Scanner
        env:
          OSV_VERSION: v2.7.0
          OSV_SHA256: 160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b
        run: |
          curl -fsSL -o osv-scanner "https://github.com/google/osv-scanner/releases/download/${OSV_VERSION}/osv-scanner_linux_amd64"
          echo "${OSV_SHA256}  osv-scanner" | sha256sum --check
          chmod +x osv-scanner
      - name: Scan the latest release
        env:
          GH_TOKEN: ${{ github.token }}
          REPO: ${{ github.repository }}
        run: |
          TAG=$(gh release view --repo "$REPO" --json tagName --jq .tagName)
          ./osv-scanner scan image "${IMAGE}:${TAG}"
```

**Verify.**

```bash
gh workflow run image-rescan.yml -R (repo)
gh run list -R (repo) --workflow image-rescan.yml --limit 3
```

**Make required.** Not applicable: it is scheduled. Like the scheduled OSV scan in layer 3, a failure is a signal, not a merge blocker.

**Not verified yet.** Pulling the image by tag in the scan, and `gh release view` with no release (the job fails, which is the right outcome before the first release).
