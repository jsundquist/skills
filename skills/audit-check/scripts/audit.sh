#!/usr/bin/env bash
# Read-only supply-chain audit of one GitHub repository, using only the gh CLI.
#
#   scripts/audit.sh owner/repo
#   scripts/audit.sh owner/repo | grep -E '❌|⚠️'      # only the gaps
#
# Needs: gh (logged in, with repo admin on the target for the settings calls), bash.
# Optional: `gh auth refresh -s read:packages` to include GHCR package checks.
# Nothing here changes anything. Every line is a check; ✅ ok, ⚠️ look at it, ❌ missing, ℹ️ information.

set -u
REPO="${1:?usage: $0 owner/repo}"
OWNER="${REPO%%/*}"
BRANCH="$(gh api "repos/$REPO" --jq .default_branch 2>/dev/null)" || { echo "cannot read $REPO"; exit 1; }

ok()   { echo "✅ $*"; }
bad()  { echo "❌ $*"; }
warn() { echo "⚠️  $*"; }
info() { echo "ℹ️  $*"; }
hdr()  { echo; echo "## $*"; }
api()  { gh api "$@" 2>/dev/null; }
raw()  { gh api -H "Accept: application/vnd.github.raw+json" "repos/$REPO/contents/$1?ref=$BRANCH" 2>/dev/null; }

echo "# Supply-chain audit: $REPO ($BRANCH), $(date +%Y-%m-%d)"

# ---------------------------------------------------------------- tree
TREE="$(api "repos/$REPO/git/trees/$BRANCH?recursive=1" --jq '.tree[].path')"
has_file() { echo "$TREE" | grep -qiE "$1"; }

hdr "Repository settings"
VIS="$(api "repos/$REPO" --jq '.visibility')"
info "visibility: $VIS"
SA="$(api "repos/$REPO" --jq '.security_and_analysis // {} | [.secret_scanning.status, .secret_scanning_push_protection.status, .dependabot_security_updates.status] | @tsv')"
set -- $SA
[ "${1:-}" = enabled ] && ok "secret scanning" || bad "secret scanning (${1:-unknown})"
[ "${2:-}" = enabled ] && ok "push protection" || bad "push protection (${2:-unknown})"
[ "${3:-}" = enabled ] && ok "Dependabot security updates" || bad "Dependabot security updates (${3:-unknown})"
[ "$(api "repos/$REPO/vulnerability-alerts" -i 2>/dev/null | head -1 | grep -c 204)" = 1 ] && ok "Dependabot alerts enabled" || warn "Dependabot alerts: could not confirm"

PERM="$(api "repos/$REPO/actions/permissions")"
SHA="$(echo "$PERM" | sed -n 's/.*"sha_pinning_required":\([a-z]*\).*/\1/p')"
[ "$SHA" = true ] && ok "Actions: require actions pinned to a full SHA" || bad "Actions: require actions pinned to a full SHA (off)"
WF="$(api "repos/$REPO/actions/permissions/workflow")"
echo "$WF" | grep -q '"default_workflow_permissions":"read"' && ok "default GITHUB_TOKEN is read-only" || bad "default GITHUB_TOKEN is not read-only"
echo "$WF" | grep -q '"can_approve_pull_request_reviews":false' && ok "Actions cannot approve PRs" || bad "Actions can approve PRs"

PVR="$(api "repos/$REPO/private-vulnerability-reporting" --jq .enabled)"
[ "$PVR" = true ] && ok "private vulnerability reporting" || bad "private vulnerability reporting (off)"

CQ="$(api "repos/$REPO/code-scanning/default-setup" --jq '[.state, (.languages|join(","))] | @tsv')"
CQ_LANGS="$(echo "$CQ" | cut -f2)"
case "$CQ" in
  configured*) if [ -n "$CQ_LANGS" ]; then ok "CodeQL default setup: $CQ_LANGS"; else warn "CodeQL default setup is on but covers no languages yet (nothing is scanned until the repo has supported code)"; fi ;;
  *) bad "CodeQL default setup: ${CQ:-unknown}" ;;
esac

num() { case "$1" in ''|*[!0-9]*) echo unknown ;; *) echo "$1" ;; esac; }

hdr "Open alerts"
DB="$(api "repos/$REPO/dependabot/alerts?state=open&per_page=100" --jq length)"
DB="$(num "$DB")"
[ "$DB" = 0 ] && ok "Dependabot alerts: 0" || warn "Dependabot alerts open: $DB"
CS="$(api "repos/$REPO/code-scanning/alerts?state=open&per_page=100" --jq length)"
CS="$(num "$CS")"
[ "$CS" = 0 ] && ok "code scanning alerts: 0" || warn "code scanning alerts open: $CS (unknown = alerts disabled, or no analysis yet)"
SS="$(api "repos/$REPO/secret-scanning/alerts?state=open&per_page=100" --jq length)"
SS="$(num "$SS")"
[ "$SS" = 0 ] && ok "secret scanning alerts: 0" || warn "secret scanning alerts open: $SS"

