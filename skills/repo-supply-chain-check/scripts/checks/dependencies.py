"""Dependency management: pinning, update automation with cooldowns, vulnerability scanning."""
import re

from lib import DEPENDENCIES, bad, check, info, ok, warn

from checks.stacks import detected


def dependabot_ecosystems(repo):
    """{ecosystem: has_cooldown} from dependabot.yml, or None when the repo has no Dependabot config."""
    path = next(iter(repo.files(r"^\.github/dependabot\.ya?ml$")), None)
    if not path:
        return None
    blocks = re.split(r"(?m)^\s*-\s*package-ecosystem:", repo.read(path))[1:]
    return {b.split()[0].strip("\"'"): "default-days" in b for b in blocks}


@check(DEPENDENCIES)
def update_automation(repo):
    ecosystems = dependabot_ecosystems(repo)
    if ecosystems is None:
        if repo.has_file(r"^(\.github/)?renovate\.json5?$"):
            return ok("Renovate config present (cooldown not checked)")
        return bad("no dependabot.yml or renovate config")
    out = [info(f"Dependabot covers: {', '.join(ecosystems) or 'nothing'}")]
    no_cooldown = [e for e, has in ecosystems.items() if not has]
    out.append(ok("cooldown on every ecosystem") if not no_cooldown else bad(f"no cooldown on: {', '.join(no_cooldown)}"))
    for stack in detected(repo):
        if not any(e in ecosystems for e in stack.dependabot):
            out.append(warn(f"{stack.name}: repo has files for it but Dependabot is not configured for {'/'.join(stack.dependabot)}"))
    return out


@check(DEPENDENCIES)
def open_dependabot_alerts(repo):
    alerts = repo.api("dependabot/alerts?state=open&per_page=100")
    if alerts is None:
        return warn("Dependabot alerts: unknown (disabled, or not readable with this token)")
    return warn(f"Dependabot alerts open: {len(alerts)}") if alerts else ok("Dependabot alerts: 0")


@check(DEPENDENCIES)
def lockfiles(repo):
    out = []
    for stack in detected(repo):
        if not stack.lockfile:
            continue
        if repo.has_file(stack.lockfile):
            out.append(ok(f"{stack.name}: lock file committed"))
        else:
            make = bad if stack.lock_required else warn
            out.append(make(f"{stack.name}: no lock file committed"))
    return out


@check(DEPENDENCIES)
def vulnerability_scanning(repo):
    out = [
        ok("dependency-review on PRs") if repo.ci_has("dependency-review-action") else bad("dependency-review on PRs (not found)"),
        ok("dependabot-coverage (manifests vs dependabot.yml)") if repo.ci_has("dependabot-coverage")
        else bad("dependabot-coverage (not found)"),
    ]
    for stack in detected(repo):
        if stack.audit:
            found = repo.ci_has(stack.audit) or repo.ci_has("dependency-review-action")
            out.append(ok(f"{stack.name}: vulnerability audit in CI") if found else bad(f"{stack.name}: vulnerability audit in CI (not found)"))
    return out


@check(DEPENDENCIES, when=lambda repo: any(s.lockfile for s in detected(repo)))
def scheduled_scan(repo):
    if repo.ci_has(r"cron:"):
        return ok("a scheduled workflow exists (check it covers the audit)")
    return warn("no scheduled workflow (new CVEs appear without commits)")
