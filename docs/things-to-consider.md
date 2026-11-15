# Things to consider

A working list of tools and practices for hardening a repository, its code, and the way it is built and shipped. It is a scratchpad for an opinionated "best practices" set, not a commitment: nothing here is wired into the skills in this repo yet.

Each item is tagged with where it can run:

- **hook**: a local git hook (pre-commit or pre-push)
- **action**: a GitHub Actions workflow
- **skill**: an AI skill or agent run locally or in CI
- **setting**: a repository or org setting, set once via `gh` or the API
- **manual**: not automatable, or only partly

## Sources

Found in a LinkedIn post (2026-11-05). The one-line descriptions come from the post and have **not** been verified against each repo. Short links were expanded.

| # | Tool | Repo | Post's claim |
|---|------|------|--------------|
| 1 | Cloudflare Security Audit | https://github.com/cloudflare/security-audit-skill | Coding agent runs a multi-phase audit; every finding verified before reporting |
| 2 | NVIDIA SkillSpector | https://github.com/NVIDIA/SkillSpector | Scans agent skills for prompt injection and exfiltration before install |
| 3 | Strix | https://github.com/usestrix/strix | AI agents that pentest your own app and help fix findings |
| 4 | Claude Code Security Review | https://github.com/anthropics/claude-code-security-review | Security review on every pull request |
| 5 | Semgrep | https://github.com/semgrep/semgrep | Write a rule once, catch the bug everywhere |
| 6 | Gitleaks | https://github.com/gitleaks/gitleaks | Stops secrets before they reach a commit |
| 7 | TruffleHog | https://github.com/trufflesecurity/trufflehog | Finds leaked credentials and checks whether they still work |
| 8 | OSV-Scanner | https://github.com/google/osv-scanner | Flags dependencies with known vulnerabilities |
| 9 | zizmor | https://github.com/zizmorcore/zizmor | Finds holes in GitHub Actions workflows |
| 10 | Nuclei | https://github.com/projectdiscovery/nuclei | Scans running services for known CVEs and misconfigurations |
| 11 | garak | https://github.com/NVIDIA/garak | Throws jailbreaks and prompt injections at an LLM app |

## By layer

### 1. Secrets

| Practice | Tools | Runs as |
|----------|-------|---------|
| Block secrets before commit | Gitleaks | hook |
| Scan full history in CI | Gitleaks, TruffleHog | action |
| Prefer verified findings to cut noise (TruffleHog checks whether a credential is live) | TruffleHog `--only-verified` | action |
| Platform secret scanning and push protection | GitHub native | setting |
| Rotate anything that leaked, even if deleted from history | | manual |

Open question: Gitleaks and TruffleHog overlap. Pick one for the hook (fast, offline: Gitleaks) and consider the other in CI only for live-credential verification.

### 2. Dependencies

| Practice | Tools | Runs as |
|----------|-------|---------|
| Known-vulnerability scan of every lockfile, on push and weekly | OSV-Scanner | action |
| Block PRs that add vulnerable or badly licensed deps | `dependency-review-action` | action (required check) |
| Automated updates with a cooldown | Dependabot / Renovate | setting |
| Lockfile enforced in CI | package manager's frozen install | action |
| Vet a new dependency (maintainers, age, install scripts) | | manual / skill |

### 3. Code

| Practice | Tools | Runs as |
|----------|-------|---------|
| Static analysis, default rules | CodeQL | setting / action |
| Custom rules for house patterns ("never call X without Y") | Semgrep | hook / action |
| AI review of each PR for security issues | Claude Code Security Review | action |
| Deep multi-phase audit with verified findings | Cloudflare security-audit-skill | skill (local, occasionally) |

Open question: where AI review sits relative to deterministic scanners. Suggested order: deterministic tools gate the merge; AI review comments but does not block.

### 4. CI and workflows

| Practice | Tools | Runs as |
|----------|-------|---------|
| Lint workflows for injection, excessive permissions, unpinned actions | zizmor | hook / action |
| Pin actions to a full commit SHA | GitHub setting, Dependabot | setting |
| Read-only `GITHUB_TOKEN` by default; widen per job | | setting / action |
| `persist-credentials: false` on checkout | | action |
| Actions cannot approve PRs | | setting |

### 5. Repository settings

Branch protection or rulesets, required checks, signed commits, CODEOWNERS, private vulnerability reporting, delete branches on merge. All **setting**. This repo's `repo-supply-chain-check` skill already audits and bootstraps most of these.

### 6. Agent and AI supply chain

New category, and the least settled.

| Practice | Tools | Runs as |
|----------|-------|---------|
| Scan third-party agent skills, MCP servers and plugins before installing | NVIDIA SkillSpector | skill / hook |
| Red-team your own LLM features (jailbreaks, prompt injection) | garak | action (scheduled) / manual |
| Treat repo content, issues and PR text as untrusted input to any agent in CI | | manual |

### 7. Running systems

Outside what a repo-level audit can see, but worth a pointer.

| Practice | Tools | Runs as |
|----------|-------|---------|
| Scan deployed services for known CVEs and misconfigurations | Nuclei | action (scheduled) |
| Agentic pentest of your own app | Strix | skill / manual |

## Where this repo stands

`repo-supply-chain-check` covers sections 2, 4 and 5 and recognises Gitleaks and zizmor. Not covered: Semgrep, OSV-Scanner, TruffleHog, anything in sections 6 and 7. An earlier attempt to recognise TruffleHog, OSV-Scanner and Semgrep in the audit was reverted so the list could be decided first.

## Next steps

- Decide which items are opinionated defaults and which are optional.
- Verify each tool's claims, license and maintenance status before recommending it.
- For each default, decide: hook, action, or both, and what "good" looks like as an audit check.
- Look for gaps the post missed: SBOM and provenance (SLSA, Sigstore), container scanning, IaC scanning, OpenSSF Scorecard, artifact signing.
