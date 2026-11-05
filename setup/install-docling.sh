#!/usr/bin/env bash
# install-docling.sh — Docling in its own virtualenv, for scripts/ingest.py.
#
#   bash setup/install-docling.sh              # install or update, then prefetch the models
#   bash setup/install-docling.sh --status     # is it there, and which version
#
# Docling converts PDF, Office, HTML, images and e-mails to Markdown on this machine, with no
# remote service. It is heavy (PyTorch and the layout models): a CPU is enough, a GPU is
# optional. Python 3.10 to 3.13; about 10 GB of disk for the venv and the models.
# The venv lives outside the repository: ~/.local/share/texo/docling.
set -euo pipefail

VENV="${DOCLING_VENV:-$HOME/.local/share/texo/docling}"
PYTHON="${PYTHON:-python3}"

if [ "${1:-}" = "--status" ]; then
    if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import docling" 2>/dev/null; then
        echo "[ok] docling $("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("docling"))') in $VENV"
        ls "${HOME}/.cache/docling/models" >/dev/null 2>&1 && echo "[ok] models in ~/.cache/docling/models" || echo "[info] models not prefetched yet (downloaded at first use)"
    else
        echo "[info] docling not installed: bash setup/install-docling.sh"
    fi
    exit 0
fi

version="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
case "$version" in
    3.10|3.11|3.12|3.13) ;;
    *) echo "[error] docling needs Python 3.10 to 3.13, found $version: set PYTHON=/path/to/python3.12"; exit 1 ;;
esac

echo "--> venv $VENV"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
echo "--> docling (this downloads PyTorch: minutes, gigabytes)"
"$VENV/bin/pip" install --quiet --upgrade docling
echo "--> models (layout, tables, OCR), into ~/.cache/docling/models"
"$VENV/bin/docling-tools" models download || echo "[warn] models not prefetched: they will be downloaded at first use"
echo "[ok] docling $("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("docling"))'). Try: python3 scripts/ingest.py <file> --project <id>"
