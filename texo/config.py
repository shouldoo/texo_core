"""The configuration of a working folder: texo.toml at its root, the configuration of the organisation in its hub,
credentials outside both.

    [texo]
    organisation = "acme"                       # the slug: ~/.config/texo/<slug>.env holds the credentials
    hub_url = "https://memoria.example.org"
    hub_token = "env:TEXO_HUB_TOKEN"            # never the value: the name of a variable
    marketplace = "github.com/shouldoo/texo_marketplace"   # optional: another marketplace

    [[pack]]                                    # optional: a pack the hub does not list, or another version
    name = "odoo_partner"
    version = "v1.0.0"

    [[thread]]                                  # optional: a thread the hub does not list, or a local variant
    id = "docs"
    ...

    [[hook]]                                    # optional, only here: a command the assistants run on an event
    id = "guard"
    event = "PreToolUse"
    matcher = "*"                               # optional
    command = "python3 {root}/guard.py"         # {root}: the working folder


The packs and threads come from the hub (route config, cached in .texo/config.json for when it does not answer);
those of texo.toml are added, or replace the hub's with the same name or id. The hooks come only from texo.toml:
a command that runs on the person's machine is never configured from the hub. `texo init` writes texo.toml.
A value written as env:NAME is read from the environment, else from ~/.config/texo/<organisation>.env (mode 600).
Outside a working folder, the CLI reads TEXO_HUB_URL and TEXO_HUB_TOKEN from the environment.
"""
import json
import os
import re
import stat
import tomllib
from pathlib import Path

from . import files

FILE = "texo.toml"
SLUG = re.compile(r"^[a-z][a-z0-9_]*$")
STATE_DIR = ".texo"
MARKETPLACE = "github.com/shouldoo/texo_marketplace"


class ConfigError(Exception):
    pass


def find_root(start=None):
    """The working folder that holds start (default: the current directory), or TEXO_ROOT; None outside one."""
    if os.environ.get("TEXO_ROOT"):
        root = Path(os.environ["TEXO_ROOT"]).expanduser().resolve()
        if not (root / FILE).is_file():
            raise ConfigError(f"TEXO_ROOT={root} has no {FILE}")
        return root
    path = Path(start or os.getcwd()).resolve()
    for candidate in (path, *path.parents):
        if (candidate / FILE).is_file():
            return candidate
    return None


def credentials_file(organisation):
    return Path(os.environ.get("TEXO_CONFIG_DIR", "~/.config/texo")).expanduser() / f"{organisation}.env"


