#!/usr/bin/env bash
set -u -o pipefail

blocked() {
  echo "BLOCKED: $1" >&2
  exit 2
}

event_name="${EVENT_NAME:-}"
head_input="${GITHUB_SHA:-HEAD}"

head_sha="$(git rev-parse --verify "${head_input}^{commit}" 2>/dev/null)" || \
  blocked "head commit is missing or invalid: ${head_input}"

case "$event_name" in
  pull_request)
    base_input="${PR_BASE_SHA:-}"
    [[ -n "$base_input" ]] || blocked "pull_request base SHA is empty"
    base_sha="$(git rev-parse --verify "${base_input}^{commit}" 2>/dev/null)" || \
      blocked "pull_request base commit is missing or invalid: ${base_input}"
    ;;
  push)
    base_input="${PUSH_BEFORE_SHA:-}"
    if [[ -n "$base_input" && ! "$base_input" =~ ^0+$ ]]; then
      base_sha="$(git rev-parse --verify "${base_input}^{commit}" 2>/dev/null)" || \
        blocked "push before commit is missing or invalid: ${base_input}"
    else
      default_branch="${DEFAULT_BRANCH:-}"
      [[ -n "$default_branch" ]] || blocked "default branch is empty for zero-before push"
      git fetch --no-tags origin "$default_branch" >/dev/null 2>&1 || \
        blocked "unable to fetch default branch: ${default_branch}"
      default_sha="$(git rev-parse --verify "origin/${default_branch}^{commit}" 2>/dev/null)" || \
        blocked "fetched default branch commit is missing or invalid: origin/${default_branch}"
      base_sha="$(git merge-base "$head_sha" "$default_sha" 2>/dev/null)" || \
        blocked "unable to determine merge-base for ${head_sha} and origin/${default_branch}"
    fi
    ;;
  workflow_dispatch)
    default_branch="${DEFAULT_BRANCH:-}"
    [[ -n "$default_branch" ]] || blocked "default branch is empty for workflow_dispatch"
    git fetch --no-tags origin "$default_branch" >/dev/null 2>&1 || \
      blocked "unable to fetch default branch: ${default_branch}"
    default_sha="$(git rev-parse --verify "origin/${default_branch}^{commit}" 2>/dev/null)" || \
      blocked "fetched default branch commit is missing or invalid: origin/${default_branch}"
    base_sha="$(git merge-base "$head_sha" "$default_sha" 2>/dev/null)" || \
      blocked "unable to determine merge-base for ${head_sha} and origin/${default_branch}"
    ;;
  *)
    blocked "unsupported event for diff base: ${event_name:-<empty>}"
    ;;
esac

git cat-file -e "${base_sha}^{commit}" 2>/dev/null || \
  blocked "resolved base commit does not exist: ${base_sha}"

printf '%s\n' "$base_sha"
