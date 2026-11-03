---
"supply-chain-audit": minor
---

`repo-supply-chain-check` audits a GitHub repository against six supply-chain areas (artifact hardening, dependency management, artifact repositories, SBOM, SLSA and the golden path) and reports each as met, partial, gap or n/a. Language and tool specifics (npm, pnpm, yarn, uv, pip, containers) are separate checks that only run when the repo uses them. `--gaps` shows only problems and `--strict` exits non-zero on a gap.
