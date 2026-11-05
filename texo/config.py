"""The configuration of a fabric: texo.toml at the root of a customer repository, credentials outside git.

    [texo]
    customer = "shouldoo"                       # the slug: ~/.config/texo/<customer>.env holds its credentials
    core = "v1.0.0"                             # the tag of texo_core mounted in core/
    hub_url = "https://memoria.example.org"
    hub_token = "env:TEXO_HUB_TOKEN"            # never the value: the name of a variable

    [[industry]]
    name = "odoo_partner"
    version = "v1.0.0"                          # the tag of texo_industry_<name> mounted in industry/<name>/

    [[thread]]                                  # texo/threads.py
    id = "normativa"
    ...

A value written as env:NAME is read from the environment, else from ~/.config/texo/<customer>.env (mode 600).
Outside a fabric, the CLI reads TEXO_HUB_URL and TEXO_HUB_TOKEN from the environment.
"""
import os
import re
import stat
import tomllib
from pathlib import Path

FILE = "texo.toml"
SLUG = re.compile(r"^[a-z][a-z0-9_]*$")
STATE_DIR = ".texo"


class ConfigError(Exception):
    pass


def find_root(start=None):
    """The fabric that holds start (default: the current directory), or TEXO_ROOT; None outside one."""
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


def credentials_file(customer):
    return Path(os.environ.get("TEXO_CONFIG_DIR", "~/.config/texo")).expanduser() / f"{customer}.env"


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


class Fabric:
    """A customer repository: its texo.toml, its root, the credentials of its customer."""

    def __init__(self, root):
        self.root = Path(root)
        try:
            self.data = tomllib.loads((self.root / FILE).read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(f"{self.root / FILE}: {error}") from None
        self.texo = self.data.get("texo") or {}
        self.customer = self.texo.get("customer") or ""
        if not SLUG.match(self.customer):
            raise ConfigError(f"{FILE}: [texo] customer is one lowercase word (letters, digits, underscore)")
        self._env = None

    @property
    def industries(self):
        return self.data.get("industry") or []

    @property
    def threads(self):
        return self.data.get("thread") or []

    @property
    def state_dir(self):
        return self.root / STATE_DIR

    def industry_dir(self, industry):
        return self.root / (industry.get("path") or f"industry/{industry['name']}")

    def secret(self, reference):
        """The value of an env:NAME reference, from the environment or the credentials of the customer."""
        if not isinstance(reference, str) or not reference.startswith("env:"):
            raise ConfigError(f"a credential is written as env:NAME, never as its value ({FILE})")
        name = reference[4:]
        if os.environ.get(name):
            return os.environ[name]
        if self._env is None:
            self._env = read_env_file(credentials_file(self.customer))
        if self._env.get(name):
            return self._env[name]
        raise ConfigError(f"{name} is not set: export it or add it to {credentials_file(self.customer)} (mode 600)")

    def has_secret(self, reference):
        try:
            self.secret(reference)
        except ConfigError:
            return False
        return True


def hub_settings(start=None):
    """(url, token) of the hub: the fabric's, else TEXO_HUB_URL and TEXO_HUB_TOKEN."""
    root = find_root(start)
    if root:
        fabric = Fabric(root)
        url = fabric.texo.get("hub_url")
        if not url:
            raise ConfigError(f"{root / FILE}: [texo] hub_url is missing")
        return url, fabric.secret(fabric.texo.get("hub_token") or "env:TEXO_HUB_TOKEN")
    url, token = os.environ.get("TEXO_HUB_URL"), os.environ.get("TEXO_HUB_TOKEN")
    if not (url and token):
        raise ConfigError(f"no {FILE} above the current directory and no TEXO_HUB_URL and TEXO_HUB_TOKEN")
    return url, token
