#!/usr/bin/env bash
# load-demo.sh — load the demo of a skill pack into a test database of the local coordination Odoo.
#
#   bash "$(texo where)/setup/load-demo.sh" <pack> <database> [--create]     from a working folder
#
# --create makes the database and installs the modules of the hub first. The data are the pack's demo/data.py
# (fictional only: it names the databases it accepts), the texts of its documents demo/texts/*.md, and the pack's
# seed.toml, applied first (scripts/load_demo.py). The tokens the load generates go to
# ~/.config/texo/<organisation>.env (mode 600, never printed: TEXO_HUB_TOKEN is the lead's, TEXO_HUB_TOKEN_<ROLE>
# the others'), the question set with the ids of the database to .texo/eval-<database>.json. Idempotent.
# The vectors (texo_vector): the tei service of the stack, or the one named by TEXO_VECTOR_ENDPOINT and TEXO_VECTOR_API
# (tei or llamacpp: llama.cpp server on a GPU through Vulkan, playbooks/coordinamento-locale.md).
set -euo pipefail

CORE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
ROOT="$(pwd)"
PACK="${1:?usage: load-demo.sh <pack> <database> [--create]}"
DB="${2:?usage: load-demo.sh <pack> <database> [--create]}"
S="${TEXO_STACK:-${HOME}/.local/share/texo/coordinamento}"
C=(docker compose -f "${S}/docker-compose.yml")
MODULES="${TEXO_DEMO_MODULES:-texo,texo_project,texo_memory,texo_timesheet,texo_mcp,texo_vector}"

[ -f "${ROOT}/texo.toml" ] || { echo "[error] run it from a working folder (texo init): no texo.toml in ${ROOT}" >&2; exit 1; }
PACK_DIR="$("$CORE/bin/texo" --root "$ROOT" where --pack "$PACK")"
[ -f "${PACK_DIR}/demo/data.py" ] || { echo "[error] the pack ${PACK} has no demo/data.py (texo mount installs it)" >&2; exit 1; }
[ -f "${S}/docker-compose.yml" ] || { echo "[error] no coordination stack in ${S}: setup/coordinamento-up.sh" >&2; exit 1; }
ORGANISATION="$(PYTHONPATH="$CORE" python3 -c 'import sys; from texo.config import Fabric; print(Fabric(sys.argv[1]).organisation)' "$ROOT")"

if [ "${3:-}" = "--create" ]; then
    echo "--> database ${DB}"
    "${C[@]}" run --rm -T --no-deps --entrypoint odoo web db -c /etc/odoo/odoo.conf init "$DB" --country it --language it_IT
    "${C[@]}" run --rm -T --no-deps --entrypoint odoo web -c /etc/odoo/odoo.conf -d "$DB" --db-filter "^${DB}\$" \
        -i "$MODULES" --stop-after-init --log-level=warn
fi

PROGRAM="$(mktemp)"
trap 'rm -f "$PROGRAM"' EXIT
# SEEDS and TEXTS, then the data, then the logic: one program for odoo shell
PYTHONPATH="$CORE" python3 - "$ROOT" "$PACK" "$PACK_DIR" > "$PROGRAM" <<'PY'
import json
import os
import pathlib
import sys

from texo import seed
from texo.config import Fabric

fabric = Fabric(sys.argv[1])
pack = next(p for p in fabric.packs if p.get("name") == sys.argv[2])
seeds = [p for p in [seed.payload(fabric, pack)] if p]
texts = {path.stem: path.read_text(encoding="utf-8")
         for path in sorted((pathlib.Path(sys.argv[3]) / "demo" / "texts").glob("*.md"))}
print(f"SEEDS = {json.dumps(seeds, ensure_ascii=False)!r}")
print("SEEDS = __import__('json').loads(SEEDS)")
print(f"TEXTS = {json.dumps(texts, ensure_ascii=False)!r}")
print("TEXTS = __import__('json').loads(TEXTS)")
vector = {key: os.environ[name] for key, name in (("endpoint", "TEXO_VECTOR_ENDPOINT"), ("api", "TEXO_VECTOR_API"))
          if os.environ.get(name)}
print(f"VECTOR = {json.dumps(vector)!r}")
print("VECTOR = __import__('json').loads(VECTOR)")
PY
cat "${PACK_DIR}/demo/data.py" "${CORE}/scripts/load_demo.py" >> "$PROGRAM"

ENV_FILE="${HOME}/.config/texo/${ORGANISATION}.env"
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
