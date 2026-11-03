#!/usr/bin/env bash
# Apply baseline supply-chain settings and starter files to a GitHub repo with the gh CLI.
# Prints each command first. Dry run unless you pass --apply.
#
#   bootstrap.sh owner/new-repo                         # show what it would do
#   bootstrap.sh owner/new-repo --apply                 # settings + starter files, committed to the default branch
#   bootstrap.sh owner/new-repo --apply --scorecard     # also add the OpenSSF Scorecard workflow
#   bootstrap.sh owner/new-repo --apply --checks default    # later: create the main-branch ruleset
#
# Options:
#   --apply          execute (default is a dry run)
#   --checks LIST    create (or update in place) the default-branch ruleset requiring these checks
#                    (comma-separated), or "default" for the checks the starter workflows define.
#                    Skipped, with a warning, if any listed check has not reported on the branch yet.
#                    The ruleset requires 1 approval, code-owner review, last-push approval and stale
#                    review dismissal, with the repo admin role allowed to bypass for pull requests so
#                    a solo owner can still merge. Drop the bypass if you have a second reviewer.
#   --scorecard      also add .github/workflows/scorecard.yml
#   --license ID     also add a LICENSE from GitHub's license list (mit, apache-2.0, ...); never defaulted
#   --codeowner X    code owner for .github/CODEOWNERS: @user or @org/team. Defaults to the repo owner on a
#                    personal account. On an organization-owned repo it is required: without it CODEOWNERS
#                    is skipped and the ruleset does not require code-owner review (an org cannot own code).
#   --no-scaffold    settings only; do not add files
#   --show           print the rendered files in the dry run
#
# Starter files (templates/default) are only created when absent, never overwritten:
#   .github/workflows/security.yml              jobs: zizmor, actionlint, gitleaks, dependency-review
#   .github/workflows/dependabot-coverage.yml   job:  dependabot-coverage
#   .github/scripts/check-dependabot-coverage.sh
#   .github/dependabot.yml                      github-actions, 7-day cooldown
#   .github/CODEOWNERS                          * @owner (the ruleset requires code-owner review)
#   SECURITY.md
# Action versions are pinned in PINS below and resolved to full commit SHAs when the script runs,
# because the settings turn on "require actions pinned to a full SHA".
#
# When the repo has .github/workflows/scorecard.yml, open Scorecard alerts that cannot be fixed on a
# new repo (CodeReview, Maintained, Fuzzing, CII-Best-Practices, SAST) are dismissed as "won't fix"
# with a comment. Fixable ones (Pinned-Dependencies, License, Branch-Protection, ...) are left open.
#
# Order: run once with --apply (settings + files), wait for the workflows to finish on the default
# branch, then run again with --checks default. It never touches secrets, tags or releases.

set -uo pipefail
REPO="${1:?usage: $0 owner/repo [--apply] [--checks a,b,c|default] [--scorecard] [--license ID] [--codeowner @x] [--no-scaffold] [--show]}"
shift
APPLY=0
CHECKS=""
SCORECARD=0
LICENSE_ID=""
CODEOWNER=""
SCAFFOLD=1
SHOW=0
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --checks) CHECKS="${2:?--checks needs a comma-separated list or 'default'}"; shift ;;
    --scorecard) SCORECARD=1 ;;
    --codeowner) CODEOWNER="${2:?--codeowner needs @user or @org/team}"; shift ;;
    --license) LICENSE_ID="${2:?--license needs an id such as mit}"; shift ;;
    --no-scaffold) SCAFFOLD=0 ;;
    --show) SHOW=1 ;;
    *) echo "unknown argument: $1"; exit 2 ;;
  esac
  shift
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TPL="$HERE/../templates"
DEFAULT_CHECKS="zizmor,actionlint,gitleaks,dependency-review,dependabot-coverage"
[ "$CHECKS" = default ] && CHECKS="$DEFAULT_CHECKS"
FAILED=0

