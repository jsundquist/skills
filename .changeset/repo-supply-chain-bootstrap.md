---
"supply-chain-audit": minor
---

`repo-supply-chain-bootstrap` applies the baseline repository settings, starter workflows and a default-branch ruleset in one run, then waits for the workflows to report before requiring them. It is safe to run again: existing files are left alone, and a protected branch gets a pull request instead of a direct commit. `--scorecard` and `--lefthook` add an OpenSSF Scorecard workflow and a lefthook pre-commit config.
