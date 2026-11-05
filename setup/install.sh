#!/usr/bin/env bash
# install.sh — install or update the texo CLI on this machine, for the person who works on it.
#
#   curl -fsSL https://raw.githubusercontent.com/shouldoo/texo_core/main/setup/install.sh | bash
#   TEXO_VERSION=v2.0.0 bash setup/install.sh          a given release (default: the latest tag)
#
# The core is checked out at a release tag in ${TEXO_HOME:-~/.local/share/texo/core} and the command texo is
# linked in ~/.local/bin. Requires git and python3 3.11 or later. Then, in a working folder of the organisation:
# texo init <hub url> <organisation>.
set -euo pipefail

REPO="${TEXO_REPO:-https://github.com/shouldoo/texo_core.git}"
HOME_DIR="${TEXO_HOME:-${HOME}/.local/share/texo/core}"
BIN_DIR="${HOME}/.local/bin"

for tool in git python3; do
    command -v "$tool" >/dev/null || { echo "[error] $tool is missing" >&2; exit 1; }
done
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "[error] python3 3.11 or later is needed" >&2; exit 1; }
VERSION="${TEXO_VERSION:-$(git ls-remote --tags --refs --sort=-v:refname "$REPO" 'v*' | head -1 | sed 's|.*refs/tags/||')}"
[ -n "$VERSION" ] || { echo "[error] no release found in $REPO" >&2; exit 1; }

if [ -d "${HOME_DIR}/.git" ]; then
    git -C "$HOME_DIR" fetch --quiet --depth 1 origin "refs/tags/${VERSION}:refs/tags/${VERSION}"
    git -C "$HOME_DIR" checkout --quiet "$VERSION"
else
    mkdir -p "$(dirname "$HOME_DIR")"
    git clone --quiet --depth 1 --branch "$VERSION" "$REPO" "$HOME_DIR"
fi
mkdir -p "$BIN_DIR"
ln -sfn "${HOME_DIR}/bin/texo" "${BIN_DIR}/texo"
echo "[ok] texo ${VERSION} in ${HOME_DIR}, command ${BIN_DIR}/texo"
case ":${PATH}:" in *":${BIN_DIR}:"*) ;; *) echo "[info] add ${BIN_DIR} to PATH" ;; esac