PINS="
actions/checkout v7.0.1
zizmorcore/zizmor-action v0.8.1
gitleaks/gitleaks-action v3.0.0
actions/dependency-review-action v5.0.0
raven-actions/actionlint v2.2.0
ossf/scorecard-action v2.5.0
github/codeql-action v4.39.2
"

INFO="$(gh api "repos/$REPO" --jq '[.default_branch, .visibility] | @tsv' 2>/dev/null)" || { echo "cannot read $REPO"; exit 1; }
BRANCH="${INFO%%$'\t'*}"
VISIBILITY="${INFO#*$'\t'}"
PUBLISH=false
[ "$VISIBILITY" = public ] && PUBLISH=true

OWNER_LOGIN="${REPO%%/*}"
OWNER_TYPE="$(gh api "users/$OWNER_LOGIN" --jq .type 2>/dev/null)"
case "$CODEOWNER" in
  ''|@?*) ;;
  *) echo "--codeowner must start with @ (for example @$OWNER_LOGIN or @$OWNER_LOGIN/team)"; exit 2 ;;
esac
if [ -z "$CODEOWNER" ] && [ "$OWNER_TYPE" = User ]; then CODEOWNER="@$OWNER_LOGIN"; fi
# Code-owner review only makes sense if a CODEOWNERS file will exist (ours, or one already in the repo)
HAS_CODEOWNERS=false
if [ -n "$CODEOWNER" ]; then HAS_CODEOWNERS=true; fi
for f in .github/CODEOWNERS CODEOWNERS docs/CODEOWNERS; do
  gh api "repos/$REPO/contents/$f" >/dev/null 2>&1 && HAS_CODEOWNERS=true
done

run() {
  echo "+ $*"
  [ "$APPLY" = 1 ] || return 0
  local err
  if ! err="$("$@" 2>&1)"; then
    echo "  FAILED: $(printf '%s' "$err" | head -c 300)"
    FAILED=$((FAILED + 1))
  fi
}

pin_tag() { echo "$PINS" | awk -v r="$1" '$1 == r { print $2 }'; }

