---
name: repo-supply-chain-bootstrap
description: Apply baseline supply-chain settings and starter files to a GitHub repo with gh (secret scanning, push protection, Dependabot, read-only Actions token, SHA pinning, private vulnerability reporting, CodeQL, a security workflow, dependabot.yml, SECURITY.md, main-branch ruleset). Changes live repo settings and commits to the default branch, so run it only when the user invokes it.
disable-model-invocation: true
argument-hint: OWNER/REPO [--license ID] [--codeowner @user] [--scorecard] [--lefthook] [--no-ruleset] [--no-scaffold]
---

# Bootstrap a repo's supply-chain settings

Changes live GitHub settings and **commits files straight to the default branch**. Needs Python 3.11+ and `gh` logged in with admin on the target. Arguments: `$ARGUMENTS`.

What it does, in order:
1. Repo settings: secret scanning, push protection, Dependabot alerts and security updates, read-only token, Actions cannot approve PRs, actions must be pinned to a full SHA, private vulnerability reporting, CodeQL default setup, delete branches on merge.
2. Starter files, created only when absent (never overwritten), with action versions resolved to full SHAs at run time:
   - `.github/workflows/security.yml`: jobs `zizmor`, `actionlint`, `gitleaks`, `dependency-review`
   - `.github/workflows/dependabot-coverage.yml` + `.github/scripts/check-dependabot-coverage.sh`: fails when a manifest in the repo has no Dependabot entry, or an entry has no cooldown
   - `.github/dependabot.yml` (github-actions, 7-day cooldown), `SECURITY.md`, `.github/CODEOWNERS` (`* <code owner>`)
   - `--scorecard` adds an OpenSSF Scorecard workflow
   - `--lefthook` adds `lefthook.yml` (gitleaks on staged changes, actionlint and zizmor on workflow files). Each clone must run `lefthook install` and have the tools installed; a missing tool is skipped silently. CI is still the gate
3. Last, in the same run: the default-branch ruleset (skip with `--no-ruleset`), created or updated in place, once the starter workflows have reported on the default branch: no deletion, no force-push, PR required with 1 approval, code-owner review, last-push approval and stale-review dismissal, required checks. The repo admin role can bypass for pull requests, so a solo owner can still merge. Say this plainly to the user: on a one-maintainer repo it adds no real second reviewer. It raised Scorecard's Branch-Protection score from 4 to 8 of 10 in testing; the last points need a second maintainer.

Steps:
0. **Ask before planning** (use AskUserQuestion; never assume an answer, and skip a question the user already answered in `$ARGUMENTS`):
   - **License.** Which one: MIT, Apache-2.0, another SPDX id, or none (reasonable for a private repo). Passed as `--license <id>`; omit the flag for none. Never default to MIT.
   - **Code owner.** Who owns `.github/CODEOWNERS`: `@user` or `@org/team`, who must have write access. On a personal account the default is the repo owner, so confirm it. On an organization-owned repo it is required, because an organization itself cannot be a code owner; without `--codeowner` the file is skipped and the ruleset won't require code-owner review. Passed as `--codeowner @x`.
   - **Scorecard.** Whether to add the OpenSSF Scorecard workflow (`--scorecard`).
   - **Lefthook.** Whether to add a `lefthook.yml` pre-commit config (`--lefthook`). Only worth it if the user has lefthook installed.
1. Run `python scripts/bootstrap.py OWNER/REPO` with those flags and **without** `--apply` (add `--show` to print the files) and show the user the plan.
2. Run again with `--apply` only after the user agrees.
3. **One pass, with a wait.** After committing the starter files the script waits (up to 8 minutes) for their workflows to report on the default branch, then creates the ruleset; a required check that never runs would block every PR. Run `--apply` in the background or with a long timeout, because it can take minutes. If the wait times out it skips the ruleset and counts a failed step: check `gh run list -R OWNER/REPO`, then run the same command again. If the default branch was already protected, the files go in by PR and the ruleset is left as it is until the PR merges; run the command again then.
4. Tell the user to run the repo-supply-chain-check skill (`/jsundquist:repo-supply-chain-check OWNER/REPO`) to confirm.

Notes to relay:
- `actionlint` uses `raven-actions/actionlint` (pinned to a SHA; Dependabot bumps it). It runs the latest actionlint release, since the action's `version` input defaults to `latest`; that binary is not pinned or checksum-verified here.
- `gitleaks-action` needs a `GITLEAKS_LICENSE` secret (free key) when the repo is owned by an organization; personal accounts don't.
- `dependency-review` needs the dependency graph (free on public repos; GitHub Advanced Security on private ones).
- With the strict ruleset, someone other than the PR's last pusher must approve, or an admin bypasses.
- Code-scanning alerts, including Scorecard's, are left open on purpose: they show what the repo still needs. Bootstrap never dismisses them.
- Safe to run again. When the default branch is already protected, new files go on `chore/supply-chain-bootstrap` and one PR is opened instead of a direct commit.
- The script keeps going after a failed step and ends with a count of failures and a non-zero exit.

Still manual: `LICENSE`, secrets, build/release/SBOM/signing workflows, release tags.
