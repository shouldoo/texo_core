#!/usr/bin/env bash
# load-demo.sh — load the demo customer of this fabric into a test database of the local coordination Odoo.
#
#   bash core/setup/load-demo.sh <database> [--create]      from the root of a demo customer repository
#
# --create makes the database and installs the modules of the hub first. The data are the fabric's demo/data.py
# (fictional only: it names the databases it accepts), the texts of its documents demo/texts/*.md, and the
# hub/seed.toml of its industries, applied first (scripts/load_demo.py). The tokens the load generates go to
# ~/.config/texo/<customer>.env (mode 600, never printed: TEXO_HUB_TOKEN is the lead's, TEXO_HUB_TOKEN_<ROLE>
# the others'), the question set with the ids of the database to .texo/eval-<database>.json. Idempotent.
set -euo pipefail

CORE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
ROOT="$(git -C "$CORE/.." rev-parse --show-toplevel)"
DB="${1:?usage: load-demo.sh <database> [--create]}"
S="${TEXO_STACK:-${HOME}/.local/share/texo/coordinamento}"
C=(docker compose -f "${S}/docker-compose.yml")
MODULES="${TEXO_DEMO_MODULES:-texo,texo_project,texo_memory,texo_timesheet,texo_mcp,texo_vector}"

[ -f "${ROOT}/texo.toml" ] && [ -f "${ROOT}/demo/data.py" ] || {
    echo "[error] run it from a demo customer repository: texo.toml and demo/data.py at ${ROOT}" >&2; exit 1; }
[ -f "${S}/docker-compose.yml" ] || { echo "[error] no coordination stack in ${S}: setup/coordinamento-up.sh" >&2; exit 1; }
CUSTOMER="$(python3 -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["texo"]["customer"])' "${ROOT}/texo.toml")"

if [ "${2:-}" = "--create" ]; then
    echo "--> database ${DB}"
    "${C[@]}" run --rm -T --no-deps --entrypoint odoo web db -c /etc/odoo/odoo.conf init "$DB" --country it --language it_IT
    "${C[@]}" run --rm -T --no-deps --entrypoint odoo web -c /etc/odoo/odoo.conf -d "$DB" --db-filter "^${DB}\$" \
        -i "$MODULES" --stop-after-init --log-level=warn
fi

PROGRAM="$(mktemp)"
trap 'rm -f "$PROGRAM"' EXIT
# SEEDS and TEXTS, then the data, then the logic: one program for odoo shell
PYTHONPATH="$CORE" python3 - "$ROOT" > "$PROGRAM" <<'PY'
import json
import pathlib
import sys

from texo import seed
from texo.config import Fabric

fabric = Fabric(sys.argv[1])
seeds = [p for p in (seed.payload(fabric, industry) for industry in fabric.industries) if p]
texts = {path.stem: path.read_text(encoding="utf-8")
         for path in sorted((fabric.root / "demo" / "texts").glob("*.md"))}
print(f"SEEDS = {json.dumps(seeds, ensure_ascii=False)!r}")
print("SEEDS = __import__('json').loads(SEEDS)")
print(f"TEXTS = {json.dumps(texts, ensure_ascii=False)!r}")
print("TEXTS = __import__('json').loads(TEXTS)")
PY
cat "${ROOT}/demo/data.py" "${CORE}/scripts/load_demo.py" >> "$PROGRAM"

ENV_FILE="${HOME}/.config/texo/${CUSTOMER}.env"
mkdir -p "$(dirname "$ENV_FILE")" "${ROOT}/.texo"
chmod 700 "$(dirname "$ENV_FILE")"
umask 077
TOKENS="$(mktemp)"
trap 'rm -f "$PROGRAM" "$TOKENS"' EXIT
"${C[@]}" exec -T web odoo shell -c /etc/odoo/odoo.conf -d "$DB" --no-http --log-level=warn < "$PROGRAM" |
while IFS= read -r line; do
    case "$line" in
        "@@TOKEN "*)
            read -r _ role key <<< "$line"
            if [ "$role" = lead ]; then name=TEXO_HUB_TOKEN; else name="TEXO_HUB_TOKEN_${role^^}"; fi
            printf '%s=%s\n' "$name" "$key" >> "$TOKENS"
            echo "[ok] token ${role} -> ${name}" ;;
        "@@EVAL "*)
            printf '%s\n' "${line#@@EVAL }" > "${ROOT}/.texo/eval-${DB}.json"
            echo "[ok] question set -> .texo/eval-${DB}.json" ;;
        *) printf '%s\n' "$line" ;;
    esac
done
if [ -s "$TOKENS" ]; then
    # the tokens of this load replace the previous ones; other lines of the file stay
    { grep -v '^TEXO_HUB_TOKEN' "$ENV_FILE" 2>/dev/null || true; cat "$TOKENS"; } > "${ENV_FILE}.new"
    mv "${ENV_FILE}.new" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "[ok] tokens -> ${ENV_FILE}"
fi