# Replace {{pin:owner/repo[/path]}}, {{sha:owner/repo}}, {{ver:owner/repo}}, {{repo}}, {{branch}}, {{publish}}
render() {
  local out m kind arg repo tag sha rep
  out="$(cat "$1")"
  for m in $(printf '%s\n' "$out" | grep -o '{{[a-z]*:[^}]*}}' | sort -u); do
    kind="${m#\{\{}"; kind="${kind%%:*}"
    arg="${m#*:}"; arg="${arg%\}\}}"
    repo="$(echo "$arg" | cut -d/ -f1-2)"
    tag="$(pin_tag "$repo")"
    if [ -z "$tag" ]; then echo "no pinned version for $repo" >&2; return 1; fi
    sha="$(gh api "repos/$repo/commits/$tag" --jq .sha 2>/dev/null)"
    if [ -z "$sha" ]; then echo "cannot resolve $repo@$tag" >&2; return 1; fi
    case "$kind" in
      pin) rep="$arg@$sha # $tag" ;;
      sha) rep="$sha" ;;
      ver) rep="${tag#v}" ;;
      *) echo "unknown placeholder $m" >&2; return 1 ;;
    esac
    out=${out//"$m"/$rep}
  done
  out=${out//\{\{repo\}\}/$REPO}
  out=${out//\{\{codeowner\}\}/$CODEOWNER}
  out=${out//\{\{branch\}\}/$BRANCH}
  out=${out//\{\{publish\}\}/$PUBLISH}
  printf '%s\n' "$out"
}

put_file() {
  local path="$1" body="$2" err b64
  if gh api "repos/$REPO/contents/$path" >/dev/null 2>&1; then
    echo "= $path exists, left alone"
    return 0
  fi
  echo "+ create $path"
  if [ "$SHOW" = 1 ]; then printf '%s\n' "$body" | sed 's/^/    | /'; fi
  [ "$APPLY" = 1 ] || return 0
  b64="$(printf '%s\n' "$body" | base64 | tr -d '\n')"
  if ! err="$(gh api -X PUT "repos/$REPO/contents/$path" -f message="chore(security): add $path" -f content="$b64" -f branch="$BRANCH" 2>&1)"; then
    echo "  FAILED: $(printf '%s' "$err" | head -c 300)"
    FAILED=$((FAILED + 1))
  fi
}

scaffold() {
  local dir="$1" rel body
  for rel in $(cd "$dir" && find . -type f | sed 's#^\./##' | sort); do
    if [ "$rel" = .github/CODEOWNERS ] && [ -z "$CODEOWNER" ]; then
      echo "! skipping .github/CODEOWNERS: $REPO is owned by an organization; pass --codeowner @user-or-@org/team"
      continue
    fi
    if ! body="$(render "$dir/$rel")"; then
      echo "  FAILED: could not render $rel"
      FAILED=$((FAILED + 1))
      continue
    fi
    put_file "$rel" "$body"
  done
}

echo "# $REPO ($VISIBILITY, default branch $BRANCH) ($( [ "$APPLY" = 1 ] && echo APPLY || echo 'dry run, pass --apply to execute' ))"

# Secret scanning, push protection and Dependabot security updates
run gh api -X PATCH "repos/$REPO" \
  -f 'security_and_analysis[secret_scanning][status]=enabled' \
  -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' \
  -f 'security_and_analysis[dependabot_security_updates][status]=enabled'
run gh api -X PUT "repos/$REPO/vulnerability-alerts"

# Actions: read-only token, no PR approval by Actions, every action pinned to a full SHA
run gh api -X PUT "repos/$REPO/actions/permissions/workflow" \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
run gh api -X PUT "repos/$REPO/actions/permissions" \
  -F enabled=true -f allowed_actions=all -F sha_pinning_required=true

# Private vulnerability reporting (pair it with a SECURITY.md)
run gh api -X PUT "repos/$REPO/private-vulnerability-reporting"

# CodeQL default setup. Accepted on an empty repo, but scans nothing until there is code in a supported language.
run gh api -X PATCH "repos/$REPO/code-scanning/default-setup" -f state=configured -f query_suite=default

# Tidy merges
run gh repo edit "$REPO" --delete-branch-on-merge

# Starter files, committed to the default branch (only when absent)
if [ "$SCAFFOLD" = 1 ]; then
  echo
  echo "# Starter files (pinned action SHAs are resolved now)"
  scaffold "$TPL/default"
  [ "$SCORECARD" = 1 ] && scaffold "$TPL/scorecard"
fi

# LICENSE from GitHub's license list
if [ -n "$LICENSE_ID" ]; then
  echo
  HOLDER="$(gh api "users/$OWNER_LOGIN" --jq '.name // .login' 2>/dev/null)"
  LIC="$(gh api "licenses/$LICENSE_ID" --jq .body 2>/dev/null)"
  if [ -z "$LIC" ]; then
    echo "  FAILED: unknown license id '$LICENSE_ID' (see: gh api licenses --jq '.[].key')"
    FAILED=$((FAILED + 1))
  else
    LIC=${LIC//\[year\]/$(date +%Y)}
    LIC=${LIC//\[fullname\]/$HOLDER}
    put_file LICENSE "$LIC"
  fi
fi

# Scorecard alerts that cannot be fixed on a new repo: dismiss as "won't fix"
if gh api "repos/$REPO/contents/.github/workflows/scorecard.yml" >/dev/null 2>&1; then
  echo
  echo "# Scorecard alerts that cannot be fixed on a new repo"
  UNFIXABLE='CodeReviewID MaintainedID FuzzingID CIIBestPracticesID SASTID'
  ALERTS="$(gh api "repos/$REPO/code-scanning/alerts?state=open&tool_name=Scorecard&per_page=100" --jq '.[] | [.number, .rule.id] | @tsv' 2>/dev/null)"
  if [ -z "$ALERTS" ]; then
    echo "(no open Scorecard alerts yet; they appear after the first Scorecard run, so run this again then)"
  else
    while IFS=$'\t' read -r num rule; do
      case " $UNFIXABLE " in
        *" $rule "*) run gh api -X PATCH "repos/$REPO/code-scanning/alerts/$num" -f state=dismissed -f "dismissed_reason=won't fix" -f dismissed_comment="Cannot be satisfied by a new or solo repo; reopen when it applies (supply-chain-audit)." ;;
        *) echo "= #$num $rule left open" ;;
      esac
    done <<< "$ALERTS"
  fi
fi

# Ruleset for the default branch: no deletion, no force-push, PR required, checks required, no bypass
echo
if [ -n "$CHECKS" ]; then
  EXISTING="$(gh api "repos/$REPO/rulesets" --jq '.[] | select(.name=="Protect default branch") | .id' 2>/dev/null)"
  REPORTED="$(gh api "repos/$REPO/commits/$BRANCH/check-runs?per_page=100" --jq '.check_runs[].name' 2>/dev/null)"
  MISSING=""
  for c in $(echo "$CHECKS" | tr ',' ' '); do
    echo "$REPORTED" | grep -qxF "$c" || MISSING="$MISSING $c"
  done
  if [ -n "$MISSING" ] && [ "$APPLY" = 1 ]; then
    echo "! skipped the ruleset: not reported on $BRANCH yet:$MISSING"
    echo "  Wait for the workflows to finish (gh run list -R $REPO), then run this again."
    FAILED=$((FAILED + 1))
  else
    [ -n "$MISSING" ] && echo "! not reported on $BRANCH yet:$MISSING (--apply would skip the ruleset)"
    [ "$HAS_CODEOWNERS" = false ] && echo "! no CODEOWNERS: the ruleset will not require code-owner review"
    CTX="$(echo "$CHECKS" | awk -F, '{for(i=1;i<=NF;i++){printf "%s{\"context\":\"%s\"}", (i>1?",":""), $i}}')"
    BODY="$(cat <<EOF
{
  "name": "Protect default branch",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [ { "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request" } ],
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request", "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": $HAS_CODEOWNERS,
        "require_last_push_approval": true,
        "required_review_thread_resolution": false } },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [ $CTX ] } }
  ]
}
EOF
)"
    if [ -n "$EXISTING" ]; then METHOD=PUT; URL="repos/$REPO/rulesets/$EXISTING"; VERB=updated; else METHOD=POST; URL="repos/$REPO/rulesets"; VERB=created; fi
    echo "+ gh api -X $METHOD $URL --input - <<< '<ruleset json>'"
    echo "$BODY"
    if [ "$APPLY" = 1 ]; then
      if ERR="$(echo "$BODY" | gh api -X "$METHOD" "$URL" --input - 2>&1)"; then
        echo "ruleset $VERB"
      else
        echo "  FAILED: $(printf '%s' "$ERR" | head -c 300)"
        FAILED=$((FAILED + 1))
      fi
    fi
  fi
else
  echo "(no --checks given: skipping the branch ruleset. After the workflows have run on $BRANCH: $0 $REPO --apply --checks default)"
fi

echo
if [ "$FAILED" -gt 0 ]; then
  echo "$FAILED step(s) failed, see FAILED lines above. Everything else was applied."
fi
echo "Still manual: LICENSE, secrets (gh secret set NAME --repo $REPO; GITLEAKS_LICENSE if the owner is an organization), build/release workflows, tag a release if the repo is an action."
[ "$FAILED" -eq 0 ]
