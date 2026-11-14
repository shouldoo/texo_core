"""The environment of this machine: a key of its own, proved to the hub at every session.

A token kept in a file works from any machine it is copied to. Where the organisation registers its
environments, the machine holds an ed25519 key pair instead (made and used with ssh-keygen: the core stays on
the standard library). The person registers the public half once, from the browser, as themselves; from then
on the CLI and the MCP server sign a challenge of the hub and receive a token that expires in hours, kept in a
file only the person reads and renewed when it is about to expire or is refused. A long-lived token never
exists on the machine.

Next to the credentials file of the organisation (config.credentials_file), with the same name:

    <organisation>.key        the private key (mode 600), never sent anywhere
    <organisation>.key.pub    the public key: what the person registers
    <organisation>.token      the short-lived token, with its expiry (mode 600)

A private key in a file is copied like a token: who has the machine can clone the environment. What the
registry gives is a revocation per machine and a long-lived secret that never travels.
"""
import base64
import contextlib
import datetime
import hashlib
import json
import platform
import shutil
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from . import files
from .config import ConfigError, credentials_file
from .hub import Hub, HubError

try:
    import fcntl
except ImportError:  # no advisory locks on this system: two processes may both ask for a token
    fcntl = None

NAMESPACE = "texo-environment"
PAGE = "/texo/environment"
TIMEOUT = 30
# a token this close to its expiry is renewed before it is used
MARGIN = datetime.timedelta(minutes=10)


def key_path(organisation):
    return credentials_file(organisation).with_suffix(".key")


def token_path(organisation):
    return credentials_file(organisation).with_suffix(".token")


def has_key(organisation):
    return key_path(organisation).is_file()


def ssh_keygen():
    """The ssh-keygen of the machine, or a ConfigError that says what it is for."""
    path = shutil.which("ssh-keygen")
    if not path:
        raise ConfigError("ssh-keygen is not installed: the key of the environment is made and used with it "
                          "(OpenSSH 8.1 or later)")
    return path


def create_key(organisation):
    """Make the key pair of this machine for the organisation; an existing one is never replaced."""
    path = key_path(organisation)
    if path.exists():
        raise ConfigError(f"{path} exists: this machine already has a key for {organisation}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    result = subprocess.run([ssh_keygen(), "-q", "-t", "ed25519", "-N", "", "-C", f"texo-{organisation}",
                             "-f", str(path)], capture_output=True, text=True, timeout=TIMEOUT)
    if result.returncode:
        raise ConfigError(f"ssh-keygen could not make the key: {result.stderr.strip()[:200]}")
    path.chmod(0o600)
    return path


def public_key(organisation):
    """The public key of this machine, without its comment: what the hub is given."""
    path = key_path(organisation).with_name(key_path(organisation).name + ".pub")
    try:
        words = path.read_text(encoding="utf-8").split()
    except OSError:
        raise ConfigError(f"{path} is missing: texo environment register") from None
    if len(words) < 2 or words[0] != "ssh-ed25519":
        raise ConfigError(f"{path} is not an ed25519 public key")
    return " ".join(words[:2])


def fingerprint(key):
    """SHA256:<base64> of a public key line, as ssh-keygen -l prints it."""
    blob = base64.b64decode(key.split()[1])
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


def registration_url(hub_url, organisation):
    """Where the person registers this machine: the page of the hub, with the public key, a name and what the
    machine says of itself. Nothing in it is a secret."""
    host = socket.gethostname() or "machine"
    query = urllib.parse.urlencode({"key": public_key(organisation), "name": host,
                                    "declared": f"{host} {platform.system()} {platform.machine()}".strip()})
    return f"{hub_url.rstrip('/')}{PAGE}?{query}"


