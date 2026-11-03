# supply-chain-audit

## 0.1.0

### Minor Changes

- [`6f30712`](https://github.com/jsundquist/skills/commit/6f30712878e237e22f2f331d49b7b3d4942d0b50) Thanks [@jsundquist](https://github.com/jsundquist)! - `repo-supply-chain-bootstrap` applies the baseline repository settings, starter workflows and a default-branch ruleset in one run, then waits for the workflows to report before requiring them. It is safe to run again: existing files are left alone, and a protected branch gets a pull request instead of a direct commit. `--scorecard` and `--lefthook` add an OpenSSF Scorecard workflow and a lefthook pre-commit config.

- [`6f30712`](https://github.com/jsundquist/skills/commit/6f30712878e237e22f2f331d49b7b3d4942d0b50) Thanks [@jsundquist](https://github.com/jsundquist)! - `repo-supply-chain-check` audits a GitHub repository against six supply-chain areas (artifact hardening, dependency management, artifact repositories, SBOM, SLSA and the golden path) and reports each as met, partial, gap or n/a. Language and tool specifics (npm, pnpm, yarn, uv, pip, containers) are separate checks that only run when the repo uses them. `--gaps` shows only problems and `--strict` exits non-zero on a gap.
