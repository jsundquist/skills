---
name: audit-check
description: Read-only audit of a GitHub repository's software supply-chain posture (branch protection, Actions pinning, Dependabot cooldowns, secret scanning, SBOM, SLSA, container hardening). Use when the user asks to audit, review, or score a repo's supply chain or security settings, or asks for a new-repo security checklist.
---

# Audit a repo's supply chain

Read-only. Needs `gh` logged in; repo admin on the target for the settings calls.

1. Run `scripts/audit.sh OWNER/REPO`. Lines are ✅ ok, ⚠️ look at it, ❌ missing, ℹ️ info. Pipe through `grep -E '❌|⚠️'` to see only gaps.
2. Triage before suggesting fixes. Some gaps are fine for the repo type (no `USER` in a Dockerfile whose base already runs non-root, no CODEOWNERS on a solo repo). Order the real gaps: repo settings one command away first, then workflow/config changes that need a PR.
3. For settings gaps, tell the user `/audit-bootstrap OWNER/REPO` applies them. Do not run bootstrap yourself.
4. For everything else (`SECURITY.md`, `dependabot.yml` with `cooldown`, workflow hardening, secrets), read the matching section of `references/checklist.md`.

## Limits

The audit cannot see GHCR packages without `gh auth refresh -s read:packages`, token expiry, account-level settings (2FA, SSH keys, installed apps), or anything inside a cluster. Say so rather than implying coverage.

Never pass secret values on a command line; `gh secret set NAME -R R` prompts.
