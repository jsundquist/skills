# Changesets

Every change to a skill that users would notice gets a changeset: a small markdown file here that says what
changed and whether it is a `patch`, `minor` or `major` bump.

- One changeset per skill per change, so a change to two skills is two files.
- Start the description with the skill's name in backticks, as in the existing changelog entries.
- No changeset for tests, CI, refactors or docs.

The repo is a single plugin with a single version. The release takes the highest level among all pending
changesets, so skills are never versioned separately.

```bash
pnpm changeset
```

Releasing is described in the repository README.
