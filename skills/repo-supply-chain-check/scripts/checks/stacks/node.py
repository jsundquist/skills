"""Node specifics, one check per package manager: how new releases and install scripts are controlled.

npm, pnpm and yarn all run a package's install scripts and accept brand-new releases by default.
Each manager spells the fix differently, so each gets its own check."""
import re

from lib import DEPENDENCIES, bad, check, ok, warn


def uses_pnpm(repo):
    return repo.has_file(r"(^|/)pnpm-lock\.yaml$")


def uses_npm(repo):
    return repo.has_file(r"(^|/)package-lock\.json$")


def uses_yarn(repo):
    return repo.has_file(r"(^|/)yarn\.lock$")


def setting(config, pattern):
    return bool(re.search(pattern, config, re.M))


@check(DEPENDENCIES, when=uses_pnpm)
def pnpm_hardening(repo):
    config = repo.read("pnpm-workspace.yaml") + "\n" + repo.read(".npmrc")
    return [
        ok("pnpm: minimumReleaseAge set") if setting(config, r"minimumReleaseAge|minimum-release-age")
        else bad("pnpm: minimumReleaseAge not set (pnpm-workspace.yaml)"),
        ok("pnpm: build scripts allow-listed") if setting(config, r"allowBuilds|onlyBuiltDependencies")
        else warn("pnpm: build scripts not allow-listed (allowBuilds in pnpm-workspace.yaml)"),
    ]


@check(DEPENDENCIES, when=uses_npm)
def npm_hardening(repo):
    npmrc = repo.read(".npmrc")
    out = [
        ok("npm: min-release-age set") if setting(npmrc, r"^\s*min-release-age\s*=")
        else warn("npm: min-release-age not set in .npmrc (needs npm 11.10 or newer; the value is in days)"),
        ok("npm: ignore-scripts=true") if setting(npmrc, r"^\s*ignore-scripts\s*=\s*true")
        else warn("npm: ignore-scripts=true not set in .npmrc (install scripts run by default)"),
    ]
    installs = repo.build_commands(r"\bnpm (install|i)\b", unless=r"\s(-g|--global)\b")
    if installs:
        out.append(warn("npm: CI or Dockerfile uses `npm install`; `npm ci` fails when the lock is out of date", *installs[:5]))
    elif repo.build_lines:
        out.append(ok("npm: no `npm install` in CI or Dockerfiles"))
    return out


@check(DEPENDENCIES, when=uses_yarn)
def yarn_hardening(repo):
    berry = repo.read(".yarnrc.yml")
    if berry:
        return [
            ok("yarn: npmMinimalAgeGate set") if setting(berry, r"^\s*npmMinimalAgeGate:")
            else warn("yarn: npmMinimalAgeGate not set in .yarnrc.yml (needs Yarn 4.10 or newer)"),
            ok("yarn: enableScripts: false") if setting(berry, r"^\s*enableScripts:\s*false")
            else warn("yarn: enableScripts: false not set in .yarnrc.yml (install scripts run by default)"),
        ]
    classic = repo.read(".yarnrc")
    return [
        warn("yarn classic has no release-age setting; consider Yarn 4 (npmMinimalAgeGate) or another package manager"),
        ok("yarn: ignore-scripts set") if setting(classic, r"^\s*ignore-scripts\s+true")
        else warn("yarn: `ignore-scripts true` not set in .yarnrc (install scripts run by default)"),
    ]
