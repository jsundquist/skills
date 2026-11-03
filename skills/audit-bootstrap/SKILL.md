---
name: audit-bootstrap
description: Apply baseline supply-chain settings and starter files to a GitHub repo with gh (secret scanning, push protection, Dependabot, read-only Actions token, SHA pinning, private vulnerability reporting, CodeQL, a security workflow, dependabot.yml, SECURITY.md, main-branch ruleset). Changes live repo settings and commits to the default branch, so run it only when the user invokes it.
disable-model-invocation: true
argument-hint: OWNER/REPO [--license ID] [--codeowner @user] [--checks default] [--scorecard] [--no-scaffold]
---

# Bootstrap a repo's supply-chain settings

Changes live GitHub settings and **commits files straight to the default branch**. Needs `gh` logged in with admin on the target. Arguments: `$ARGUMENTS`.

What it does, in order:
1. Repo settings: secret scanning, push protection, Dependabot alerts and security updates, read-only token, Actions cannot approve PRs, actions must be pinned to a full SHA, private vulnerability reporting, CodeQL default setup, delete branches on merge.
2. Starter files, created only when absent (never overwritten), with action versions resolved to full SHAs at run time:
   - `.github/workflows/security.yml`: jobs `zizmor`, `actionlint`, `gitleaks`, `dependency-review`
   - `.github/workflows/dependabot-coverage.yml` + `.github/scripts/check-dependabot-coverage.sh`: fails when a manifest in the repo has no Dependabot entry, or an entry has no cooldown
   - `.github/dependabot.yml` (github-actions, 7-day cooldown), `SECURITY.md`, `.github/CODEOWNERS` (`* <code owner>`)
   - `--scorecard` adds an OpenSSF Scorecard workflow
3. With `--checks default` (or a list): the default-branch ruleset, created or updated in place: no deletion, no force-push, PR required with 1 approval, code-owner review, last-push approval and stale-review dismissal, required checks. The repo admin role can bypass for pull requests, so a solo owner can still merge. Say this plainly to the user: on a one-maintainer repo it adds no real second reviewer. It raised Scorecard's Branch-Protection score from 4 to 8 of 10 in testing; the last points need a second maintainer.

Steps:
0. **Ask before planning** (use AskUserQuestion; never assume an answer, and skip a question the user already answered in `$ARGUMENTS`):
   - **License.** Which one: MIT, Apache-2.0, another SPDX id, or none (reasonable for a private repo). Passed as `--license <id>`; omit the flag for none. Never default to MIT.
   - **Code owner.** Who owns `.github/CODEOWNERS`: `@user` or `@org/team`, who must have write access. On a personal account the default is the repo owner, so confirm it. On an organization-owned repo it is required, because an organization itself cannot be a code owner; without `--codeowner` the file is skipped and the ruleset won't require code-owner review. Passed as `--codeowner @x`.
   - **Scorecard.** Whether to add the OpenSSF Scorecard workflow (`--scorecard`).
1. Run `scripts/bootstrap.sh OWNER/REPO` with those flags and **without** `--apply` (add `--show` to print the files) and show the user the plan.
2. Run again with `--apply` only after the user agrees.
3. **Two passes.** The ruleset needs the check names to have reported on the default branch, so the first pass has no `--checks`. Wait for the workflows (`gh run list -R OWNER/REPO`), then run `--apply --checks default`. The script refuses to create the ruleset while a check hasn't reported, because a required check that never runs blocks every PR.
4. Tell the user to run `/audit-check OWNER/REPO` to confirm.

Notes to relay:
- `actionlint` uses `raven-actions/actionlint` (pinned to a SHA; Dependabot bumps it). It runs the latest actionlint release, since the action's `version` input defaults to `latest`; that binary is not pinned or checksum-verified here.
- `gitleaks-action` needs a `GITLEAKS_LICENSE` secret (free key) when the repo is owned by an organization; personal accounts don't.
- `dependency-review` needs the dependency graph (free on public repos; GitHub Advanced Security on private ones).
- Direct commits fail once a ruleset requires PRs. Bootstrap before the ruleset exists, or add the files by PR. With the strict ruleset, someone other than the PR's last pusher must approve, or an admin bypasses.
- Open Scorecard alerts that can't be fixed on a new repo are dismissed as "won't fix" when `scorecard.yml` exists; run again after the first Scorecard run.
- The script keeps going after a failed step and ends with a count of failures and a non-zero exit.

Still manual: `LICENSE`, secrets, build/release/SBOM/signing workflows, release tags.
