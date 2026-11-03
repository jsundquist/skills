#!/usr/bin/env bash
# Fails when the repo has a package manifest that .github/dependabot.yml does not cover,
# or a Dependabot entry without a cooldown. Run from the repo root.
set -euo pipefail

CFG=.github/dependabot.yml
[ -f "$CFG" ] || CFG=.github/dependabot.yaml
if [ ! -f "$CFG" ]; then
  echo "::error::no .github/dependabot.yml"
  exit 1
fi

# path regex ; accepted package-ecosystem values (alternation)
MAP='(^|/)package\.json$;npm
(^|/)(requirements[^/]*\.txt|pyproject\.toml|Pipfile|setup\.py)$;pip|uv
(^|/)uv\.lock$;uv
(^|/)Dockerfile[^/]*$;docker
(^|/)(docker-)?compose[^/]*\.ya?ml$;docker-compose
^\.github/(workflows|actions)/;github-actions
(^|/)action\.ya?ml$;github-actions
(^|/)go\.mod$;gomod
(^|/)Cargo\.toml$;cargo
(^|/)Gemfile$;bundler
(^|/)pom\.xml$;maven
(^|/)build\.gradle(\.kts)?$;gradle
\.tf$;terraform
(^|/)Chart\.yaml$;helm
(^|/)composer\.json$;composer
\.(cs|fs|vb)proj$;nuget
(^|/)mix\.exs$;mix
(^|/)pubspec\.yaml$;pub
(^|/)Package\.swift$;swift
(^|/)\.pre-commit-config\.yaml$;pre-commit
(^|/)devcontainer\.json$;devcontainers'

FILES="$(git ls-files)"
CONFIGURED="$(sed -nE 's/^[[:space:]]*-?[[:space:]]*package-ecosystem:[[:space:]]*"?([a-z-]+)"?.*/\1/p' "$CFG")"
status=0

while IFS=';' read -r pattern ecosystems; do
  match="$(printf '%s\n' "$FILES" | grep -E "$pattern" | head -3 || true)"
  [ -n "$match" ] || continue
  if ! printf '%s\n' "$CONFIGURED" | grep -qE "^($ecosystems)$"; then
    echo "::error::Dependabot has no '$ecosystems' entry, but the repo contains: $(echo "$match" | tr '\n' ' ')"
    status=1
  fi
done <<< "$MAP"

entries="$(printf '%s\n' "$CONFIGURED" | grep -c . || true)"
cooldowns="$(grep -c 'default-days' "$CFG" || true)"
if [ "$entries" != "$cooldowns" ]; then
  echo "::error::$cooldowns of $entries Dependabot entries have a cooldown (default-days)"
  status=1
fi

[ "$status" = 0 ] && echo "Dependabot covers every ecosystem found ($entries entries, all with a cooldown)."
exit "$status"
