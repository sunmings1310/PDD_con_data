#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
RESOLVER = ROOT / ".github" / "scripts" / "resolve-diff-base.sh"


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(command, cwd=cwd, env=merged, text=True, encoding="utf-8", capture_output=True)


def git(*args: str, cwd: Path = ROOT) -> str:
    result = run(["git", *args], cwd=cwd)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def git_with_env(*args: str, cwd: Path, env: dict[str, str]) -> str:
    result = run(["git", *args], cwd=cwd, env=env)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def bash_executable() -> str:
    found = shutil.which("bash")
    if found:
        return found
    fallback = Path(r"D:\Git\bin\bash.exe")
    if fallback.is_file():
        return str(fallback)
    raise RuntimeError("bash executable not found")


def markdown_check() -> None:
    files = list(ROOT.glob("*.md"))
    files += list((ROOT / "docs").rglob("*.md"))
    files += list((ROOT / "server").glob("*.md"))
    files += list((ROOT / "android_collector").glob("*.md"))
    files += list((ROOT / "web").glob("*.md"))
    files += list((ROOT / ".github").glob("*.md"))
    files = sorted(set(files))
    failures: list[str] = []
    pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
    for source in files:
        for raw in pattern.findall(source.read_text(encoding="utf-8")):
            target = raw.strip().split()[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_text = target.split("#", 1)[0]
            if path_text and not (source.parent / path_text).resolve().exists():
                failures.append(f"{source.relative_to(ROOT)}: missing link target {target}")
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print(f"Validated {len(files)} Markdown files")


def yaml_check() -> None:
    import yaml

    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    yaml.safe_load(workflow.read_text(encoding="utf-8"))
    print("YAML_FILES=1")
    print("YAML_PARSE=PASS")


def ci_static_check() -> None:
    import yaml

    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    text = workflow.read_text(encoding="utf-8")
    jobs = yaml.safe_load(text)["jobs"]
    expected = {"governance", "python-offline", "web-build", "android-jvm", "oracle-scope", "oracle-integration"}
    assert set(jobs) == expected, sorted(jobs)
    required_text = [
        "fetch-depth: 0",
        ".github/scripts/resolve-diff-base.sh",
        "validate_governance.py --check resolver",
        "org.gradle.wrapper.GradleWrapperMain",
        "ORACLE_GATE=SKIPPED",
        "BLOCKED: missing $name",
        "needs.oracle-scope.outputs.required == 'true'",
        "test_job_reconciliation_oracle_integration.py",
    ]
    for value in required_text:
        assert value in text, value
    resolver = RESOLVER.read_text(encoding="utf-8")
    for value in ("git fetch", "git rev-parse", "git merge-base", "git cat-file", "BLOCKED:", "exit 2"):
        assert value in resolver, value
    print("CI_JOBS=" + ",".join(sorted(jobs)))
    print("CI_STATIC=PASS")


def resolver_call(env: dict[str, str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return run([bash_executable(), ".github/scripts/resolve-diff-base.sh"], cwd=cwd, env=env)


def expect_pass(name: str, env: dict[str, str], expected: str, *, cwd: Path = ROOT) -> None:
    result = resolver_call(env, cwd=cwd)
    actual = result.stdout.strip()
    if result.returncode != 0 or actual != expected:
        raise AssertionError(f"{name}: exit={result.returncode} stdout={actual!r} stderr={result.stderr.strip()!r}")
    print(f"{name}_OUTPUT={actual}")
    print(f"{name}_EXIT=0")


def expect_blocked(name: str, env: dict[str, str], message: str, *, cwd: Path = ROOT) -> None:
    result = resolver_call(env, cwd=cwd)
    actual = result.stderr.strip()
    expected = f"BLOCKED: {message}"
    if result.returncode != 2 or actual != expected:
        raise AssertionError(f"{name}: exit={result.returncode} stdout={result.stdout.strip()!r} stderr={actual!r}")
    print(f"{name}_OUTPUT={actual}")
    print(f"{name}_EXIT=2")


def resolver_check() -> None:
    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD^")
    main = git("rev-parse", "origin/main")
    common = {"GITHUB_SHA": head, "DEFAULT_BRANCH": "main"}
    expect_pass("RESOLVER_PR", {**common, "EVENT_NAME": "pull_request", "PR_BASE_SHA": main}, main)
    expect_pass("RESOLVER_PUSH", {**common, "EVENT_NAME": "push", "PUSH_BEFORE_SHA": parent}, parent)
    expect_pass("RESOLVER_DISPATCH", {**common, "EVENT_NAME": "workflow_dispatch"}, main)
    expect_blocked(
        "RESOLVER_INVALID_BASE",
        {**common, "EVENT_NAME": "pull_request", "PR_BASE_SHA": "not-a-commit"},
        "pull_request base commit is missing or invalid: not-a-commit",
    )
    expect_blocked(
        "RESOLVER_INVALID_HEAD",
        {"GITHUB_SHA": "not-a-head", "EVENT_NAME": "pull_request", "PR_BASE_SHA": main},
        "head commit is missing or invalid: not-a-head",
    )
    missing = "definitely-missing-governance-branch"
    expect_blocked(
        "RESOLVER_FETCH_FAILURE",
        {"GITHUB_SHA": head, "EVENT_NAME": "workflow_dispatch", "DEFAULT_BRANCH": missing},
        f"unable to fetch default branch: {missing}",
    )

    with tempfile.TemporaryDirectory(prefix="repo-gov-resolver-") as temp:
        repo = Path(temp) / "repo"
        remote = Path(temp) / "remote.git"
        repo.mkdir()
        git("init", "--bare", str(remote), cwd=Path(temp))
        git("init", "-b", "main", cwd=repo)
        git("config", "user.email", "ci@example.invalid", cwd=repo)
        git("config", "user.name", "CI", cwd=repo)
        fixed_date = {"GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z"}
        (repo / "main.txt").write_text("main\n", encoding="utf-8")
        git("add", "main.txt", cwd=repo)
        git_with_env("commit", "-m", "main", cwd=repo, env=fixed_date)
        git("remote", "add", "origin", str(remote), cwd=repo)
        git("push", "-u", "origin", "main", cwd=repo)
        git("checkout", "--orphan", "worker", cwd=repo)
        git("rm", "-rf", ".", cwd=repo)
        (repo / "worker.txt").write_text("worker\n", encoding="utf-8")
        git("add", "worker.txt", cwd=repo)
        git_with_env("commit", "-m", "worker", cwd=repo, env=fixed_date)
        (repo / ".github" / "scripts").mkdir(parents=True)
        shutil.copy2(RESOLVER, repo / ".github" / "scripts" / RESOLVER.name)
        unrelated_head = git("rev-parse", "HEAD", cwd=repo)
        expect_blocked(
            "RESOLVER_MERGE_BASE_FAILURE",
            {"GITHUB_SHA": unrelated_head, "EVENT_NAME": "workflow_dispatch", "DEFAULT_BRANCH": "main"},
            f"unable to determine merge-base for {unrelated_head} and origin/main",
            cwd=repo,
        )
    print("RESOLVER_TESTS=PASS")


def scope_check() -> None:
    paths = git("diff", "--name-only", "origin/main...HEAD").splitlines()
    allowed_exact = {
        "AGENTS.md", "GAP.md", "PRODUCT.md", "README.md", "WORKFLOW.md",
        "server/AGENTS.md", "android_collector/AGENTS.md", "web/AGENTS.md",
    }
    bad = [path for path in paths if not (path.startswith((".github/", "docs/")) or path in allowed_exact)]
    if bad:
        print("\n".join(bad))
        raise SystemExit(1)
    print(f"CHANGED_FILES={len(paths)}")
    print("SCOPE_STATIC=PASS")


CHECKS = {
    "markdown": markdown_check,
    "yaml": yaml_check,
    "ci": ci_static_check,
    "resolver": resolver_check,
    "scope": scope_check,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=[*CHECKS, "all"], required=True)
    args = parser.parse_args()
    selected = CHECKS.values() if args.check == "all" else [CHECKS[args.check]]
    for check in selected:
        check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