def sign(organisation, text):
    """The signature of text by the key of this machine, in the namespace of Texo (ssh-keygen -Y sign)."""
    result = subprocess.run([ssh_keygen(), "-Y", "sign", "-f", str(key_path(organisation)), "-n", NAMESPACE],
                            input=text, capture_output=True, text=True, timeout=TIMEOUT)
    if result.returncode or "BEGIN SSH SIGNATURE" not in result.stdout:
        raise ConfigError(f"ssh-keygen could not sign: {result.stderr.strip()[:200]}")
    return result.stdout


def post(hub_url, route, data, opener=None):
    """POST JSON to an open route of the hub: the answer, or a HubError with its status and message."""
    request = urllib.request.Request(f"{hub_url.rstrip('/')}{route}", data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "texo"}, method="POST")
    try:
        with (opener or urllib.request.urlopen)(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        error.close()
        try:
            message = json.loads(body).get("message") or body
        except (ValueError, AttributeError):
            message = body
        if error.code == 404:
            message = "this hub keeps no registry of environments (texo 20.0.1.7.0 or later)"
        raise HubError(error.code, (message or "").strip()[:300]) from None
    except urllib.error.URLError as error:
        raise HubError(0, f"Odoo not reachable at {hub_url}: {error.reason}") from None


def login(hub_url, organisation, opener=None):
    """Prove the key to the hub: a challenge, its signature, a short-lived token. {token, expires, login,
    environment}, or a HubError (403: not registered, not authorized yet, or revoked)."""
    print_ = fingerprint(public_key(organisation))
    challenge = post(hub_url, f"{PAGE}/challenge", {"fingerprint": print_}, opener)
    signature = sign(organisation, challenge.get("challenge") or "")
    answer = post(hub_url, f"{PAGE}/token", {"fingerprint": print_, "signature": signature}, opener)
    if not answer.get("token"):
        raise HubError(0, "the hub gave no token")
    return answer


def load_token(organisation):
    try:
        data = json.loads(token_path(organisation).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def usable(kept, hub_url, print_, now=None):
    """Whether a token kept in its file is this hub's, this key's, and far enough from its expiry."""
    if kept.get("hub") != hub_url.rstrip("/") or kept.get("fingerprint") != print_ or not kept.get("token"):
        return False
    try:
        expires = datetime.datetime.strptime(kept.get("expires") or "", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return expires - now > MARGIN


@contextlib.contextmanager
def token_lock(organisation):
    """One process at a time asks for a token: each access deletes the token before it, so two at once would
    leave one of them with a token that no longer works."""
    path = token_path(organisation).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "a", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)


def token(hub_url, organisation, stale=None, opener=None):
    """The token of this machine for the hub: the one kept in its file while it holds, else a new one, proved
    with the key. stale is a token the hub just refused: the file is read again (another process may have
    renewed it) and the token there is used only if it is another one."""
    print_ = fingerprint(public_key(organisation))
    with token_lock(organisation):
        kept = load_token(organisation)
        if usable(kept, hub_url, print_) and kept["token"] != stale:
            return kept["token"]
        answer = login(hub_url, organisation, opener)
        files.write_text(token_path(organisation), json.dumps(
            {"hub": hub_url.rstrip("/"), "fingerprint": print_, "token": answer["token"],
             "expires": answer.get("expires"), "environment": answer.get("environment")}, indent=2) + "\n", mode=0o600)
        return answer["token"]


def told_by_hub(hub_url, organisation, opener=None):
    """What the hub says now of the environment of this machine: {environment, state, fingerprint, expires,
    required}. The token kept in its file is not taken at its word: it is used, and renewed if the hub refuses
    it; a HubError 403 when the machine is not registered, not authorized yet, or revoked."""
    client = Hub(hub_url, token(hub_url, organisation, opener=opener), opener)
    client.renew = lambda stale: token(hub_url, organisation, stale=stale, opener=opener)
    told = client.call("environment")
    return told if isinstance(told, dict) else {}


def describe(hub_url, organisation):
    """What the person needs to register this machine: the fingerprint to compare and the address to open."""
    return fingerprint(public_key(organisation)), registration_url(hub_url, organisation)
