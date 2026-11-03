# supply-chain-audit

Two [Claude Code skills](https://code.claude.com/docs/en/skills) and their standalone shell scripts for auditing and hardening the supply-chain settings of a GitHub repository. Everything goes through the `gh` CLI.

| Skill | Script | What it does |
|---|---|---|
| `/audit-check OWNER/REPO` | `skills/audit-check/scripts/audit.sh` | Read-only audit: repo settings, branch protection and rulesets, alerts, policy files, Dependabot config, lockfiles, workflow hardening, Dockerfiles, secrets (names only), recent run health. Claude may run it on its own. |
| `/audit-bootstrap OWNER/REPO` | `skills/audit-bootstrap/scripts/bootstrap.sh` | Applies the repo settings, commits starter files, and creates the main-branch ruleset. Changes live settings, so only you can invoke it (`disable-model-invocation`). Dry run first, then `--apply`. |

`skills/audit-check/references/checklist.md` is the per-area checklist with the `gh` command for each item.

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

Then, with `--checks default`, a ruleset on the default branch (created, or updated in place if it exists): no deletion, no force-push, PR required with **1 approval, code-owner review, last-push approval and stale-review dismissal**, required status checks that must be up to date.

**The admin role can bypass the ruleset for pull requests.** Without it a solo owner could never merge their own PR (you cannot approve your own work, and last-push approval means someone other than the pusher must). The rules are therefore enforced for everyone but repo admins; with one maintainer that is not a second pair of eyes. Measured on a test repo, OpenSSF Scorecard's Branch-Protection check went from 4 to 8 out of 10. The remaining warnings are "settings apply to administrators" (caused by this bypass) and "required approving review count is 1" (it wants 2). Both need a second maintainer; remove the `bypass_actors` entry in `bootstrap.sh` and raise the approval count once there is one.

## Use the scripts directly

```bash
skills/audit-check/scripts/audit.sh owner/repo | grep -E '❌|⚠️'
skills/audit-bootstrap/scripts/bootstrap.sh owner/repo                       # dry run (--show prints the files)
skills/audit-bootstrap/scripts/bootstrap.sh owner/repo --apply --license mit --codeowner @owner   # settings + starter files
# wait for the workflows to run on the default branch, then:
skills/audit-bootstrap/scripts/bootstrap.sh owner/repo --apply --checks default
```

Requires `bash` and `gh` (logged in, admin on the target repo). For GHCR package checks: `gh auth refresh -s read:packages`. The ruleset is a second pass because the check names must have reported on the default branch first. `gitleaks-action` needs a `GITLEAKS_LICENSE` secret when the repo is owned by an organization.

## Install as skills

Each skill is self-contained, so link each one:

```bash
git clone https://github.com/OWNER/supply-chain-audit ~/src/supply-chain-audit
for s in ~/src/supply-chain-audit/skills/*; do ln -s "$s" ~/.claude/skills/; done
```

Keep the clone wherever you like (for example in your dotfiles). Use `.claude/skills/` inside a repo to scope them to one project.

## License

MIT
