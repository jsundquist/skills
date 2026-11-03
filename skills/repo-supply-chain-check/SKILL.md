---
name: repo-supply-chain-check
description: Read-only audit of a GitHub repository's software supply-chain posture (branch protection, Actions pinning, Dependabot cooldowns, secret scanning, SBOM, SLSA, container hardening). Use when the user asks to audit, review, or score a repo's supply chain or security settings, or asks for a new-repo security checklist.
---

# Audit a repo's supply chain

Read-only. Needs Python 3.11+ and `gh` logged in; repo admin on the target for the settings calls.

1. Run `python scripts/audit.py OWNER/REPO`. Lines are ✅ ok, ⚠️ look at it, ❌ missing, ℹ️ info. The last section, "Summary by area", rolls them up into six areas (artifact hardening, dependency management, artifact repositories, SBOM, SLSA, golden path) as met, partial, gap or n/a. An area is n/a when the repo has nothing of that kind (no Dockerfile or release, no manifest). `--gaps` shows only warnings and gaps. `--strict` exits 1 when any area has a gap.
2. Triage before suggesting fixes. Some gaps are fine for the repo type (no `USER` in a Dockerfile whose base already runs non-root, no CODEOWNERS on a solo repo). Order the real gaps: repo settings one command away first, then workflow/config changes that need a PR.
3. For settings gaps, tell the user the repo-supply-chain-bootstrap skill (`/jsundquist:repo-supply-chain-bootstrap OWNER/REPO`) applies them. Do not run bootstrap yourself.
4. For everything else (`SECURITY.md`, `dependabot.yml` with `cooldown`, workflow hardening, secrets), read the matching section of `references/checklist.md`. For language or tool specifics (pnpm, uv, Docker, Kubernetes), read only the matching section of `references/stacks.md`.

## Limits

Bootstrap applies settings and baseline files only. For artifact repositories, SBOM, SLSA and the deeper hardening items the audit reports whether they are present; there is no template that creates them, so point the user to the matching section of `references/checklist.md`, or `references/stacks.md` for a specific stack.

The audit cannot see GHCR packages without `gh auth refresh -s read:packages`, token expiry, account-level settings (2FA, SSH keys, installed apps), or anything inside a cluster. Say so rather than implying coverage.

Never pass secret values on a command line; `gh secret set NAME -R R` prompts.