def read_env_file(path):
    """KEY=value lines; a file others may read is refused, since it holds tokens."""
    values = {}
    if not path.is_file():
        return values
    if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigError(f"{path} is readable by others: chmod 600 {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def merge(remote, local, key, base=()):
    """The entries of the packs (base, each with its origin), then the hub's, then those of texo.toml: an entry
    with the same key replaces the one before."""
    merged = {entry.get(key): dict(entry) for entry in base}
    for entry in remote:
        merged[entry.get(key)] = dict(entry, origin="hub")
    for entry in local:
        merged[entry.get(key)] = dict(entry, origin="local")
    return list(merged.values())


class Fabric:
    """A working folder: its texo.toml, its root, the configuration of its organisation."""

    def __init__(self, root, remote=None):
        self.root = Path(root)
        try:
            self.data = tomllib.loads((self.root / FILE).read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(f"{self.root / FILE}: {error}") from None
        self.texo = self.data.get("texo") or {}
        # customer: the name of the key before the organisation lived in the hub
        self.organisation = self.texo.get("organisation") or self.texo.get("customer") or ""
        if not SLUG.match(self.organisation):
            raise ConfigError(f"{FILE}: [texo] organisation is one lowercase word (letters, digits, underscore)")
        self.remote = remote if remote is not None else self.cached_remote()
        self._env = None

    @property
    def marketplace(self):
        return self.texo.get("marketplace") or os.environ.get("TEXO_MARKETPLACE") or MARKETPLACE

    @property
    def packs(self):
        return merge(self.remote.get("packs") or [], self.data.get("pack") or [], "name")

    @property
    def threads(self):
        """The threads of the installed packs, then the hub's, then those of texo.toml."""
        from . import packs  # packs reads the configuration: imported here, not at the top
        return merge(self.remote.get("threads") or [], self.data.get("thread") or [], "id",
                     base=[thread for pack in self.packs for thread in packs.carried_threads(self, pack)])

    @property
    def hooks(self):
        """The [[hook]] of texo.toml, never the hub's: what runs on the machine is decided on the machine."""
        return [dict(hook) for hook in self.data.get("hook") or []]

    @property
    def state_dir(self):
        return self.root / STATE_DIR

    def cached_remote(self):
        try:
            return json.loads((self.state_dir / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_remote(self, remote):
        self.remote = remote
        self.state_dir.mkdir(exist_ok=True)
        files.write_text(self.state_dir / "config.json", json.dumps(remote, indent=2) + "\n")

    def secret(self, reference):
        """The value of an env:NAME reference, from the environment or the credentials of the organisation."""
        if not isinstance(reference, str) or not reference.startswith("env:"):
            raise ConfigError(f"a credential is written as env:NAME, never as its value ({FILE})")
        name = reference[4:]
        if os.environ.get(name):
            return os.environ[name]
        if self._env is None:
            self._env = read_env_file(credentials_file(self.organisation))
        if self._env.get(name):
            return self._env[name]
        raise ConfigError(f"{name} is not set: export it or add it to {credentials_file(self.organisation)} (mode 600)")

    def has_secret(self, reference):
        try:
            self.secret(reference)
        except ConfigError:
            return False
        return True

    def hub(self):
        """(url, token) of the hub of the organisation."""
        url = self.texo.get("hub_url")
        if not url:
            raise ConfigError(f"{self.root / FILE}: [texo] hub_url is missing")
        from . import environment  # environment reads the configuration: imported here, not at the top
        if environment.has_key(self.organisation):
            # a machine with a key of its own proves it and holds a short-lived token: no other is used
            return url, environment.token(url, self.organisation)
        return url, self.secret(self.texo.get("hub_token") or "env:TEXO_HUB_TOKEN")

    def renewal(self):
        """How a client that lives longer than its token gets another: a function of the token the hub just
        refused, or None where the token is a long-lived one the person keeps."""
        from . import environment
        url = self.texo.get("hub_url")
        if not url or not environment.has_key(self.organisation):
            return None
        return lambda stale: environment.token(url, self.organisation, stale=stale)


def hub_settings(start=None):
    """(url, token) of the hub: the working folder's, else TEXO_HUB_URL and TEXO_HUB_TOKEN."""
    root = find_root(start)
    if root:
        return Fabric(root).hub()
    url, token = os.environ.get("TEXO_HUB_URL"), os.environ.get("TEXO_HUB_TOKEN")
    if not (url and token):
        raise ConfigError(f"no {FILE} above the current directory and no TEXO_HUB_URL and TEXO_HUB_TOKEN")
    return url, token


def write_texo_toml(root, organisation, hub_url):
    """The texo.toml of `texo init`: the hub and the name of the organisation, nothing else."""
    if not SLUG.match(organisation or ""):
        raise ConfigError("the organisation is one lowercase word (letters, digits, underscore)")
    path = Path(root) / FILE
    if path.exists():
        raise ConfigError(f"{path} exists: edit it, or remove it to start again")
    path.write_text(
        "# The working folder of a Texo organisation: its packs and threads come from the hub (texo mount).\n"
        "[texo]\n"
        f'organisation = "{organisation}"\n'
        f'hub_url = "{hub_url.rstrip("/")}"\n'
        'hub_token = "env:TEXO_HUB_TOKEN"\n', encoding="utf-8")
    return path
