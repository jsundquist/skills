# skills

[Claude Code skills](https://code.claude.com/docs/en/skills), packaged as the `jsundquist` plugin. Each skill lives in `skills/<name>` and is self-contained.

## Repo supply-chain security

Two skills, with Python scripts that go through the `gh` CLI, for auditing and hardening the supply-chain settings of a GitHub repository.

| Skill | Script | What it does |
|---|---|---|
| `/jsundquist:repo-supply-chain-check OWNER/REPO` | `skills/repo-supply-chain-check/scripts/audit.py` | Read-only audit: repo settings, branch protection and rulesets, alerts, policy files, Dependabot config, lockfiles, workflow hardening, Dockerfiles, secrets (names only), recent run health. Ends with a summary of six areas (artifact hardening, dependency management, artifact repositories, SBOM, SLSA, golden path) as met, partial, gap or n/a; `--strict` exits 1 on any gap. Claude may run it on its own. |
| `/jsundquist:repo-supply-chain-bootstrap OWNER/REPO` | `skills/repo-supply-chain-bootstrap/scripts/bootstrap.py` | Applies the repo settings, commits starter files, and creates the main-branch ruleset. Changes live settings, so only you can invoke it (`disable-model-invocation`). Dry run first, then `--apply`. Safe to re-run: once the default branch is protected, new files arrive as a PR. |

`skills/repo-supply-chain-check/references/checklist.md` is the per-area checklist with the `gh` command for each item. Items that only apply to one language or tool (pnpm, uv, Docker, Kubernetes) are in `references/stacks.md`; the audit's checks for them are in `scripts/checks/stacks/`.

### What bootstrap sets up

Settings: secret scanning, push protection, Dependabot alerts and security updates, read-only `GITHUB_TOKEN`, Actions cannot approve PRs, actions pinned to a full SHA, private vulnerability reporting, CodeQL default setup, delete branches on merge.

Starter files (only if absent; action versions are resolved to full commit SHAs when it runs):

| File | Purpose |
|---|---|
| `.github/workflows/security.yml` | Jobs `zizmor`, `actionlint` (via `raven-actions/actionlint`: inline annotations plus a job summary), `gitleaks`, `dependency-review` on PRs, pushes and a weekly schedule. Every action is pinned to a full SHA, so Dependabot can bump it |
| `.github/workflows/dependabot-coverage.yml` | Fails when a manifest in the repo (npm, pip/uv, docker, gomod, cargo, ...) has no Dependabot entry, or an entry has no cooldown |
| `.github/dependabot.yml` | `github-actions` with a 7-day cooldown; add entries as the repo grows |
| `SECURITY.md` | Points at private vulnerability reporting |
| `.github/CODEOWNERS` | `* <code owner>` (`--codeowner @user` or `@org/team`; defaults to the owner on a personal account, required for an organization), so the ruleset's code-owner review has an owner |
| `LICENSE` | Only with `--license <id>` (mit, apache-2.0, ...). Never chosen for you |
| `.github/workflows/scorecard.yml` | Only with `--scorecard` (OpenSSF Scorecard) |
| `lefthook.yml` | Only with `--lefthook`: gitleaks on staged changes, actionlint and zizmor on workflow files. Needs `lefthook install` in each clone and the tools on PATH; a missing tool is skipped. CI stays the gate |

Last, in the same run (skip with `--no-ruleset`), a ruleset on the default branch, created once the starter workflows have reported there (created, or updated in place if it exists): no deletion, no force-push, PR required with **1 approval, code-owner review, last-push approval and stale-review dismissal**, required status checks that must be up to date.

**The admin role can bypass the ruleset for pull requests.** Without it a solo owner could never merge their own PR (you cannot approve your own work, and last-push approval means someone other than the pusher must). The rules are therefore enforced for everyone but repo admins; with one maintainer that is not a second pair of eyes. Measured on a test repo, OpenSSF Scorecard's Branch-Protection check went from 4 to 8 out of 10. The remaining warnings are "settings apply to administrators" (caused by this bypass) and "required approving review count is 1" (it wants 2). Both need a second maintainer; remove the `bypass_actors` entry in `skills/repo-supply-chain-bootstrap/scripts/steps/ruleset.py` and raise the approval count once there is one.

## Use the scripts directly

```bash
python3 skills/repo-supply-chain-check/scripts/audit.py owner/repo --gaps
python3 skills/repo-supply-chain-bootstrap/scripts/bootstrap.py owner/repo                       # dry run (--show prints the files)
python3 skills/repo-supply-chain-bootstrap/scripts/bootstrap.py owner/repo --apply --license mit --codeowner @owner   # settings, starter files, then the ruleset
```

Requires Python 3.11+ and `gh` (logged in, admin on the target repo). For GHCR package checks: `gh auth refresh -s read:packages`. Bootstrap waits up to 8 minutes for the starter workflows to report before creating the ruleset, because a required check must have reported first; if it times out, run the same command again. `gitleaks-action` needs a `GITLEAKS_LICENSE` secret when the repo is owned by an organization.

## Install

This repo is a Claude Code plugin named `jsundquist`, so the skills are namespaced: `/jsundquist:repo-supply-chain-check` and `/jsundquist:repo-supply-chain-bootstrap`.

Try it from a clone (validate first with `claude plugin validate .`):

```bash
git clone https://github.com/jsundquist/skills ~/src/skills
claude --plugin-dir ~/src/skills
```

To keep it installed, add this repo as a marketplace and install from it:

```
/plugin marketplace add jsundquist/skills
/plugin install jsundquist@jsundquist
```

Or link the skills instead (each is self-contained), which gives the un-namespaced names `/repo-supply-chain-check` and `/repo-supply-chain-bootstrap`:

```bash
for s in ~/src/skills/skills/*; do ln -s "$s" ~/.claude/skills/; done
```

Use `.claude/skills/` inside a repo to scope them to one project.

## Development

```bash
python3 tests/run.py          # both skills' unit tests (standard library only)
uvx ruff check .              # lint (rules pinned in ruff.toml)
pnpm install                  # once, for Changesets
pnpm changeset                # describe a user-visible change
lefthook install              # optional pre-commit hooks (gitleaks, actionlint, zizmor)
```

CI (`.github/workflows/ci.yml`) runs the tests on Python 3.11 and the latest 3.x, ruff, shellcheck on the one Bash script the bootstrap skill ships, and checks that the JSON manifests parse and the two versions agree. The starter workflows from `repo-supply-chain-bootstrap` (zizmor, actionlint, gitleaks, dependency-review, dependabot-coverage) run here too. The tests and the two skills' `lib.py` are separate on purpose: each skill is self-contained, so the suites run in separate Python processes.

## Releasing

Versions are tracked with [Changesets](https://github.com/changesets/changesets). The version lives in `package.json` (private, never published) and is copied to `.claude-plugin/plugin.json`. Tags are `vX.Y.Z`; `plugin.json` and the changelog use `X.Y.Z`.

1. For every change a user of the skills should know about, run `pnpm changeset`, choose `patch`, `minor` or `major`, and describe the change for a reader. Commit the generated file in `.changeset/` with the change.
2. In the Actions tab, run the **release** workflow on `main`. With changesets pending it reads all of them, takes the highest level (major beats minor beats patch), updates `package.json`, `plugin.json` and `CHANGELOG.md`, pushes a `release/vX.Y.Z` branch and opens a PR. Merge that PR.
3. Run the **release** workflow again. With nothing pending and no tag for the current version, it creates the tag `vX.Y.Z` and the GitHub release, with that version's section of `CHANGELOG.md` as the notes.

It needs two runs because `main` is protected: the version commit has to go through a PR. The workflow stops with an error if there is nothing to release. If it cannot open the PR itself (Actions may not create PRs on this repo; bootstrap turns that off), it prints the link to open it by hand. To bump the version locally instead: `GITHUB_TOKEN="$(gh auth token)" pnpm run version` on a branch.

## License

MIT
