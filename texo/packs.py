"""The skill packs of the marketplace: what a sector shares (skills, the seed of the hub, suggested threads).

The marketplace is one repository (texo_marketplace by default): packs/<name>/ holds a pack, its pack.toml, its
skills/ and its seed.toml; a release of a pack is the tag <name>-<version>. texo mount checks out only that folder
at that tag, once per machine, in $TEXO_SHARED_DIR/mirrors/pack-<name>-<version>.

    [pack]
    name = "odoo_partner"
    version = "v1.0.0"
    core = ">=2.0, <3"                  # the core it needs
    work_dirs = ["progetti"]            # working folders texo mount creates

    [[suggested_thread]]                # the threads the sector suggests: id, why, and a declaration to copy
    id = "odoo-20"
    why = "..."
"""
import tomllib

from . import threads
from .config import ConfigError


def thread_of(fabric, pack):
    """The pack as a git-mirror of the marketplace: its folder only, at its tag."""
    name, version = pack.get("name") or "", pack.get("version") or ""
    return {"id": f"pack-{name}-{version}", "type": "source", "driver": "git-mirror", "data_class": "public",
            "repo": fabric.marketplace, "ref": f"{name}-{version}", "paths": [f"packs/{name}"]}


def folder(fabric, pack):
    return threads.mirror_dir(thread_of(fabric, pack)) / "packs" / pack["name"]


def manifest(fabric, pack):
    path = folder(fabric, pack) / "pack.toml"
    if not path.is_file():
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: {error}") from None


def install(fabric, pack):
    return threads.mount_git_mirror(thread_of(fabric, pack))
