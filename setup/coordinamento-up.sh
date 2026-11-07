#!/usr/bin/env bash
# coordinamento-up.sh — create or refresh the local coordination Odoo of a fabric (the home of the memory),
# outside git, in $TEXO_STACK (default ~/.local/share/texo/coordinamento), from setup/templates/coordinamento/.
#
#   bash core/setup/coordinamento-up.sh        create the stack (secrets only when missing), build, start
#
# The modules come from a release of texo_hub: TEXO_HUB_REF (default 20.0.1.5.0) is cloned into the stack and
# mounted read-only; a new value checks the new release out. Idempotent: Dockerfile and docker-compose.yml are
# copied again; odoo.conf and pg_password are generated once and never printed; the ports and the release chosen in
# $TEXO_STACK/.env are kept. Databases are created afterwards, with the commands of
# playbooks/coordinamento-locale.md: this script never touches a database.
set -euo pipefail

CORE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
TPL="${CORE}/setup/templates/coordinamento"
S="${TEXO_STACK:-${HOME}/.local/share/texo/coordinamento}"
HUB_REPO="${TEXO_HUB_REPO:-https://github.com/shouldoo/texo_hub.git}"
IMAGE=texo-coordinamento:20.0

for tool in docker git openssl; do
    command -v "$tool" >/dev/null || { echo "[fatal] $tool is missing" >&2; exit 2; }
done
mkdir -p "${S}/filestore" "${S}/backups"
chmod 700 "$S"     # the secrets below are readable by the containers, not by other users of the host
cp "${TPL}/Dockerfile" "${TPL}/docker-compose.yml" "$S/"

# .env: the choices of the person stay, the missing ones get their default
touch "${S}/.env"
for setting in TEXO_HUB_REF=20.0.1.5.0 TEXO_WEB_PORT=8069 TEXO_LONGPOLL_PORT=8072 TEXO_TEI_PORT=8080; do
    grep -q "^${setting%%=*}=" "${S}/.env" || echo "$setting" >> "${S}/.env"
done
[ -z "${TEXO_HUB_REF:-}" ] || sed -i "s|^TEXO_HUB_REF=.*|TEXO_HUB_REF=${TEXO_HUB_REF}|" "${S}/.env"
REF="$(sed -n 's/^TEXO_HUB_REF=//p' "${S}/.env")"

if [ ! -d "${S}/texo_hub/.git" ]; then
    git clone --quiet --depth 1 --branch "$REF" "$HUB_REPO" "${S}/texo_hub"
elif [ "$(git -C "${S}/texo_hub" describe --tags --exact-match 2>/dev/null || true)" != "$REF" ]; then
    git -C "${S}/texo_hub" fetch --quiet --depth 1 origin "refs/tags/${REF}:refs/tags/${REF}"
    git -C "${S}/texo_hub" checkout --quiet "$REF"
fi
echo "[ok] texo_hub ${REF}"

if [ ! -f "${S}/pg_password" ]; then
    (umask 022; openssl rand -hex 24 > "${S}/pg_password")    # read by the postgres user of its image
    echo "[ok] pg_password generated"
fi
if [ ! -f "${S}/odoo.conf" ]; then
    # odoo.conf: mode 640, group 101, the odoo user of the image (uid 100, gid 101)
    (umask 027
     sed -e "s/@DB_PASSWORD@/$(cat "${S}/pg_password")/" -e "s/@ADMIN_PASSWD@/$(openssl rand -hex 24)/" \
         "${TPL}/odoo.conf.template" > "${S}/odoo.conf")
    chgrp 101 "${S}/odoo.conf" 2>/dev/null || \
        docker run --rm --user root --entrypoint chgrp -v "${S}:/s" "$IMAGE" 101 /s/odoo.conf 2>/dev/null || true
    echo "[ok] odoo.conf generated"
fi

docker compose -f "${S}/docker-compose.yml" build -q web
# filestore and backups belong to the odoo user of the image: a throw-away root container, no sudo
docker run --rm --user root --entrypoint chown -v "${S}:/s" "$IMAGE" -R 100:101 /s/filestore /s/backups
docker run --rm --user root --entrypoint chgrp -v "${S}:/s" "$IMAGE" 101 /s/odoo.conf
docker compose -f "${S}/docker-compose.yml" up -d
docker compose -f "${S}/docker-compose.yml" ps
PORT="$(sed -n 's/^TEXO_WEB_PORT=//p' "${S}/.env")"
echo "[ok] coordination Odoo on http://coord.localhost:${PORT} (create the databases: core/playbooks/coordinamento-locale.md)"