hdr "Protection of $BRANCH"
RS="$(api "repos/$REPO/rulesets" --jq '.[] | select(.target=="branch") | .id')"
CLASSIC=0
if api "repos/$REPO/branches/$BRANCH/protection" >/dev/null; then CLASSIC=1; fi
if [ -z "$RS" ] && [ "$CLASSIC" = 0 ]; then bad "no ruleset and no branch protection"; fi
for id in $RS; do
  R="$(api "repos/$REPO/rulesets/$id")"
  NAME="$(echo "$R" | sed -n 's/^{"id":[0-9]*,"name":"\([^"]*\)".*/\1/p')"
  info "ruleset #$id ${NAME:-}"
  api "repos/$REPO/rulesets/$id" --jq '"   enforcement: \(.enforcement)  bypass actors: \(.bypass_actors|length)  rules: \([.rules[].type]|join(", "))"'
  api "repos/$REPO/rulesets/$id" --jq '.rules[] | select(.type=="required_status_checks") | "   required checks: \([.parameters.required_status_checks[].context]|join(", "))  strict: \(.parameters.strict_required_status_checks_policy)"'
  api "repos/$REPO/rulesets/$id" --jq '.rules[] | select(.type=="pull_request") | "   required approvals: \(.parameters.required_approving_review_count)"'
done
if [ "$CLASSIC" = 1 ]; then
  info "classic branch protection"
  api "repos/$REPO/branches/$BRANCH/protection" --jq '"   required checks: \([.required_status_checks.checks[]?.context]|join(", "))  strict: \(.required_status_checks.strict)  enforce_admins: \(.enforce_admins.enabled)  approvals: \(.required_pull_request_reviews.required_approving_review_count // 0)  force-push allowed: \(.allow_force_pushes.enabled)  deletions allowed: \(.allow_deletions.enabled)"'
fi

hdr "Policy files"
has_file '^(\.github/|docs/)?SECURITY\.md$' && ok "SECURITY.md" || bad "SECURITY.md"
has_file '^\.github/dependabot\.ya?ml$' && ok "dependabot.yml" || { has_file '^(\.github/)?renovate\.json5?$' && ok "renovate config" || bad "no dependabot.yml or renovate config"; }
has_file '(^|/)CODEOWNERS$' && ok "CODEOWNERS" || info "no CODEOWNERS (fine for a solo repo)"
has_file '^LICENSE' && ok "LICENSE" || warn "no LICENSE"
has_file '(^|/)(lefthook|\.pre-commit-config)\.ya?ml$|^\.husky/' && ok "pre-commit hooks present" || warn "no pre-commit hooks (gitleaks locally)"
has_file '^\.gitleaks\.toml$' && info "gitleaks config present"

hdr "Dependabot configuration"
if has_file '^\.github/dependabot\.ya?ml$'; then
  DEP="$(raw .github/dependabot.yml; [ -z "$(raw .github/dependabot.yml)" ] && raw .github/dependabot.yaml)"
  echo "$DEP" | grep -E 'package-ecosystem' | sed 's/^ *- */   /'
  N="$(echo "$DEP" | grep -c 'package-ecosystem')"
  C="$(echo "$DEP" | grep -c 'default-days')"
  [ "$N" = "$C" ] && ok "cooldown on every ecosystem ($C of $N)" || bad "cooldown on $C of $N ecosystems"
  # Ecosystems the repo uses but Dependabot is not configured for
  for pair in 'package-lock.json|pnpm-lock.yaml|yarn.lock:npm' 'uv.lock|requirements.*\.txt|poetry.lock:uv|pip' 'Dockerfile:docker' '^\.github/workflows/:github-actions' 'go.mod:gomod' 'Cargo.toml:cargo'; do
    pat="${pair%%:*}"; eco="${pair#*:}"
    if has_file "$pat" && ! echo "$DEP" | grep -qE "package-ecosystem: *\"?($eco)"; then warn "repo has files for $eco but Dependabot is not configured for it"; fi
  done
fi

hdr "Package manager hardening"
has_file '(^|/)pnpm-lock\.yaml$' && ok "pnpm-lock.yaml committed"
has_file '(^|/)package-lock\.json$' && ok "package-lock.json committed"
has_file '(^|/)uv\.lock$' && ok "uv.lock committed"
if has_file '(^|/)package\.json$' && ! has_file '(^|/)(pnpm-lock\.yaml|package-lock\.json|yarn\.lock)$'; then bad "package.json without a lockfile"; fi
if has_file '^pnpm-workspace\.yaml$'; then
  PW="$(raw pnpm-workspace.yaml)"
  echo "$PW" | grep -q 'minimumReleaseAge' && ok "pnpm minimumReleaseAge set" || bad "pnpm minimumReleaseAge not set"
  echo "$PW" | grep -qE 'allowBuilds|onlyBuiltDependencies' && ok "pnpm build scripts allow-listed" || warn "pnpm build scripts not allow-listed"
fi

hdr "Workflows"
WFS="$(echo "$TREE" | grep -E '^\.github/workflows/.*\.ya?ml$')"
ALL=""
for f in $WFS; do
  body="$(raw "$f")"
  ALL="$ALL
$body"
  unpinned="$(echo "$body" | grep -E '^\s*-?\s*uses:' | grep -vE 'uses:\s*(\./|docker://)' | grep -vE '@[0-9a-f]{40}(\s|$)')"
  [ -n "$unpinned" ] && { warn "$f: actions not pinned to a full SHA:"; echo "$unpinned" | sed 's/^/     /'; }
  echo "$body" | grep -qE '^permissions:' || echo "$body" | grep -qE '^\s{2,}permissions:' || warn "$f: no permissions block (inherits the default)"
  echo "$body" | grep -qE '^\s*run:.*\$\{\{ *(github\.event|github\.head_ref|inputs)' && warn "$f: expression in a run: line (injection risk, use env:)"
  echo "$body" | grep -q 'pull_request_target' && info "$f: uses pull_request_target (check it never checks out PR code)"
done
[ -z "$WFS" ] && bad "no workflows" || ok "$(echo "$WFS" | wc -l | tr -d ' ') workflow files"
chk() { echo "$ALL" | grep -qiE "$1" && ok "$2" || bad "$2 (not found)"; }
chk 'persist-credentials: *false' "checkout with persist-credentials: false"
chk 'zizmor' "zizmor"
chk 'actionlint' "actionlint"
chk 'gitleaks' "gitleaks in CI"
chk 'dependency-review-action' "dependency-review on PRs"
chk 'check-dependabot-coverage|dependabot-coverage' "dependabot-coverage (manifests vs dependabot.yml)"
chk 'sbom|cyclonedx|syft|cdxgen|dependency-snapshot|spdx' "SBOM generation"
chk 'attest-build-provenance|actions/attest|slsa-github-generator' "provenance attestation (SLSA)"
echo "$ALL" | grep -qiE 'pnpm audit|npm audit|pip-audit|osv-scanner|cargo audit|govulncheck' && ok "vulnerability audit in CI" || bad "vulnerability audit in CI (not found)"
echo "$ALL" | grep -qE 'cron:' && ok "a scheduled workflow exists (check it covers audit)" || warn "no scheduled workflow (new CVEs appear without commits)"

if has_file '(^|/)Dockerfile'; then
  hdr "Container build"
  chk 'trivy' "Trivy scan"
  chk 'cosign|sigstore' "signing (cosign / sigstore)"
  chk 'attest-build-provenance|actions/attest@|attest-sbom|actions/attest' "attestations (provenance / SBOM)"
  chk 'push: *true|docker/build-push-action' "image push in CI"
  for d in $(echo "$TREE" | grep -E '(^|/)Dockerfile'); do
    body="$(raw "$d")"
    for line in $(echo "$body" | grep -E '^FROM ' | awk '{print $2}'); do
      case "$line" in *@sha256:*) ok "$d: base $line pinned by digest";; scratch) ;; *) echo "$body" | grep -qE "AS +$line( |$)" || warn "$d: base image not pinned by digest: $line";; esac
    done
    echo "$body" | grep -qE '^USER +[0-9a-z]' && ok "$d: runs as non-root USER" || warn "$d: no USER instruction (fine if the base image already runs non-root, e.g. nginx-unprivileged; confirm with docker inspect)"
    echo "$body" | grep -q 'org.opencontainers.image.source' && ok "$d: image.source label" || warn "$d: no org.opencontainers.image.source label"
    echo "$body" | grep -qE 'apt-get (upgrade|dist-upgrade)|apk upgrade' && warn "$d: OS upgrade at build time (makes the digest-pinned base non-reproducible)"
  done
fi

hdr "Releases and tags"
REL="$(api "repos/$REPO/releases?per_page=3" --jq '.[].tag_name' | tr '\n' ' ')"
[ -n "$REL" ] && info "releases: $REL" || info "no GitHub releases"

hdr "Secrets (names only)"
api "repos/$REPO/actions/secrets" --jq '.secrets[] | "   \(.name)  (updated \(.updated_at[:10]))"'
api "repos/$REPO/actions/variables" --jq '.variables[] | "   var \(.name)"'

hdr "Packages (GHCR)"
PK="$(api "users/$OWNER/packages?package_type=container&per_page=100" --jq '.[] | select(.repository.full_name=="'"$REPO"'") | "   \(.name)  \(.visibility)"')"
[ -n "$PK" ] && ! echo "$PK" | grep -q '"message"' && echo "$PK" || info "none found, or the token lacks read:packages (gh auth refresh -s read:packages)"

hdr "Recent workflow health"
api "repos/$REPO/actions/runs?branch=$BRANCH&per_page=10" --jq '[.workflow_runs[] | select(.conclusion=="failure")] | length | "failed runs among the last 10 on '"$BRANCH"': \(.)"'
