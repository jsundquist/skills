# Supply-chain checklist for a GitHub repo

Copy into the first PR. `R` is `OWNER/REPO`. Run `scripts/audit.sh R` after each section.

## 0. Bootstrap (before any code)

- [ ] Public or private chosen on purpose; default branch `main`; `LICENSE` added if public
- [ ] Secret scanning, push protection, Dependabot alerts and security updates on
- [ ] Token read-only, Actions cannot approve PRs, **require actions pinned to a full SHA**
- [ ] `SECURITY.md` and private vulnerability reporting
- [ ] CodeQL default setup, if the language is supported
- [ ] Ruleset on `main`: no deletion, no force-push, PR required, required checks, no bypass actors
- [ ] Tag protection for release tags (`v*.*.*`)
- [ ] Delete head branches on merge; auto-merge allowed only if a Dependabot auto-merge workflow needs it

```bash
# Everything above except SECURITY.md and LICENSE, in one go (dry run first, then --apply)
/audit-bootstrap R --checks "test,lint,secrets,workflow-lint,zizmor,dependency-review"

# Or one setting at a time
gh api -X PATCH repos/R \
  -f 'security_and_analysis[secret_scanning][status]=enabled' \
  -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' \
  -f 'security_and_analysis[dependabot_security_updates][status]=enabled'
gh api -X PUT repos/R/vulnerability-alerts
gh api -X PUT repos/R/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
gh api -X PUT repos/R/actions/permissions -F enabled=true -f allowed_actions=all -F sha_pinning_required=true
gh api -X PUT repos/R/private-vulnerability-reporting
gh api -X PATCH repos/R/code-scanning/default-setup -f state=configured -f query_suite=default

# Read each setting back
gh api repos/R --jq '.security_and_analysis'
gh api repos/R/actions/permissions            # sha_pinning_required
gh api repos/R/actions/permissions/workflow
gh api repos/R/private-vulnerability-reporting
gh api repos/R/code-scanning/default-setup

# Protect release tags (cannot be deleted or rewritten; a moving tag like v1 is not matched by v*.*.*)
gh api -X POST repos/R/rulesets --input - <<'JSON'
{ "name": "Protect release tags", "target": "tag", "enforcement": "active", "bypass_actors": [],
  "conditions": { "ref_name": { "include": ["refs/tags/v*.*.*"], "exclude": [] } },
  "rules": [ { "type": "deletion" }, { "type": "non_fast_forward" } ] }
JSON
```

Add a check to an existing **classic** branch protection (this replaces the list, so include every check you want; read it first):

```bash
gh api repos/R/branches/main/protection/required_status_checks --jq '{strict, checks: [.checks[].context]}'
gh api -X PATCH repos/R/branches/main/protection/required_status_checks --input - <<'JSON'
{ "strict": true,
  "checks": [ {"context":"test","app_id":15368}, {"context":"lint","app_id":15368} ] }
JSON
```

Add a check to a **ruleset**: fetch it, edit the `required_status_checks` list, and PUT it back.

```bash
gh api repos/R/rulesets --jq '.[] | [.id, .name, .enforcement] | @tsv'
gh api repos/R/rulesets/ID > ruleset.json     # edit required_status_checks, then:
gh api -X PUT repos/R/rulesets/ID --input ruleset.json
```

Only require a check after it has run successfully once, or every PR will wait for a check that never reports.

## 1. Artifact hardening

- [ ] Builds run in CI from a clean checkout on a hosted runner
- [ ] Top-level `permissions: {}` or `contents: read`; widen per job
- [ ] Every action pinned by full SHA with a version comment; `persist-credentials: false` on checkout
- [ ] No `${{ }}` expressions inside `run:`; pass values through `env:`
- [ ] actionlint and zizmor in CI and required
- [ ] Container: multi-stage, base pinned by digest, non-root, no OS upgrade at build time (it defeats the digest pin), `org.opencontainers.image.source` label
- [ ] Trivy gate on HIGH and CRITICAL fixable, scanning the image that will be pushed
- [ ] Push by digest, record the digest as a job output
- [ ] Sign by digest with cosign keyless; separate the signing job so only it has `id-token` and `attestations: write`
- [ ] Verify the signature before deploy

```bash
# Every action pinned by full SHA? (prints offenders; run inside a clone)
grep -rnE '^\s*-?\s*uses:' .github/workflows | grep -vE '(\./|docker://)' | grep -vE '@[0-9a-f]{40}'

# Does the image carry a signature, provenance and an SBOM attestation?
gh attestation verify oci://ghcr.io/OWNER/IMAGE@sha256:DIGEST --owner OWNER --predicate-type https://slsa.dev/provenance/v1
gh attestation verify oci://ghcr.io/OWNER/IMAGE@sha256:DIGEST --owner OWNER --predicate-type https://cyclonedx.org/bom
# (it prints nothing when not on a terminal; read the exit code: echo $?)

cosign verify ghcr.io/OWNER/IMAGE@sha256:DIGEST \
  --certificate-identity 'https://github.com/OWNER/REPO/.github/workflows/release.yml@refs/heads/main' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com

# Digest of a tag, and the base image's digest
docker buildx imagetools inspect ghcr.io/OWNER/IMAGE:TAG
docker buildx imagetools inspect nginxinc/nginx-unprivileged:1.30-alpine-slim
```

## 2. Package and dependency management

