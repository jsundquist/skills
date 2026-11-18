# Golden path

An ordered way to set up and harden a GitHub repository. Each layer assumes the ones before it. Work through it top to bottom; every step can be done by hand with the commands and files shown.

Status: **draft**. All layers are written. On 2026-11-18 every layer was run against two throwaway public repositories on a personal account, one to find problems and a second, fresh one after the fixes. Steps marked "Not verified yet" are the ones that run did not reach.

## Scope and conventions

- A repository on a **personal account**, with one owner and at most a few collaborators. Organizations are out of scope for now.
- Account security (2FA, passkeys, personal tokens) is out of scope. This path assumes the accounts with access to the repo are secured.
- `(repo)` stands for `OWNER/REPO`; replace it, brackets included, before running a command. Commands use the [`gh` CLI](https://cli.github.com/), logged in as the owner.
- Each step has the same parts: **Why**, **Apply**, **Verify**, and where relevant **Make required** and **Skip when**.
- **Make required** means adding a status check to the ruleset. Only do it after the check has run successfully once, or every PR will wait for a check that never reports.

## The ladder

| Layer | Question | Written |
|---|---|---|
| 0. Repo setup | Is the repo created on purpose? | Yes |
| 1. Source integrity | Can a change skip the rules? | Yes |
| 2. Pipeline trust | Can CI itself be abused? | Yes |
| 3. Inputs | What comes into the repo? | Yes |
| 4. Code | Is what we wrote safe? | Yes |
| 5. Artifacts | Can we prove what we shipped? | Yes |
| 6. Response and drift | Do the controls stay on? | Yes |

## The review model

The ruleset in layer 1 requires a pull request but **zero approvals and no bypass**. A solo owner cannot approve their own work, so a required approval would only ever be skipped by an admin bypass. Instead, the rules apply to everyone including you, and **the required status checks are the review**. Every PR, yours and bots', merges when the checks are green. That is why the later layers each end with "make required": a check that is not required gates nothing.

A consequence: with no bypass, even the first workflow arrives through a PR, and the check is made required only after it has run once.

---

## Layer 0: Repo setup

The repo exists, with an initial commit (a README is enough). Nothing here needs code, workflows or dependencies.

### 0.1 Create the repo on purpose

**Why.** Visibility and the default branch are hard to reason about later if they were left at defaults.

**Apply.**

```bash
gh repo create OWNER/REPO --private --add-readme   # or --public
gh repo edit (repo) --default-branch main
```

If public, add a `LICENSE` (never chosen for you; pick one):

```bash
gh api licenses --jq '.[].spdx_id'                  # list the options
gh api licenses/mit --jq .body > LICENSE            # edit the copyright line, then commit
```

**Verify.**

```bash
gh repo view (repo) --json visibility,defaultBranchRef,licenseInfo
```

### 0.2 Turn off features you do not use

**Why.** Every enabled feature is surface you have to keep an eye on. A public wiki can be edited by others on some configurations, and projects add a place for content and access you did not plan for. Turn them on later if you need them.

**Apply.**

```bash
gh api -X PATCH repos/(repo) -F has_wiki=false -F has_projects=false
```

**Verify.**

```bash
gh api repos/(repo) --jq '{has_wiki, has_projects}'   # both false
```

### 0.3 Security policy and private vulnerability reporting

**Why.** Gives people a private place to report a problem, instead of a public issue.

**Apply.** Commit a `SECURITY.md` (replace `(repo)` and `main`):

```markdown
# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately: https://github.com/(repo)/security/advisories/new

Do not open a public issue for a suspected vulnerability.

## Supported versions

Only the latest release, or `main` if there are no releases, receives security fixes.
```

```bash
gh api -X PUT repos/(repo)/private-vulnerability-reporting
```

**Verify.**

```bash
gh api repos/(repo)/private-vulnerability-reporting --jq .enabled   # true
gh api repos/(repo)/contents/SECURITY.md --jq .path
```

### 0.4 CODEOWNERS

**Why.** Names who owns the code. It costs nothing now, and becomes a real review rule when you add a collaborator.

**Apply.** Commit `.github/CODEOWNERS`:

```
* @OWNER
```

**Verify.**

```bash
gh api repos/(repo)/contents/.github/CODEOWNERS --jq .path
```

### 0.5 You are the only writer

**Why.** A new repo should have no other writers. Checking now makes the check meaningful when you add someone later.

**Verify.**

```bash
gh api repos/(repo)/collaborators --jq '.[] | [.login, .role_name] | @tsv'   # only you, role admin
gh api repos/(repo)/invitations --jq '.[].invitee.login'                     # empty
```

**Skip when.** Never. It passes trivially on day one.

---

## Layer 1: Source integrity

**Needs.** Layer 0 (a repo with a default branch).

The default branch cannot be rewritten or deleted, and every change goes through a pull request. No required checks yet: none exist.

### 1.1 Ruleset on the default branch

**Why.** Protects history and routes every change through a PR, which is where checks run.

**Apply.**

```bash
gh api -X POST repos/(repo)/rulesets --input - <<'JSON'
{
  "name": "Protect default branch",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request", "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["squash"] } }
  ]
}
JSON
```

`bypass_actors` is empty on purpose: the rules apply to you too. From now on, change `main` only through a PR.

**Verify.**

```bash
gh api repos/(repo)/rulesets --jq '.[] | [.id, .name, .enforcement] | @tsv'
git push origin main      # from a clone: should be rejected
```

### 1.2 Squash merges only

**Why.** One PR becomes one commit on the default branch, so history matches the unit that was reviewed and checked, a revert undoes exactly one change, and the PR title becomes the Conventional Commits line that release notes are built from. Merge commits add noise and non-linear history. Rebase merges rewrite the commits that were tested in the PR.

The ruleset in 1.1 already limits the merge button to squash. This step turns the other methods off at the repo level too, so the setting is not only enforced in one place, and sets the squash commit to use the PR title and body.

**Apply.**

```bash
gh api -X PATCH repos/(repo) --silent \
  -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
  -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY
```

**Verify.**

```bash
gh api repos/(repo) --jq '{allow_squash_merge, allow_merge_commit, allow_rebase_merge, squash_merge_commit_title, squash_merge_commit_message}'
```

**Tradeoff.** If PR B is based on PR A, merging B into A first and then A into the default branch collapses B's history into A's commit. To keep B as its own commit, land A first, then rebase B onto the default branch (`git rebase --onto <default> <A's old tip> B`) before merging it.

### 1.3 Delete branches on merge

**Why.** Merged branches are noise and a small attack surface.

**Apply / Verify.**

```bash
gh api -X PATCH repos/(repo) --silent -F delete_branch_on_merge=true
gh api repos/(repo) --jq .delete_branch_on_merge
```

### 1.4 Recommended: signed commits

**Why.** Shows that commits came from you. Merges done in the GitHub web UI are signed by GitHub automatically, so the cost is low.

**Before you enable it.** The rule requires every commit on a pull request branch to have a verified signature, not only the merge commit. GitHub signs the squash commit it makes, but your own commits on the branch must be signed too, and commits made with the contents API are not. Without a signing key GitHub knows about, every PR is blocked ("not mergeable") with all checks green. Set up signing first:

1. Make a signing key and tell git to use it, for example an SSH key: `git config --global gpg.format ssh`, `git config --global user.signingkey ~/.ssh/KEY.pub`, `git config --global commit.gpgsign true`.
2. Add the same public key to your account as a **signing key**: Settings → SSH and GPG keys → New SSH key → Key type "Signing Key". It is separate from any authentication key you already have.
3. Commit something on a branch, push it, and check `gh api repos/(repo)/commits/BRANCH --jq .commit.verification` shows `"verified": true`.

**Apply.** Add the rule to the ruleset. This keeps every other rule and adds one:

```bash
ID=$(gh api repos/(repo)/rulesets --jq '.[] | select(.name=="Protect default branch") | .id')
gh api repos/(repo)/rulesets/$ID \
  | jq '{name, target, enforcement, bypass_actors, conditions,
         rules: (.rules | map(select(.type != "required_signatures")) + [{type: "required_signatures"}])}' \
  | gh api -X PUT repos/(repo)/rulesets/$ID --input -
```

**Verify.** Open a PR from a signed branch and confirm it merges. Open one with an unsigned commit and confirm it is blocked.

**Not verified yet.** The signing setup in steps 1 to 3 (no signing key was registered on the test account). The block it causes without one, and the `required_signatures` rule JSON, were verified.

**Skip when.** You commit from places where you cannot sign. Optional, not baseline.

---

## Layer 2: Pipeline trust

**Needs.** Layer 1 (workflows arrive through a PR, and the ruleset exists to make their checks required).

CI is what enforces every later layer, so it must not be the weak point.

### 2.1 Repository Actions settings, before the first workflow

**Why.** These apply to every workflow, including ones added later or by someone else.

**Apply.**

```bash
# Read-only token by default; Actions cannot approve PRs
gh api -X PUT repos/(repo)/actions/permissions/workflow \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false

# Require every action to be pinned to a full commit SHA
gh api -X PUT repos/(repo)/actions/permissions \
  -F enabled=true -f allowed_actions=all -F sha_pinning_required=true

# Hold every workflow run from a fork PR until you approve it
gh api -X PUT repos/(repo)/actions/permissions/fork-pr-contributor-approval \
  -f approval_policy=all_external_contributors
```

Fork PRs already run with a read-only token and no secrets. Approval stops a stranger from running arbitrary workflow code on your runners and minutes. It does not affect your own PRs or Dependabot's. The cost is one click per outside PR. Do this before the first workflow.

**Verify.**

```bash
gh api repos/(repo)/actions/permissions/workflow
gh api repos/(repo)/actions/permissions --jq .sha_pinning_required   # true
gh api repos/(repo)/actions/permissions/fork-pr-contributor-approval --jq .approval_policy   # all_external_contributors
```

### 2.2 Rules every workflow follows

**Why.** Most workflow vulnerabilities come from a few patterns. Following these makes the checks in 2.4 pass.

- Top-level `permissions: {}`; widen per job.
- Every action pinned to a full SHA, with a version comment.
- `persist-credentials: false` on every checkout.
- No `${{ }}` expressions inside `run:`; pass values through `env:`.
- Check `pull_request_target` usage by hand: it must never check out or run PR code.

**Verify.**

```bash
# Unpinned actions (prints offenders; run in a clone)
grep -rnE '^\s*-?\s*uses:' .github/workflows | grep -vE '(\./|docker://)' | grep -vE '@[0-9a-f]{40}'
```

### 2.3 Keep pins fresh: Dependabot for `github-actions`

**Why.** SHA pins never update on their own. Without this, they go stale and nobody notices. The 7-day cooldown keeps you off brand-new releases.

**Apply.** Commit `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    cooldown:
      default-days: 7
    groups:
      github-actions:
        patterns: ["*"]
        update-types: [minor, patch]
```

Add an entry with the same cooldown for each other ecosystem you add later (layer 3).

**Verify.**

```bash
gh api repos/(repo)/contents/.github/dependabot.yml --jq .content | base64 -d | grep -E 'package-ecosystem|default-days'
```

### 2.4 Lint the workflows: actionlint, then zizmor

**Why.** actionlint finds syntax and type mistakes. zizmor finds security problems such as injection, excess permissions and unpinned actions. Fix actionlint findings first, because zizmor on a broken workflow is noisy.

**Apply.** Commit `.github/workflows/workflow-lint.yml` in a PR. The SHAs below are the versions pinned when this was written; let Dependabot move them.

```yaml
name: workflow-lint

on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "17 5 * * 1" # Mondays at 05:17 UTC
  workflow_dispatch:

permissions: {}

concurrency:
  group: workflow-lint-${{ github.ref }}
  cancel-in-progress: true

jobs:
  actionlint:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: raven-actions/actionlint@3d39aea434753780c3b3d4a1a31c854b4dbf49d7 # v2.2.0

  zizmor:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: read # only needed for private repos
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: zizmorcore/zizmor-action@45d7276c9ca790aabd705e31ca99c6185c3e76dd # v0.8.1
        with:
          advanced-security: false
```

The two jobs run in parallel and are separate checks. Do not chain them with `needs:`: a skipped required check counts as passing.

**Verify.**

```bash
gh run list -R (repo) --workflow workflow-lint.yml --limit 3
gh pr checks PR_NUMBER -R (repo)
```

Merge the PR once both jobs are green.

### 2.5 Make both checks required

**Why.** Until now the ruleset has no checks. This is what turns the lint into a gate.

**Apply.** Update the ruleset in place. This replaces any existing `required_status_checks` rule, so list every check you want:

```bash
ID=$(gh api repos/(repo)/rulesets --jq '.[] | select(.name=="Protect default branch") | .id')
gh api repos/(repo)/rulesets/$ID \
  | jq '{name, target, enforcement, bypass_actors, conditions,
         rules: (.rules | map(select(.type != "required_status_checks"))
           + [{type: "required_status_checks", parameters: {
                strict_required_status_checks_policy: true,
                required_status_checks: [{context: "actionlint"}, {context: "zizmor"}]}}])}' \
  | gh api -X PUT repos/(repo)/rulesets/$ID --input -
```

**Verify.**

```bash
gh api repos/(repo)/rulesets/$ID --jq '.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context'
```

Open a PR that breaks a workflow on purpose; it should not be mergeable.

`strict_required_status_checks_policy: true` means a PR must be up to date with the default branch. When one PR merges, every other open PR shows `BEHIND` and cannot merge. Bring it up to date with `gh pr update-branch PR_NUMBER -R (repo)`; the checks run again on the new head. After pushing or updating a PR, wait about a minute: its workflows start some seconds after the push, and `gh pr checks` can say "no checks reported" until they do.

### 2.6 List what else can act on the repo

**Why.** A GitHub App or integration with write access acts like another collaborator, and it arrives with CI and bots. Dependabot is one.

**Verify.** Review it in the web UI: your account's Settings → Applications (installed GitHub Apps, and which repos each can reach), and the repo's Settings → Integrations. There is no script for this. The REST endpoints that list installations (`repos/(repo)/installation`, `user/installations`) need a GitHub App token and reject a normal `gh` login, so the drift script in 6.1 cannot check it.

---

## Layer 3: Inputs

**Needs.** Layer 2 (the checks below run in CI and become required, so the pipeline has to be trustworthy first).

**Scope.** Public repositories. Some of the GitHub features used here are free only for public repos.

What comes into the repo: secrets (by mistake), dependencies, and the tooling you install. Secrets come first because they can leak from the very first commit. The dependency steps wait until the first dependency exists.

**Adding a required check.** Used in several steps below. It appends one check to the ruleset and leaves the rest alone, and is safe to repeat. Set `CHECK` to the exact check name shown by `gh pr checks`, and only do it after the check has passed once.

```bash
CHECK=gitleaks
ID=$(gh api repos/(repo)/rulesets --jq '.[] | select(.name=="Protect default branch") | .id')
gh api repos/(repo)/rulesets/$ID \
  | jq --arg c "$CHECK" '{name, target, enforcement, bypass_actors, conditions,
      rules: (.rules | map(if .type == "required_status_checks"
        then .parameters.required_status_checks |= ((. + [{context: $c}]) | unique)
        else . end))}' \
  | gh api -X PUT repos/(repo)/rulesets/$ID --input -
```

If the ruleset has no `required_status_checks` rule yet, use the recipe in 2.5 first.

### 3.1 Repository security features

**Why.** Secret scanning finds known credential formats in the repo. Push protection blocks them before the push is accepted. Dependabot alerts tell you when a dependency has a known vulnerability, and security updates open the fix PR.

**Apply.**

```bash
gh api -X PATCH repos/(repo) --silent \
  -f 'security_and_analysis[secret_scanning][status]=enabled' \
  -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' \
  -f 'security_and_analysis[dependabot_security_updates][status]=enabled'
gh api -X PUT repos/(repo)/vulnerability-alerts
```

**Verify.**

```bash
gh api repos/(repo) --jq '.security_and_analysis'
gh api repos/(repo)/vulnerability-alerts -i | head -1      # HTTP 204 means on
```

The alerts setting can take a few seconds to show. A `404` right after the `PUT` is normal, so check again before assuming it failed.

### 3.2 gitleaks in CI

**Why.** GitHub's scanning knows provider-specific formats. gitleaks adds generic rules and scans the full history, not just new pushes.

**Apply.** Commit `.github/workflows/secrets.yml` in a PR:

```yaml
name: secrets

on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "41 5 * * 1" # Mondays at 05:41 UTC
  workflow_dispatch:

permissions: {}

concurrency:
  group: secrets-${{ github.ref }}
  cancel-in-progress: true

jobs:
  gitleaks:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0 # full history
          persist-credentials: false
      - uses: gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e # v3.0.0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Verify.**

```bash
gh run list -R (repo) --workflow secrets.yml --limit 3
```

**Make required.** After it passes once on the PR, use the "Adding a required check" recipe with `CHECK=gitleaks`.

**If it finds a secret.** The secret is already exposed. Revoke and rotate it first; rewriting history is secondary.

### 3.3 Recommended: a local pre-commit hook

**Why.** CI and push protection catch a secret after it has been pushed. A hook catches it before it enters history at all, which is the only point where nothing needs rotating.

**Not enforceable.** Hooks run on your machine, are installed per clone, and `git commit --no-verify` skips them. That is why this is recommended and not required: CI stays the gate, and the hook is fast feedback. The audit can only check that the config file is committed.

**Apply.** Commit `lefthook.yml` and install it in each clone:

```yaml
pre-commit:
  commands:
    gitleaks:
      skip:
        - run: "! command -v gitleaks"
      run: gitleaks git --pre-commit --staged --redact
```

```bash
brew install lefthook gitleaks        # or your platform's package manager
lefthook install
```

A missing tool is skipped silently so it never blocks a commit. Add the 2.4 linters here too if you want them locally: `actionlint {staged_files}` and `zizmor {staged_files}` on `.github/workflows/*.yml`.

**Verify.**

```bash
# In a clone: stage a fake token, confirm the hook rejects it, then remove it. Never commit or push it.
echo 'token = "ghp_R8kZ3mQ9xV2nL5wT7yB4cH6jD1fG0aS8eUpK"' > leak-test.txt
git add leak-test.txt && lefthook run pre-commit      # should fail
git restore --staged leak-test.txt && rm leak-test.txt
```

Use a realistic-looking fake. gitleaks ignores obvious placeholders: the well-known AWS documentation key `AKIAIOSFODNN7EXAMPLE` is on its allowlist, so the hook passes and proves nothing.

### 3.4 Lockfile committed and enforced

**Needs.** The first dependency.

**Why.** A lockfile makes installs repeatable. CI that installs with a command that fails when the lock is out of date stops a change that was never reviewed from slipping into the build.

**Apply.** Commit the lockfile, and use the strict install command in CI and Dockerfiles:

| Tool | Strict install |
|---|---|
| npm | `npm ci` |
| pnpm | `pnpm install --frozen-lockfile` |
| yarn 2+ | `yarn install --immutable` |
| uv | `uv sync --frozen` (or `--locked`) |
| pip | requirements with hashes, `pip install --require-hashes` |

**Verify.**

```bash
git ls-files | grep -E '(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|uv\.lock)$'
grep -rnE 'npm install|pnpm install($| [^-])' .github/workflows Dockerfile* 2>/dev/null   # should print nothing
```

**Skip when.** No dependencies yet.

### 3.5 Dependabot for every ecosystem

**Needs.** 2.3 (the `github-actions` entry already exists).

**Why.** An ecosystem with no entry is never updated. The 7-day cooldown keeps you off brand-new releases, which is when most malicious versions are caught and pulled.

**Apply.** For each ecosystem in the repo, add an entry like the `github-actions` one from 2.3, with the same cooldown. Example for npm:

```yaml
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
    cooldown:
      default-days: 7
    groups:
      npm-minor-patch:
        patterns: ["*"]
        update-types: [minor, patch]
```

Majors stay out of the group so each gets its own PR.

To catch an ecosystem you forgot, add the `dependabot-coverage` workflow and script from the [jsundquist/skills](https://github.com/jsundquist/skills) repository: [`.github/workflows/dependabot-coverage.yml`](https://github.com/jsundquist/skills/blob/main/.github/workflows/dependabot-coverage.yml) and [`.github/scripts/check-dependabot-coverage.sh`](https://github.com/jsundquist/skills/blob/main/.github/scripts/check-dependabot-coverage.sh). Copy both files into your repo. It fails when a manifest has no Dependabot entry, or an entry has no cooldown, and it was verified to fail on a `Dockerfile` with no `docker` entry.

**Verify.**

```bash
gh api repos/(repo)/contents/.github/dependabot.yml --jq .content | base64 -d | grep -E 'package-ecosystem|default-days'
```

**Make required.** `dependabot-coverage`, once it has passed.

**Skip when.** The only ecosystem is `github-actions`.

### 3.6 Vulnerability scanning with OSV-Scanner

**Needs.** A lockfile (3.4).

**Why.** One tool that reads every lockfile in the repo, whatever the ecosystem, instead of a separate audit command per stack. It runs in two modes: a pull-request scan that fails only on vulnerabilities the PR introduces, and a full scan on push and on a weekly schedule, because new CVEs appear without any commit.

**Apply.** Commit two workflows in a PR. Both call Google's reusable workflows, pinned to the commit for `v2.7.0`.

`.github/workflows/osv-scanner-pr.yml`:

```yaml
name: osv-scanner-pr

on:
  pull_request:
    branches: [main]
  merge_group:
    branches: [main]

permissions: {}

jobs:
  scan-pr:
    permissions:
      actions: read
      security-events: write # upload results to the Security tab
      contents: read
    uses: google/osv-scanner-action/.github/workflows/osv-scanner-reusable-pr.yml@b1d267aea5211fa648d9d442fa64b90dbdcbdd36 # v2.7.0
```

`.github/workflows/osv-scanner-scheduled.yml`:

```yaml
name: osv-scanner-scheduled

on:
  schedule:
    - cron: "17 6 * * 1" # Mondays at 06:17 UTC
  push:
    branches: [main]

permissions: {}

jobs:
  scan-scheduled:
    permissions:
      actions: read
      security-events: write
      contents: read
    uses: google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml@b1d267aea5211fa648d9d442fa64b90dbdcbdd36 # v2.7.0
```

**Why two files.** The two scans fail for different reasons. The pull-request scan fails only on vulnerabilities the PR introduces, so it can safely be a required check. The full scan fails on any known vulnerability in the repo, including old ones. If it were required, a single newly published CVE in an existing dependency would block every unrelated PR. Kept separate, a red scheduled run means "the repo has a known vulnerability", not "this change broke something". Putting both jobs in one file with `if:` conditions on the event also works, and the choice is about readability, not correctness.

**Verify.**

```bash
gh run list -R (repo) --workflow osv-scanner-pr.yml --limit 3
gh pr checks PR_NUMBER -R (repo)          # note the exact check name
```

**Make required.** The pull-request scan, using the exact name from `gh pr checks`. Called workflows are named `<caller job> / <called job>`, so confirm it and don't guess. The scheduled scan is not a PR check and is not made required; its failures show in the Security tab and the Actions list.

**Skip when.** No lockfile yet. Both workflows pass on a repo with nothing to scan, so adding them early does no harm, but they check nothing and the required check proves nothing. Add them with the first lockfile.

### 3.7 Install and build scripts

**Needs.** The first dependency.

**Why.** Package managers run a package's install scripts and accept a brand-new release by default. Turn both down.

| | Release-age cooldown | Install scripts |
|---|---|---|
| pnpm | `minimumReleaseAge` in `pnpm-workspace.yaml` (minutes) | `allowBuilds` lists the only packages allowed to run them |
| npm | `min-release-age=7` in `.npmrc` (days; npm 11.10+) | `ignore-scripts=true` in `.npmrc` |
| yarn 4 | `npmMinimalAgeGate: 7d` in `.yarnrc.yml` | `enableScripts: false` in `.yarnrc.yml` |
| uv | `exclude-newer` under `[tool.uv]`, such as `"7 days"` | not applicable |

Each setting was checked against the tool itself (npm 11.16, pnpm 11.21, yarn 4.18, uv 0.13). yarn's `npmMinimalAgeGate` needs **Yarn 4.10 or newer**; Yarn 4.9 stops with "Unrecognized or legacy configuration settings". pnpm silently ignores a key it does not know, so confirm with `pnpm config get minimumReleaseAge`. Other ecosystems get a row when someone uses them. The cooldown is not a complete defence: a compromised release that stays published longer than the cooldown still gets through.

**Skip when.** The ecosystem has no install scripts, or there are no dependencies.

### 3.8 Before adding a dependency

A checklist, not automation. Ask:

- Who maintains it, and is it still maintained?
- How old is the release you would install?
- Does it run install scripts?
- Is there a smaller alternative, or could you write the few lines yourself?

### 3.9 Agent tooling is a dependency too (emerging)

Skills, MCP servers, plugins and agent config you install run with your permissions. The practices here are newer and less settled than the rest of this layer.

- Pin an MCP server or plugin to a version or commit, not "latest".
- Read a third-party skill before installing it. A scanner such as NVIDIA's SkillSpector is meant for this; check what it actually covers before relying on it.
- Review committed agent config like code: `.claude/settings.json` hooks, `CLAUDE.md`, `AGENTS.md`. A hook runs commands, and instructions steer an agent.
- In CI, give any agent the least permissions it needs, and treat issue, PR and comment text as untrusted input.

**Verify.**

```bash
git ls-files '.claude' 'CLAUDE.md' 'AGENTS.md' '.mcp.json'     # what is committed, for review
```

### Optional additions

These overlap with the baseline above. Add one only if you have a reason.

- **TruffleHog** alongside gitleaks. Its difference is checking whether a found credential is still valid, so `--only-verified` shows live secrets only. A second scanner means a second set of rules to maintain. Pinned to the commit for `v3.99.8`:

  ```yaml
  jobs:
    trufflehog:
      runs-on: ubuntu-latest
      permissions:
        contents: read
      steps:
        - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
          with:
            fetch-depth: 0
            persist-credentials: false
        - uses: trufflesecurity/trufflehog@ea68ca03c865c5f324e86e849ced20ed3cf9dbbb # v3.99.8
          with:
            extra_args: --only-verified
  ```

- **`dependency-review-action`** on pull requests. The OSV pull-request scan already covers new vulnerabilities, so the unique value here is licence policy (deny lists) and GitHub's own advisory data. Add it if you care about licences. `.github/workflows/dependency-review.yml`, pinned to the commit for `v5.0.1`:

  ```yaml
  name: dependency-review

  on:
    pull_request:

  permissions: {}

  jobs:
    dependency-review:
      runs-on: ubuntu-latest
      permissions:
        contents: read
      steps:
        - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
          with:
            persist-credentials: false
        - uses: actions/dependency-review-action@bbc44d14a204704ccc493733616cd1e93a0321ec # v5.0.1
  ```
- **Per-stack audit tools** (`npm audit`, `pip-audit`). Only if OSV-Scanner misses something for an ecosystem you use.

---

## Layer 4: Code

**Needs.** Layer 2 (CI is trustworthy, including the fork-PR approval in 2.1) and layer 1 (the ruleset exists).

**Scope.** Public repositories. CodeQL is free for public repos.

Is the code you wrote safe? A deterministic scanner gates the merge, and an occasional manual agent audit goes deeper. Build, lint and test workflows are not covered here: they depend on the language, and this path stays language-independent.

### 4.1 CodeQL, default setup

**Why.** GitHub maintains a large query library and runs dataflow analysis, such as user input reaching a dangerous call across several functions. It is the baseline scanner for the code itself. Default setup is one API call, with no workflow file to pin or maintain.

**Apply.**

```bash
gh api -X PATCH repos/(repo)/code-scanning/default-setup \
  -f state=configured -f query_suite=default
```

GitHub detects the languages and starts a first run on the default branch. Supported languages include `actions`, so a repo whose only code is workflows is still scanned. The `languages` field stays empty until that first run has finished, so wait for it before concluding that nothing was detected.

**Verify.**

```bash
gh api repos/(repo)/code-scanning/default-setup --jq '{state, languages, query_suite}'
gh api repos/(repo)/code-scanning/analyses --jq '.[0] | {tool: .tool.name, ref, created_at}'   # after the first run finishes
```

**Make required.** The `code_scanning` ruleset rule blocks on alert severity and not on a check name. Default setup's check names are generated by GitHub and vary by language, so a named check would be fragile. This rule needs a completed analysis on the default branch, so wait for the first run (Verify, above). It replaces any existing `code_scanning` rule:

```bash
ID=$(gh api repos/(repo)/rulesets --jq '.[] | select(.name=="Protect default branch") | .id')
gh api repos/(repo)/rulesets/$ID \
  | jq '{name, target, enforcement, bypass_actors, conditions,
         rules: (.rules | map(select(.type != "code_scanning"))
           + [{type: "code_scanning", parameters: {code_scanning_tools: [
                {tool: "CodeQL", alerts_threshold: "errors", security_alerts_threshold: "high_or_higher"}]}}])}' \
  | gh api -X PUT repos/(repo)/rulesets/$ID --input -
```

`high_or_higher` blocks a PR that introduces a high or critical security alert. Lower the threshold to `medium_or_higher` for a stricter gate.

**When the repo gains a language.** Default setup fixes its language list when you configure it. Adding JavaScript or Python to a repo that started with only workflows does not add it: PRs kept being analyzed as `actions` only, even after the merge. Run the same `PATCH` again and it detects the languages afresh (the list then showed actions, javascript-typescript and python).

**Skip when.** The repo has no language CodeQL supports (after the first run finishes, `languages` stays empty).

**Verified.** The `PATCH`, the `code_scanning` rule JSON and the gate. A PR whose only fault was an `eval` of a query parameter failed only the `CodeQL` check, with a critical `js/code-injection` alert, and could not merge. CodeQL's `actions` queries did not flag `run: echo "${{ github.event.issue.title }}"` under an `issues:` trigger; they flagged `pull_request_target` with an untrusted checkout. Do not rely on CodeQL alone for workflow injection: that is what zizmor in 2.4 is for.

### 4.2 Deep agent audit (optional, manual, occasional)

**Why.** A one-off, multi-phase audit by a coding agent that tries to disprove its own findings. It is far more thorough than a per-PR review and much too slow and costly to run on every PR. Run it before a release or after a large change.

This is [Cloudflare's security-audit-skill](https://github.com/cloudflare/security-audit-skill) (MIT licensed, actively maintained when checked). It is a third-party skill, so layer 3.9 applies: pin it, and read it before you install it.

**Apply.** Install the skill, then start your coding agent in the repo and ask for a security audit.

```bash
git clone https://github.com/cloudflare/security-audit-skill
git -C security-audit-skill rev-parse HEAD     # note the commit you reviewed
```

Read it, then install **from that clone**, not with the README's `npx skills add https://github.com/cloudflare/security-audit-skill --skill security-audit`: that fetches whatever the repository holds today, not the commit you reviewed. Copy the skill directory instead, for example `cp -R security-audit-skill/skills/security-audit ~/.claude/skills/`. By default it writes reports outside the repo, under `~/security-audit-skill/<repo-name>/run-<N>`. It asks for an OS-enforced sandbox before running target code; without one it records leads as `needs_validation` and does not execute them.

Checked: the repo exists, is MIT licensed, and had a commit on 2026-09-14. The skill that was already installed matched the reviewed clone file for file (`diff -r` was empty).

**Run once, on a small test repo (2026-11-18).** The audit ran to completion on about 25 files and wrote `REPORT.md`, `FINDINGS-DETAIL.md`, `NEEDS-VALIDATION.md`, `findings.json`, `coverage-ledger.json` and `architecture.md` under `~/security-audit-skill/<repo-name>/run-1/`, and both of its validators passed. Notes for the next run:

- It defaults to the `standard` profile. For a small repo you can ask for `quick`, which is one hunter wave and one critic and is explicitly a partial pass. Our `quick` run used 3 hunters and 1 critic, took a few minutes, and found nothing, while the critic still listed four coverage gaps and two reassignments that `quick` defers. Treat a clean `quick` result as "nothing found in what was reviewed", and run `standard` before a release.
- A `standard` run followed on the same repo, using the first run as prior-run input. It took 16 agents across two hunter waves, three critics and seven verifiers, found no confirmed vulnerability, and produced three `needs_validation` records and one rejected record. All three open records were about hosted settings or third-party tool behaviour the repo cannot show, and the last critic still reported gaps, so it stopped at a cap and says so. Expect that: the critic loop does not converge on a small repo, so decide a cap up front. The cost is real (about 65,000 to 100,000 tokens per agent), so run `standard` before a release, not on every change.
- With no OS-enforced sandbox it reads source only and executes nothing, so anything needing execution or a hosted setting becomes `needs_validation`. It cannot see rulesets, environments or fork-PR approval; those come from the drift script in 6.1.
- The skill writes into `~/security-audit-skill/`, outside the repo, so the report is not committed by accident.

**Verify.** The run produces `REPORT.md` and `findings.json`. Triage the confirmed findings, and fix them in a PR.

**Make required.** Not applicable. It is manual and has no check.

**Skip when.** The repo is small or docs-only, or you do not want to spend the tokens.

### Optional additions

- **Semgrep.** A pattern-based scanner you teach with your own rules, such as "never call `fetch` without `safeFetch`". Use it only when you have a house rule you keep wanting to enforce, because CodeQL already covers the generic bugs. The CLI is open source and needs no account. Example rule, `.semgrep/no-shell-true.yml`:

  ```yaml
  rules:
    - id: no-shell-true
      languages: [python]
      severity: ERROR
      message: Do not run subprocesses with shell=True
      pattern: subprocess.$FUNC(..., shell=True, ...)
  ```

  `.github/workflows/semgrep.yml`:

  ```yaml
  name: semgrep

  on:
    pull_request:
    push:
      branches: [main]
    workflow_dispatch:

  permissions: {}

  concurrency:
    group: semgrep-${{ github.ref }}
    cancel-in-progress: true

  jobs:
    semgrep:
      runs-on: ubuntu-latest
      permissions:
        contents: read
      steps:
        - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
          with:
            persist-credentials: false
        - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
          with:
            python-version: "3.13"
        - run: pip install semgrep==1.184.0
        - run: semgrep scan --config .semgrep/ --error
  ```

  Make `semgrep` required with the "Adding a required check" recipe in layer 3, once it has passed. The pinned version is the one current when this was written. Bump it deliberately, and keep it out of Dependabot's reach unless you add `pip` coverage.

  Pin the Python minor version, as above. With `"3.x"` the runner picked Python 3.15, and `semgrep-core` crashed (exit -11) with "Nothing to scan". Scorecard (6.4) also marks `pip install semgrep==1.184.0` as "not pinned by hash" and takes a point off Pinned-Dependencies; accept that, or install from a hashed requirements file with `pip install --require-hashes`.

---

## Layer 5: Artifacts

**Needs.** Layers 2 and 3 (a trusted pipeline, and dependencies already scanned).

**Scope.** Public repositories. Attestations are free for public repos and can be verified by anyone. The signing certificate and workflow identity are written to a public transparency log, which is fine for a public repo.

Can you prove what you shipped? This layer covers release tags, immutable releases, build provenance and verification, for any repo that cuts releases, whether the release is source only or carries built files. Package registries (npm, PyPI) and container images are stack-specific and live in their own documents. For a container image, see [containers.md](containers.md).

### 5.0 Does this repo cut releases?

A release is a tag or GitHub release that someone else consumes, with or without attached files. If you never cut one, **skip the whole layer**. It is a "skip when", not a gap. Come back before the first release.

Release-time jobs run on a tag, not on a pull request, so **nothing in this layer is added to the ruleset's required checks**. The checks that gate a merge (layers 2 to 4) already ran.

### 5.1 Protect release tags

**Why.** A release tag that can be moved or deleted lets someone swap what a version means. This was moved here from layer 1: tags are only a risk once you ship.

**Apply.**

```bash
gh api -X POST repos/(repo)/rulesets --input - <<'JSON'
{
  "name": "Protect release tags",
  "target": "tag",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": { "ref_name": { "include": ["refs/tags/v*.*.*"], "exclude": [] } },
  "rules": [ { "type": "deletion" }, { "type": "non_fast_forward" } ]
}
JSON
```

A tag matching `v*.*.*` can no longer be deleted or moved. A moving tag such as `v1` is not matched, on purpose, for consumers of an Action or library you publish who want automatic patches.

**A pushed tag is permanent.** If the release workflow (5.4) fails after you push a tag, you cannot delete the tag and push it again. Fix the workflow in a PR and release the next patch version. A failed run costs a version number, even before any immutable release exists.

**Verify.**

```bash
gh api repos/(repo)/rulesets --jq '.[] | select(.target=="tag") | [.id, .name, .enforcement] | @tsv'
git push origin :refs/tags/v0.0.1    # after a test tag exists: should be rejected
```

**Make required.** Not applicable: a tag rule has no status checks.

**Verified.** The ruleset JSON is accepted, and both deleting and moving `v0.1.0` were rejected (`GH013: Repository rule violations`).

### 5.2 Publish with short-lived credentials

**Why.** A long-lived token in a secret can leak and keeps working. The workflow's own `GITHUB_TOKEN` is created for each run and expires with it.

**Apply.** Give the one job that creates the release `contents: write` and nothing wider, and use `GITHUB_TOKEN` (the release job in 5.4 does). Do not create a personal access token for publishing. When you publish to a package registry, use its **trusted publishing / OIDC** option instead of a stored token. That setup differs per registry and belongs in that stack's document.

**Verify.**

```bash
gh secret list -R (repo)                                          # no publishing tokens
grep -rn 'secrets\.' .github/workflows | grep -v GITHUB_TOKEN    # should print nothing for the release
```

**Skip when.** You publish nothing.

### 5.3 Immutable releases

**Why.** Once a release is published, its tag and its files can no longer be changed or deleted. That closes the swap-after-the-fact attack for source-only releases too, with no build step. Creating an immutable release also generates a **release attestation** recording the tag, commit and files, which anyone can verify.

**Apply.** In the web UI: Settings → Releases → **Enable release immutability**. Or with the API:

```bash
gh api -X PUT repos/(repo)/immutable-releases
```

This applies only to releases created afterwards.

**What it changes for you**
- You cannot add or replace files after publishing. Create the release as a **draft**, attach every file, then publish it. The workflow in 5.4 does this.
- A tag name used by an immutable release can never be reused, even if you delete the release. A mistake costs a version number, so fix forward with a new patch release.
- The title, the notes and the pre-release or latest flags can still be edited.
- Because of the draft step, cut the release by pushing a tag, as in 5.4. `gh release create` without `--draft` would publish at once, with no files.

**Verify.**

```bash
gh api repos/(repo)/immutable-releases --jq .enabled      # true; a 404 means off
gh release verify v0.1.0 -R (repo)                         # after the first release
```

**Make required.** Not applicable.

**Verified.** `PUT repos/(repo)/immutable-releases` works on a personal public repo and `GET` returns `{"enabled": true, "enforced_by_owner": false}`. Uploading to a published release failed with `HTTP 400`, and creating a release on the tag of a deleted immutable release failed with `tag_name was used by an immutable release`. `gh release verify` does not cover the auto-generated source zip and tarball.

**Skip when.** 5.0 says to skip the layer.

### 5.4 Release workflow with build provenance

**Needs.** A release that carries built files (a binary, an archive). For a source-only release, enable 5.3 and publish with `gh release create v0.1.0 --draft --generate-notes` followed by `gh release edit v0.1.0 --draft=false`. Skip the rest of this step.

**Why.** Immutability fixes the files in place. **Provenance** proves where they came from: which workflow, in which repo, built them from which commit. GitHub signs it with Sigstore as part of the attestation, so there is no separate signing step. Build, attest and release run as separate jobs so that only the attest job can request a signing identity and only the release job can write to the repo.

**Apply.** Commit `.github/workflows/release.yml` in a PR. Replace the Build step with your own build. It must write the files to ship into `dist/`. As written, the step fails on purpose until you do.

```yaml
name: release

on:
  push:
    tags: ["v*.*.*"]

permissions: {}

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Build
        run: |
          echo "Replace this step with your build. Write the files to ship into dist/." >&2
          exit 1
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: dist
          path: dist/

  attest:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      id-token: write # request the signing certificate
      attestations: write
    steps:
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          name: dist
          path: dist
      - uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2
        with:
          subject-path: dist/*

  release:
    needs: [build, attest]
    runs-on: ubuntu-latest
    permissions:
      contents: write # create the release
    steps:
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          name: dist
          path: dist
      - name: Create the draft, attach the files, publish
        env:
          GH_TOKEN: ${{ github.token }}
          REPO: ${{ github.repository }}
          TAG: ${{ github.ref_name }}
        run: |
          gh release create "$TAG" dist/* --repo "$REPO" --verify-tag --draft --generate-notes --title "$TAG"
          gh release edit "$TAG" --repo "$REPO" --draft=false
```

Notes:

- **This is the one place `needs:` is correct.** The rule against chaining applies to required checks, where a skipped job counts as passing. These jobs are not required checks, and each depends on the one before it. A failed build stops the release.
- Every action is pinned to a full SHA with a version comment, so Dependabot moves them.

**Cut a release.** Push a tag from a clone, on the commit you want to release:

```bash
git switch main && git pull
git tag v0.1.0 && git push origin v0.1.0
```

**Verify.**

```bash
gh run list -R (repo) --workflow release.yml --limit 3
gh release view v0.1.0 -R (repo)
```

**Make required.** Not applicable: it runs on a tag.

**Verified.** Run end to end on a tag with immutable releases on: build, attest and release all passed, the release was published as immutable with both files attached, and 5.5's commands all passed. With the SBOM steps from 5.6 added as described there, it passed on the first try.

**Skip when.** The release has no built files.

### 5.5 Verify before you use it

**Why.** An attestation only matters if something checks it. Verify the release and its files before you use or hand them on.

**Apply / Verify.** From a clone of the repo, with a downloaded file:

```bash
gh release verify v0.1.0 -R (repo)                 # the tag, commit and files match the release attestation
gh release verify-asset v0.1.0 ./my-asset.tar.gz   # this exact file is part of that release
gh attestation verify ./my-asset.tar.gz --repo (repo) \
  --signer-workflow (repo)/.github/workflows/release.yml \
  --predicate-type https://slsa.dev/provenance/v1    # built by the release workflow in 5.4
```

The exit code is the answer: 0 means verified. `gh attestation verify` prints nothing on success when its output is not a terminal, and a file with no attestation fails with an `HTTP 404` message, not a "verification failed" one.

**Skip when.** You do not consume your own releases. Anyone else who does can run the same commands.

### 5.6 Optional: SBOM

**Why.** A list of what went into the release, signed to the files, so you can answer "does this release contain package X?" later.

**Apply.** Change the `attest` job in 5.4 in two places. Syft reads the repo at the tagged commit. Pinned to the commit for `v0.24.3`.

First, add these two steps at the **start** of the job, before `download-artifact`. `actions/checkout` cleans the workspace, so a checkout after the download would delete `dist/` and the attest step would fail with "Could not find subject at path dist/*":

```yaml
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: anchore/sbom-action@66cbf4bc1f1c0d2edc94016e65bc221b6bb0ad6c # v0.24.3
        with:
          path: .
          format: cyclonedx-json
          output-file: sbom.cdx.json
          upload-artifact: false
```

Then add this step at the **end** of the job, after the existing `actions/attest` step:

```yaml
      - uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2
        with:
          subject-path: dist/*
          sbom-path: sbom.cdx.json
```

**Verify.**

```bash
gh attestation verify ./my-asset.tar.gz --repo (repo) --predicate-type https://cyclonedx.org/bom
```

**Skip when.** You do not need to answer "what is inside this release?". Optional, not baseline.

---

## Layer 6: Response and drift

**Needs.** Layers 0 to 5. Each step re-checks something an earlier layer set up, so a step does not apply if its layer was skipped.

**Scope.** Public repositories.

Controls get switched off, expire, or quietly stop running. This layer re-reads what the earlier layers set, and says what to do when something goes wrong.

### 6.1 Drift check: a script you run by hand

**Why.** Every setting in layers 0 to 5 can change without a commit: someone with admin access edits it in the web UI, a feature gets switched off, a collaborator is added. This script re-reads them and prints what no longer matches this document.

**Apply.** Commit `.github/scripts/drift-check.sh`. It needs `gh` and `jq`, and a login with admin access to the repo.

```bash
#!/usr/bin/env bash
# Re-check the settings the golden path sets. Usage: drift-check.sh OWNER/REPO
set -uo pipefail

repo="${1:?usage: drift-check.sh OWNER/REPO}"
failures=0

check() { # description, expected, actual
  if [ "$2" = "$3" ]; then
    echo "ok     $1"
  else
    echo "DRIFT  $1 (expected $2, got $3)"
    failures=$((failures + 1))
  fi
}

check_visible() { # like check, but skip when GitHub does not return the field to this token
  if [ "$3" = null ]; then
    echo "skip   $1 (not visible to this token)"
  else
    check "$@"
  fi
}

# Layer 0 and 1: repository settings
r=$(gh api "repos/$repo")
check "wiki off" false "$(jq .has_wiki <<<"$r")"
check "projects off" false "$(jq .has_projects <<<"$r")"
# GitHub returns these four only to a caller with push access, so a read-only token sees null
check_visible "squash merge on" true "$(jq .allow_squash_merge <<<"$r")"
check_visible "merge commits off" false "$(jq .allow_merge_commit <<<"$r")"
check_visible "rebase merge off" false "$(jq .allow_rebase_merge <<<"$r")"
check_visible "delete branch on merge" true "$(jq .delete_branch_on_merge <<<"$r")"

# Layer 3: security features
check "secret scanning" enabled "$(jq -r .security_and_analysis.secret_scanning.status <<<"$r")"
check "push protection" enabled "$(jq -r .security_and_analysis.secret_scanning_push_protection.status <<<"$r")"
check "dependabot security updates" enabled "$(jq -r .security_and_analysis.dependabot_security_updates.status <<<"$r")"
if gh api "repos/$repo/vulnerability-alerts" --silent 2>/dev/null; then
  check "dependabot alerts" on on
else
  check "dependabot alerts" on off
fi
check "private vulnerability reporting" true "$(gh api "repos/$repo/private-vulnerability-reporting" --jq .enabled 2>/dev/null || echo off)"

# Layer 2: Actions settings
check "default token read-only" read "$(gh api "repos/$repo/actions/permissions/workflow" --jq .default_workflow_permissions)"
check "actions cannot approve PRs" false "$(gh api "repos/$repo/actions/permissions/workflow" --jq .can_approve_pull_request_reviews)"
check "actions pinned to SHA" true "$(gh api "repos/$repo/actions/permissions" --jq .sha_pinning_required)"
check "fork PR approval" all_external_contributors "$(gh api "repos/$repo/actions/permissions/fork-pr-contributor-approval" --jq .approval_policy)"

# Layer 1 and 2: the branch ruleset
id=$(gh api "repos/$repo/rulesets" --jq '.[] | select(.name=="Protect default branch") | .id')
if [ -z "$id" ]; then
  echo "DRIFT  ruleset 'Protect default branch' (expected present, got missing)"
  failures=$((failures + 1))
else
  rj=$(gh api "repos/$repo/rulesets/$id")
  check "ruleset active" active "$(jq -r .enforcement <<<"$rj")"
  check "no bypass actors" 0 "$(jq '.bypass_actors | length' <<<"$rj")"
  for t in deletion non_fast_forward pull_request required_status_checks; do
    check "ruleset rule: $t" 1 "$(jq --arg t "$t" '[.rules[] | select(.type == $t)] | length' <<<"$rj")"
  done
  check "zero required approvals" 0 "$(jq '[.rules[] | select(.type=="pull_request") | .parameters.required_approving_review_count][0]' <<<"$rj")"
  check "squash is the only merge method" '["squash"]' "$(jq -c '[.rules[] | select(.type=="pull_request") | .parameters.allowed_merge_methods][0]' <<<"$rj")"
  echo "info   required checks: $(jq -r '[.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context] | join(", ")' <<<"$rj")"
fi

# Layer 0: nobody else has access
check "collaborators" 1 "$(gh api "repos/$repo/collaborators" --jq length)"
check "pending invitations" 0 "$(gh api "repos/$repo/invitations" --jq length)"
check "deploy keys" 0 "$(gh api "repos/$repo/keys" --jq length)"
check "webhooks" 0 "$(gh api "repos/$repo/hooks" --jq length)"
echo "info   repo secrets: $(gh api "repos/$repo/actions/secrets" --jq '[.secrets[].name] | join(", ")')"

# Layer 0 to 2: files that must exist
for f in SECURITY.md .github/CODEOWNERS .github/dependabot.yml; do
  if gh api "repos/$repo/contents/$f" --silent 2>/dev/null; then
    check "file $f" present present
  else
    check "file $f" present missing
  fi
done

# 6.3: workflows that stopped running
check "disabled workflows" 0 "$(gh api "repos/$repo/actions/workflows" --jq '[.workflows[] | select(.state != "active")] | length')"

echo
if [ "$failures" -eq 0 ]; then
  echo "No drift."
else
  echo "$failures check(s) drifted."
  exit 1
fi
```

The four merge-setting checks print `skip` when run with the read-only token from 6.2, because GitHub returns those fields only to callers with push access. The ruleset check on `allowed_merge_methods` still covers squash-only, and a run by hand as the repo owner checks all four.

It covers the settings in layers 0 to 3 and the 2.6 gap for collaborators, keys, webhooks and secrets. It does not list installed GitHub Apps: no API for that has been confirmed, so review Settings → GitHub Apps by hand. It does not check layer 4 or 5 settings that only exist when you use them (the `code_scanning` rule, the tag ruleset, immutable releases). Add a check for each you adopted.

**Verify.**

```bash
bash .github/scripts/drift-check.sh (repo)
```

Turn one setting off on purpose (for example `gh api -X PATCH repos/(repo) -F has_wiki=true`), run it, confirm it reports `DRIFT`, then turn it back.

**Make required.** Not applicable: it reads settings, not code.

**Verified.** Run as the repo owner it reported no drift, and with four settings changed on purpose (wiki, merge commits, private vulnerability reporting, fork PR approval) it reported all four. Every field name it reads exists, including `squash_merge_commit_*`, `fork-pr-contributor-approval` and `allowed_merge_methods`.

### 6.2 Drift check: scheduled

**Why.** A script you run by hand gets run when you remember. This runs it every week and goes red when something has drifted.

**Why a token.** The checks in 6.1 need admin read access. The workflow's `GITHUB_TOKEN` cannot be given that, so the workflow uses a **fine-grained personal access token** scoped to this one repo with read-only permissions. That is a secret worth protecting, so it lives in a GitHub **environment** that only the default branch can use. A pull request branch cannot read it.

**Apply.**

1. Create the token in the web UI (it cannot be created through the API): Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token.
   - Resource owner: you. Repository access: **only** this repo. Expiration: 90 days.
   - Repository permissions, all read-only: **Administration**, **Secrets**, **Webhooks**, **Contents**. Metadata is read-only by default.
   - If a check later reports a 403, the token is missing a permission. Add the one it names.
2. Create the environment, restrict it to the default branch, and store the token in it:

```bash
gh api -X PUT repos/(repo)/environments/drift --input - <<'JSON'
{ "deployment_branch_policy": { "protected_branches": false, "custom_branch_policies": true } }
JSON
gh api -X POST repos/(repo)/environments/drift/deployment-branch-policies -f name=main -f type=branch
gh secret set DRIFT_TOKEN --env drift -R (repo)
```

3. Commit `.github/workflows/drift.yml` in a PR:

```yaml
name: drift

on:
  schedule:
    - cron: "23 6 * * 1" # Mondays at 06:23 UTC
  workflow_dispatch:

permissions: {}

jobs:
  drift:
    runs-on: ubuntu-latest
    environment: drift
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Check for drift
        env:
          GH_TOKEN: ${{ secrets.DRIFT_TOKEN }}
          REPO: ${{ github.repository }}
        run: bash .github/scripts/drift-check.sh "$REPO"
```

The workflow only runs on a schedule or by hand, never on a pull request, and it is not made required.

**Verify.**

```bash
gh workflow run drift.yml -R (repo)
gh run list -R (repo) --workflow drift.yml --limit 3
```

**When the token expires** the run fails with an authentication error. That is the reminder to rotate it: create a new token, run `gh secret set DRIFT_TOKEN --env drift -R (repo)`, and delete the old token in the web UI.

**Make required.** Not applicable.

**Not verified yet.** The environment API calls, and the exact permission set the token needs.

### 6.3 Scheduled workflows have not gone quiet

**Why.** GitHub disables scheduled workflows in a public repo after 60 days with no repository activity. The weekly secret scan, vulnerability scan and workflow lint would silently stop, and every earlier check would still look green.

**Apply / Verify.** The drift script in 6.1 already counts them. By hand:

```bash
gh api repos/(repo)/actions/workflows --jq '.workflows[] | select(.state != "active") | [.name, .state] | @tsv'
gh workflow enable "WORKFLOW NAME" -R (repo)      # re-enable one that was switched off
```

A workflow switched off for inactivity shows `disabled_inactivity`. Merged Dependabot PRs and your own commits count as activity, so a repo that is looked after rarely hits this. A repo you leave alone for two months does.

**Skip when.** The repo has no scheduled workflows.

### 6.4 OpenSSF Scorecard

**Why.** A weekly score for how well the repo follows common security practices: branch protection, pinned dependencies, token permissions, a security policy, a code scanner. It looks at the controls in layers 0 to 5 from the outside, as an independent report card. It does not read your code for bugs.

**Apply.** Commit `.github/workflows/scorecard.yml` in a PR:

```yaml
name: scorecard

on:
  branch_protection_rule:
  push:
    branches: [main]
  schedule:
    - cron: "41 6 * * 2" # Tuesdays at 06:41 UTC
  workflow_dispatch:

permissions: {}

jobs:
  analysis:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: read
      security-events: write # upload results to the Security tab
      id-token: write # publish results (public repos only)
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: ossf/scorecard-action@fa7117db83c52d787ae5a89f350999701505d78e # v2.5.0
        with:
          results_file: results.sarif
          results_format: sarif
          publish_results: true
      - uses: github/codeql-action/upload-sarif@33d7b85da1a04171e211befe2c739303b9a4c066 # v4.39.3
        with:
          sarif_file: results.sarif
```

**Read the score as a report, not a target.** On a new test repo with all of layers 0 to 5 in place it scored about 6 out of 10. Code-Review scores 0 (zero approvals), Maintained scores 0 for a repo under 90 days old, and Fuzzing, CII-Best-Practices and Contributors score 0. Signed-Releases also scores 0, even with attestations and immutable releases: it looks for signature or provenance files attached to the release (such as `*.intoto.jsonl`), and does not read GitHub attestations. Some checks cannot be perfect here by design. The review checks expect an approving human, and this path uses zero approvals. Some branch protection checks need a token with admin access that this workflow does not have. Look for checks that dropped, not for a score of 10.

**Verify.**

```bash
gh run list -R (repo) --workflow scorecard.yml --limit 3
```

The score is on the run's summary, in the Security tab, and at `https://scorecard.dev/viewer/?uri=github.com/(repo)`.

**Make required.** Not applicable: it runs on a schedule and on pushes, and its alerts are not PR checks.

**Verified.** The action SHAs resolve and the workflow runs. See the score notes above for what scores low and why.

### 6.5 Alerts: where they arrive, and how often you look

**Why.** Dependabot, code scanning and secret scanning only help if someone reads what they report.

**Apply.** In the web UI under your account's notification settings, make sure alerts for Dependabot, code scanning and secret scanning reach you (email or web). That is an account setting, so it is outside the scope of this path. Then pick a cadence. Weekly is enough for a small repo.

**Verify.** The counts of open alerts, any of which is a to-do:

```bash
gh api repos/(repo)/dependabot/alerts --jq '[.[] | select(.state=="open")] | length'
gh api 'repos/(repo)/code-scanning/alerts?state=open&tool_name=CodeQL' --jq length
gh api 'repos/(repo)/secret-scanning/alerts?state=open' --jq length
```

The code-scanning count is filtered to CodeQL on purpose. The Scorecard workflow in 6.4 uploads its results to code scanning, so with it enabled there are always open Scorecard alerts, some marked high (such as Code-Review, which this path cannot satisfy with zero approvals). Read those in the Security tab as a report, not as a to-do count.

### 6.6 Runbook: when something goes wrong

Short on purpose. Each row is the first things to do, not the whole response. Expand it the first time one of these actually happens.

| If | Do this |
|---|---|
| **A secret leaked** (gitleaks, push protection or a secret-scanning alert) | 1. Revoke or rotate it at the provider. Do this first. 2. Replace it where it is used: `gh secret set NAME -R (repo)`. 3. Close the alert: `gh api -X PATCH repos/(repo)/secret-scanning/alerts/N -f state=resolved -f resolution=revoked`. 4. Rewriting history is secondary and does not un-leak it. |
| **A dependency was compromised** | 1. Pin back to a good version or remove it, and regenerate the lockfile. 2. List runs that installed it: `gh run list -R (repo) --limit 50`. 3. Rotate every secret those runs could read. |
| **A workflow or action was compromised** | 1. Pin the action to a known-good SHA in a PR. 2. Rotate every secret the affected workflows could read. 3. Clear the Actions caches: `gh cache delete --all -R (repo)` (exits 1 with "No caches to delete" when there are none). |
| **A release is bad** | Immutable releases cannot be edited or re-tagged. Mark it a pre-release in the notes, publish a fixed patch release, and say why in the notes. A container image is covered in [containers.md](containers.md). |
| **Settings or workflows changed that you did not change** | 1. Run the drift script (6.1). 2. Check `gh api repos/(repo)/collaborators`, keys, hooks and recent commits and workflow runs. 3. Restore the setting from this document. |
| **A vulnerability was reported privately** | 1. Read it: `gh api repos/(repo)/security-advisories`. 2. Fix it privately through the advisory's temporary private fork. 3. Publish the advisory and request a CVE from the advisory page. |
| **The drift token expired** | Create a new token, `gh secret set DRIFT_TOKEN --env drift -R (repo)`, delete the old one (6.2). |

Before a release, run the deep agent audit from 4.2 on the code that is going out. It is manual, so it lives in this runbook as a habit and not as a check.
