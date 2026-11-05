#!/usr/bin/env bash
# install-git-hooks.sh — the git hooks of the core (setup/git-hooks) for a repository and its submodules
# (core.hooksPath, local to each repository).
#
#   bash "$(texo where)/setup/install-git-hooks.sh" [<repository>]     default: the repository of the current folder
#
# Idempotent. A repository whose core.hooksPath already points elsewhere is left as it is, and said.
set -euo pipefail

CORE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
HOOKS="$CORE/setup/git-hooks"
TARGET="${1:-$(git rev-parse --show-toplevel)}"
chmod +x "$HOOKS"/*

install_in() {
    local repo="$1" current
    current="$(git -C "$repo" config --local --get core.hooksPath || true)"
    if [ -n "$current" ] && [ "$current" != "$HOOKS" ]; then
        echo "skip  $repo (core.hooksPath is $current)"
        return
    fi
    git -C "$repo" config --local core.hooksPath "$HOOKS"
    echo "hooks $repo"
}

install_in "$TARGET"
while IFS= read -r sub; do
    [ -n "$sub" ] && install_in "$TARGET/$sub"
done < <(git -C "$TARGET" submodule --quiet foreach 'echo "$sm_path"' 2>/dev/null || true)