- [ ] Lockfile committed and enforced (`--frozen-lockfile`, `uv sync --frozen`)
- [ ] Dependabot (or Renovate) for every ecosystem in the repo: language packages, `github-actions`, `docker`, `docker-compose`, Helm and kustomize if present
- [ ] 7-day cooldown on every entry; group minor and patch; majors stay separate
- [ ] pnpm: `allowBuilds` list and `minimumReleaseAge`; Python: lock reviewed
- [ ] Vulnerability audit on push and PR, plus a weekly schedule (new CVEs appear without commits)
- [ ] `dependency-review-action` on PRs and **required**
- [ ] Every audit ignore has a reason, a scope and a removal condition
- [ ] gitleaks in pre-commit and in CI over full history
- [ ] Auto-merge only for dependency types and update levels you would merge unread
- [ ] Before adding a dependency: maintainers, release age, install scripts, smaller alternatives

```bash
# Which ecosystems does Dependabot cover, and does each have a cooldown?
gh api repos/R/contents/.github/dependabot.yml --jq .content | base64 -d | grep -E 'package-ecosystem|default-days'

# Open Dependabot alerts (quote the URL: zsh treats ? as a glob)
gh api 'repos/R/dependabot/alerts?state=open' \
  --jq '.[] | [.number, .security_advisory.severity, .dependency.package.name, .dependency.scope, (.security_vulnerability.first_patched_version.identifier // "no fix")] | @tsv'

# Dependabot and Renovate PRs waiting
gh pr list -R R --author 'app/dependabot'
gh pr list -R R --author 'app/renovate'
gh pr checks PR_NUMBER -R R

# Other code scanning and secret scanning alerts
gh api 'repos/R/code-scanning/alerts?state=open' --jq '.[] | [.number, .rule.severity, .rule.id] | @tsv'
gh api 'repos/R/secret-scanning/alerts?state=open' --jq '.[] | [.number, .secret_type_display_name] | @tsv'
```

## 3. Artifact repositories

- [ ] One registry per artifact type (GHCR for images), package linked to its repo
- [ ] Visibility chosen on purpose; public images need no pull secret
- [ ] Push with the short-lived `GITHUB_TOKEN`; deployments reference the **digest**
- [ ] Retention for old untagged versions, keeping what signatures and attestations reference
- [ ] Access review: who can push, pull and delete; which workflows have `packages: write`
- [ ] If you add a repository manager (Artifactory, Cloudsmith, Harbor): builds pull through it, direct public pulls blocked, allow/deny and licence policy, promotion between staging and production, audit log

```bash
gh auth refresh -s read:packages            # once; then:
gh api 'users/OWNER/packages?package_type=container' --jq '.[] | [.name, .visibility, .repository.full_name] | @tsv'
gh api 'users/OWNER/packages/container/IMAGE/versions?per_page=100' --jq 'length'
gh api 'users/OWNER/packages/container/IMAGE/versions?per_page=100' \
  --jq '.[] | [.id, .created_at[:10], (.metadata.container.tags | join(","))] | @tsv'
# Package visibility and "manage Actions access" are only in the web UI:
#   https://github.com/users/OWNER/packages/container/IMAGE/settings
```

## 4. SBOM

- [ ] Source SBOM generated on every push to `main` (Syft, cdxgen, `actions/dependency-snapshot`, or your tool) and sent somewhere it is tracked (Dependency-Track, GitHub dependency graph, an artifact store)
- [ ] The SBOM action pinned to a release commit with a `# vX.Y.Z` comment, so Dependabot can bump it
- [ ] Image SBOM per built image, tied to its digest, attached as a signed attestation
- [ ] Every deployed image, including third-party ones, covered
- [ ] Findings triaged; accepted risks have a reason and a review date
- [ ] Repos without push triggers (bot merges) have a scheduled run or a dispatch

```bash
gh secret list -R R                         # names and update dates only
gh secret set SOME_TOKEN -R R               # prompts; never pass the value on the command line
gh run list -R R --workflow sbom.yml --limit 5
```

## 5. SLSA

- [ ] Build scripted and run in CI from version control
- [ ] Provenance generated and signed by the platform (`actions/attest`) for **L2**
- [ ] Provenance verified before deploy
- [ ] Claimed level written in the README, with what is missing for the next level
- [ ] **L3** needs the build in a reusable workflow the calling repo cannot alter (or `slsa-github-generator`); this is not claimed today

## 6. Secure golden path

- [ ] New repos start from a template that already has sections 0 to 5
- [ ] Secure steps live in reusable workflows, so one fix reaches every repo
- [ ] Controls are required checks and a ruleset, not optional
- [ ] The cluster enforces what CI promises (PSA, digest check, signature check)
- [ ] Deploy only through git and Argo CD
- [ ] A written path a new repo can follow in under an hour: this file
- [ ] A score you re-run: the audit script, plus OpenSSF Scorecard

```bash
# Make a repo a template, then create new repos from it
gh repo edit OWNER/template-repo --template
gh repo create OWNER/new-repo --template OWNER/template-repo --public --clone

# OpenSSF Scorecard on any public repo
docker run --rm -e GITHUB_AUTH_TOKEN="$(gh auth token)" gcr.io/openssf/scorecard:stable --repo=github.com/OWNER/REPO
```

## 7. Releasing an action or library

```bash
SHA=$(git rev-parse HEAD)                    # a commit on main that is already green
gh release create v1.0.0 -R R --target "$SHA" --title v1.0.0 --notes "what changed"
# Moving major tag (v1) for consumers who want automatic patches; consumers still pin the commit SHA
gh api -X POST repos/R/git/refs -f ref=refs/tags/v1 -f sha="$SHA"                    # first time
gh api -X PATCH repos/R/git/refs/tags/v1 -f sha="$SHA" -F force=true                 # later moves
gh release list -R R
```

