"""The skill packs of the marketplace: what a sector shares (skills, the seed of the hub, suggested threads).

The marketplace is one repository (texo_marketplace by default): packs/<name>/ holds a pack, its pack.toml, its
skills/ and its seed.toml; a release of a pack is the tag <name>-<version>. texo mount checks out only that folder
at that tag, once per machine, in $TEXO_SHARED_DIR/mirrors/pack-<name>-<version>.

    [pack]
    name = "odoo_partner"
    version = "v1.0.0"
    core = ">=2.0, <3"                  # the core it needs
    work_dirs = ["progetti"]            # working folders texo mount creates

    [[thread]]                          # the threads the pack carries: part of its method, pinned by its version
    id = "odoo-skills"                  # public sources only (git-mirror or git-remote, data_class public);
    ...                                 # the hub replaces one by declaring a thread with the same id

    [[suggested_thread]]                # the threads the sector suggests: id, why, and a declaration to copy
    id = "odoo-20"
    why = "..."

A pack under development on this machine is declared in texo.toml with its folder (path = "/.../packs/<name>",
with the version its pack.toml carries): nothing is checked out, the folder is used as it is. For the people who
write a pack and load its demo; never in the hub, which knows only released packs.
"""
import pathlib
import tomllib

from . import threads
from .config import ConfigError


def thread_of(fabric, pack):
    """The pack as a git-mirror of the marketplace: its folder only, at its tag."""
    name, version = pack.get("name") or "", pack.get("version") or ""
    return {"id": f"pack-{name}-{version}", "type": "source", "driver": "git-mirror", "data_class": "public",
            "repo": fabric.marketplace, "ref": f"{name}-{version}", "paths": [f"packs/{name}"]}


def folder(fabric, pack):
    """The folder of the pack on this machine: the checkout of its tag, or its path when it is under development."""
    if pack.get("path"):
        return pathlib.Path(pack["path"]).expanduser()
    return threads.mirror_dir(thread_of(fabric, pack)) / "packs" / pack["name"]


def manifest(fabric, pack):
    path = folder(fabric, pack) / "pack.toml"
    if not path.is_file():
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: {error}") from None


PACK_DRIVERS = ("git-mirror", "git-remote")


def carried_threads(fabric, pack):
    """The threads an installed pack carries, each with its origin; none before the pack is installed."""
    try:
        data = manifest(fabric, pack)
    except ConfigError:
        return []
    return [dict(thread, origin=f"pack {pack.get('name')}") for thread in (data or {}).get("thread") or []]


def thread_problems(thread):
    """What a pack may not carry: only public, read-only sources; a tool, a connector or a credential is the
    choice of the administrators of the hub."""
    if (thread.get("type") != "source" or thread.get("driver") not in PACK_DRIVERS
            or thread.get("data_class") != "public" or thread.get("auth") or thread.get("env")):
        return [("error", f"{thread.get('id')}: a {thread.get('origin')} carries only public sources "
                          f"({' or '.join(PACK_DRIVERS)}, data_class public, no credential): declare it in the hub")]
    return []


def install(fabric, pack):
    if pack.get("path"):
        path = folder(fabric, pack)
        if (path / "pack.toml").is_file():
            return "ok", f"a pack under development, used as it is: {path}"
        return "error", f"no pack.toml in {path}"
    return threads.mount_git_mirror(thread_of(fabric, pack))
