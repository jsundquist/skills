# Supply-chain checklist for a GitHub repo

Copy into the first PR. `R` is `OWNER/REPO`. Run `python scripts/audit.py R` after each section. Language- and tool-specific items (pnpm, uv, Docker, Kubernetes, ...) are in `stacks.md`.

## 0. Bootstrap (before any code)

- [ ] Public or private chosen on purpose; default branch `main`; `LICENSE` added if public
- [ ] Secret scanning, push protection, Dependabot alerts and security updates on
- [ ] Token read-only, Actions cannot approve PRs, **require actions pinned to a full SHA**
- [ ] `SECURITY.md` and private vulnerability reporting
- [ ] CodeQL default setup, if the language is supported
- [ ] Ruleset on `main`: no deletion, no force-push, PR required, required checks. Bootstrap lets the admin role bypass for pull requests so a solo owner can merge; remove that bypass once there is a second maintainer
- [ ] Tag protection for release tags (`v*.*.*`)
- [ ] Delete head branches on merge; auto-merge allowed only if a Dependabot auto-merge workflow needs it

```bash
# Everything above except SECURITY.md and LICENSE, in one go (dry run first, then --apply)
/jsundquist:repo-supply-chain-bootstrap R      # requires zizmor, actionlint, gitleaks, dependency-review, dependabot-coverage

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
- [ ] The artifact you publish is the artifact you scanned; gate on fixable HIGH and CRITICAL findings
- [ ] Record the artifact's digest or checksum as a job output and publish by that identifier
- [ ] Sign it; keep signing in its own job so only that job has `id-token` and `attestations: write`
- [ ] Verify the signature before deploy

```bash
# Every action pinned by full SHA? (prints offenders; run inside a clone)
grep -rnE '^\s*-?\s*uses:' .github/workflows | grep -vE '(\./|docker://)' | grep -vE '@[0-9a-f]{40}'
```

How to build, scan, sign and verify a specific artifact type is in `stacks.md` (containers today).

## 2. Package and dependency management

- [ ] Lockfile committed and enforced in CI (the install fails if the lock is out of date)
- [ ] Dependabot (or Renovate) for every ecosystem in the repo, including `github-actions`
- [ ] 7-day cooldown on every entry; group minor and patch; majors stay separate
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

Per-ecosystem controls (lockfile commands, release-age settings, build-script allow-lists) are in `stacks.md`.

## 3. Artifact repositories

- [ ] One registry per artifact type, each package linked to its repo
- [ ] Visibility chosen on purpose
- [ ] Publish with short-lived credentials (the `GITHUB_TOKEN` or OIDC), never a long-lived token
- [ ] Deployments reference an immutable identifier (digest or exact version), not a moving tag
- [ ] Retention for old versions, keeping whatever signatures and attestations reference
- [ ] Access review: who can push, pull and delete; which workflows have `packages: write`
- [ ] If you add a repository manager (Artifactory, Cloudsmith, Harbor): builds pull through it, direct public pulls blocked, allow/deny and licence policy, promotion between staging and production, audit log

Registry commands (GHCR) are in `stacks.md`.

## 4. SBOM

- [ ] Source SBOM generated on every push to the default branch (Syft, cdxgen, GitHub dependency submission, or your tool) and sent somewhere it is tracked (Dependency-Track, the GitHub dependency graph, an artifact store)
- [ ] The SBOM action pinned to a release commit with a `# vX.Y.Z` comment, so Dependabot can bump it
- [ ] An SBOM per built artifact, tied to its digest or checksum, attached as a signed attestation
- [ ] Every deployed artifact covered, including third-party ones
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
- [ ] **L3** needs the build in a reusable workflow the calling repo cannot alter (or `slsa-github-generator`); do not claim it without that

## 6. Secure golden path

- [ ] New repos start from a template that already has sections 0 to 5
- [ ] Secure steps live in reusable workflows, so one fix reaches every repo
- [ ] Controls are required checks and a ruleset, not optional
- [ ] The place you deploy to enforces what CI promises (admission policy, digest check, signature check)
- [ ] Deploy only through reviewed changes in git
- [ ] A written path a new repo can follow in under an hour: this file
- [ ] A score you re-run: the audit script, plus OpenSSF Scorecard

```bash
# Make a repo a template, then create new repos from it
gh repo edit OWNER/template-repo --template
gh repo create OWNER/new-repo --template OWNER/template-repo --public --clone

# OpenSSF Scorecard result for a public repo
curl -s https://api.securityscorecards.dev/projects/github.com/OWNER/REPO
```
