#!/usr/bin/env bash
# =============================================================
# bootstrap.sh — prepare a customer repository (a fabric) for the person who works in it.
#
#   bash core/setup/bootstrap.sh            from the root of the customer repository
#
# Non-interactive and idempotent. Requires bash, git and python3 (3.11 or later).
#   - the submodules (core, industries) at the commits the customer repository records;
#   - the git hooks of core/setup/git-hooks for the repository and its submodules (no commit names an
#     AI assistant as author);
#   - Claude Code: trusts the folder (~/.claude.json, merged);
#   - Antigravity, if agy is installed: a profile of its own for this customer (~/.antigravity-texo-<customer>);
#   - texo mount: the threads, the MCP configuration of every assistant, the skills, .texo/THREADS.md.
# No credential is asked or written: the hub token and the credentials of the threads go in
# ~/.config/texo/<customer>.env (mode 600), then `core/bin/texo doctor`.
# =============================================================
set -euo pipefail

CORE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
ROOT="$(git -C "$CORE/.." rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/texo.toml" ]; then
    echo "[error] run it from a customer repository: no texo.toml at the root above $CORE" >&2
    exit 1
fi
cd "$ROOT"

MISSING=()
for tool in git python3; do
    command -v "$tool" &>/dev/null || MISSING+=("$tool")
done
[ ${#MISSING[@]} -eq 0 ] || { echo "[error] missing tools: ${MISSING[*]}" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "[error] python3 3.11 or later is needed" >&2; exit 1; }
if [ "$(id -u)" -eq 0 ]; then
    echo "[error] do not run as root: the fabric belongs to the person who works in it" >&2
    exit 1
fi

echo "--> Fabric: ${ROOT}"
git submodule update --init --recursive
echo "[ok] submodules"
bash "$CORE/setup/install-git-hooks.sh" "$ROOT"

# Claude Code: trust this folder (merge into ~/.claude.json, never overwrite)
ROOT="$ROOT" python3 - <<'PYEOF'
import json
import os

path = os.path.expanduser("~/.claude.json")
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except (OSError, ValueError):
    data = {}
data.setdefault("projects", {}).setdefault(os.environ["ROOT"], {})["hasTrustDialogAccepted"] = True
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
os.chmod(path, 0o600)
PYEOF
echo "[ok] Claude Code: folder trusted"

# Antigravity: a profile of its own for this customer (login, state, MCP servers, trusted folders). It reads AGENTS.md
# and .agents/skills natively; its MCP servers come from the profile, which texo mount fills.
CUSTOMER="$(python3 -c 'import tomllib; print(tomllib.load(open("texo.toml", "rb"))["texo"]["customer"])')"
if command -v agy &>/dev/null || command -v antigravity &>/dev/null; then
    PROFILE="${TEXO_AGY_PROFILE:-${HOME}/.antigravity-texo-${CUSTOMER}}"
    mkdir -p "$PROFILE/.gemini/config" "$PROFILE/.gemini/antigravity-cli"
    chmod 700 "$PROFILE"
    for item in .gitconfig .ssh .local .config; do
        if [ -e "${HOME}/${item}" ] && [ ! -e "${PROFILE}/${item}" ]; then
            ln -s "${HOME}/${item}" "${PROFILE}/${item}"
        fi
    done
    PROFILE="$PROFILE" ROOT="$ROOT" python3 - <<'PYEOF'
import json
import os

path = os.path.join(os.environ["PROFILE"], ".gemini", "antigravity-cli", "settings.json")
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except (OSError, ValueError):
    data = {}
trusted = data.setdefault("trustedWorkspaces", [])
if os.environ["ROOT"] not in trusted:
    trusted.append(os.environ["ROOT"])
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PYEOF
    export TEXO_AGY_PROFILE="$PROFILE"
    echo "[ok] Antigravity profile ${PROFILE} (log in once with: HOME=\"${PROFILE}\" agy)"
fi

"$CORE/bin/texo" --root "$ROOT" mount
CREDENTIALS="${HOME}/.config/texo/${CUSTOMER}.env"
[ -f "$CREDENTIALS" ] || echo "[info] no ${CREDENTIALS}: create it (mode 600) with the hub token, then core/bin/texo doctor"
echo "[ok] Bootstrap complete. Start the assistants from ${ROOT}."
