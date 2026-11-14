"""The threads of a fabric: the sources, tools and connectors a deploy mounts (docs/fili.md).

A thread is declared in texo.toml and mounted by a driver. A driver is a way of connecting, not a piece
of software: any MCP server, CLI, repository or URL is mounted with the drivers below, without touching
the core. The hub, the connector of the memory, is always mounted (the MCP server memoria) and is not
declared as a thread.
"""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TYPES = ("source", "tool", "connector")
DRIVERS = ("git-remote", "git-mirror", "http", "mcp-stdio", "mcp-http", "cli")
DATA_CLASSES = ("public", "org", "customer", "personal")
# personal is outside the ladder public < org < customer: the data of the person (family, private life), which
# never go to the threads of the organisation nor to the hub, and receive nothing from them
WRITES = ("never", "confirm")
ID = re.compile(r"^[a-z][a-z0-9_-]*$")
# a package pinned to an exact version: name@1.2.3, @scope/name@1.2.3, name==1.2.3
PINNED = re.compile(r"(@|==)v?\d+(\.\d+)*([.-][0-9A-Za-z.-]+)?$")
REQUIRED = {"git-remote": ("repo", "ref"), "git-mirror": ("repo", "ref"), "http": ("url",),
            "mcp-stdio": ("command",), "mcp-http": ("url",), "cli": ("command", "version")}
TIMEOUT = 20
# the handshake of doctor with an MCP server: how long it waits for an answer, how many pages of tools it reads
MCP_TIMEOUT = 60
MCP_PAGES = 20
MCP_PROTOCOL = "2025-06-18"


def shared_dir():
    """Where the mirrors of a machine live, shared by every fabric on it."""
    return Path(os.environ.get("TEXO_SHARED_DIR", "~/.local/share/texo")).expanduser()


def check(thread):
    """The problems of a thread declaration: (level, message) with level error or warning."""
    problems = []
    tid = thread.get("id") or "?"

    def error(message):
        problems.append(("error", f"{tid}: {message}"))

    def warning(message):
        problems.append(("warning", f"{tid}: {message}"))

    if not ID.match(thread.get("id") or ""):
        error("id is one lowercase word (letters, digits, - or _)")
    kind, driver = thread.get("type"), thread.get("driver")
    if kind not in TYPES:
        error(f"type is one of {', '.join(TYPES)}")
    if driver not in DRIVERS:
        error(f"driver is one of {', '.join(DRIVERS)}")
        return problems
    for key in REQUIRED[driver]:
        if not thread.get(key):
            error(f"the driver {driver} needs {key}")
    data_class = thread.get("data_class")
    if data_class not in DATA_CLASSES:
        error(f"data_class is one of {', '.join(DATA_CLASSES)}: what the thread may receive")
    writes = thread.get("writes", "never")
    if writes not in WRITES:
        error(f"writes is one of {', '.join(WRITES)}")
    if kind == "source" and writes != "never":
        error("a source is read only: writes = \"never\"")
    if kind == "connector" and data_class == "public":
        error("a connector holds data of the organisation, its customers or the person: data_class org, customer "
              "or personal")
    if kind == "connector" and writes == "never" and driver in ("mcp-stdio", "mcp-http"):
        warning("a connector the agent can only read: texo doctor lists the tools that say they write, and "
                "nothing stops them at run time")
    if kind == "tool" and data_class == "customer":
        warning("a tool that receives the data of customers: check where they go")
    if not (thread.get("guide") or "").strip():
        warning("no guide: the agent will not know when to use it and its limits")
    for key in ("paths", "skills"):
        if thread.get(key) and driver != "git-mirror":
            error(f"{key} is for a git-mirror thread")
    if thread.get("skills") and thread.get("paths") and not any(
            str(thread["skills"]).startswith(str(p).rstrip("/")) for p in thread["paths"]):
        error("skills is not inside the paths checked out")
    if driver in ("git-remote", "git-mirror") and thread.get("ref") in ("main", "master", "HEAD"):
        warning("ref is a moving branch: pin a tag or a commit")
    if driver == "mcp-stdio" and thread.get("command") in ("npx", "uvx", "pipx") and not any(
            PINNED.search(str(arg)) for arg in thread.get("args") or []):
        error(f"{thread['command']} installs a package: pin its version (name@1.2.3)")
    for key in ("auth", "token"):
        value = thread.get(key)
        if value and not str(value).startswith("env:"):
            error(f"{key} is written as env:NAME, never as its value")
    for name, value in (thread.get("env") or {}).items():
        if not str(value).startswith("env:") and re.search(r"(?i)token|key|secret|password", name):
            error(f"env {name} looks like a credential: write it as env:NAME")
    return problems


# -- git ----------------------------------------------------------------------------------------

def git_url(repo):
    """A repository written as host/owner/name or as a full URL."""
    if "://" in repo or repo.startswith(("git@", "/")):
        return repo
    return f"https://{repo}.git"


def run(command, cwd=None, timeout=300):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def mirror_dir(thread):
    return shared_dir() / "mirrors" / thread["id"]


def mount_git_mirror(thread):
    """A shallow clone at the pinned ref (a tag, a branch or a commit), refreshed when the ref changes; with
    paths, only those folders are checked out and the other files are never downloaded."""
    path = mirror_dir(thread)
    url, ref = git_url(thread["repo"]), thread["ref"]
    fresh = not (path / ".git").is_dir()
    if fresh:
        path.mkdir(parents=True, exist_ok=True)
        for step in (["git", "init", "--quiet"], ["git", "remote", "add", "origin", url]):
            run(step, cwd=path)
    paths = thread.get("paths") or []
    if paths:
        run(["git", "sparse-checkout", "set", *paths], cwd=path)
    elif not fresh:
        run(["git", "sparse-checkout", "disable"], cwd=path)
    fetch = ["git", "fetch", "--quiet", "--depth", str(thread.get("depth", 1))]
    fetch += ["--filter=blob:none"] if paths else []
    result = run([*fetch, "origin", ref], cwd=path)
    if result.returncode:
        if fresh:
            shutil.rmtree(path, ignore_errors=True)
            return "error", f"clone of {thread['repo']} at {ref} failed: {result.stderr.strip()[:200]}"
        return "warning", f"{path} kept: fetch of {ref} failed (offline?)"
    result = run(["git", "checkout", "--quiet", "--force", "FETCH_HEAD"], cwd=path)
    if result.returncode:
        return "error", f"checkout of {ref} in {path} failed: {result.stderr.strip()[:200]}"
    (path / ".git" / "texo-ref").write_text(ref + "\n", encoding="utf-8")
    return "ok", f"{'cloned' if fresh else 'at'} {ref} in {path}"


def doctor_git_mirror(thread):
    path = mirror_dir(thread)
    if not (path / ".git").is_dir():
        return "error", f"not mounted: {path} is missing (texo mount)"
    marker = path / ".git" / "texo-ref"
    mounted = marker.read_text(encoding="utf-8").strip() if marker.is_file() else None
    if mounted != thread["ref"]:
        return "warning", f"{path} is at {mounted or 'an unknown ref'}, texo.toml pins {thread['ref']}: texo mount"
    head = run(["git", "rev-parse", "HEAD"], cwd=path).stdout.strip()
    if thread.get("skills") and not (path / thread["skills"]).is_dir():
        return "error", f"{path} has no {thread['skills']}/: check skills and paths"
    return "ok", f"{path} at {thread['ref']} ({head[:12]})"


def doctor_git_remote(thread):
    result = run(["git", "ls-remote", git_url(thread["repo"]), thread["ref"]], timeout=TIMEOUT)
    if result.returncode:
        return "error", f"{thread['repo']} not reachable: {result.stderr.strip()[:200]}"
    if not result.stdout.strip() and not re.fullmatch(r"[0-9a-f]{7,40}", thread["ref"]):
        return "error", f"{thread['repo']} has no ref {thread['ref']}"
    return "ok", f"{thread['repo']} at {thread['ref']}"


# -- reading a git-remote source without cloning it -----------------------------------------------

def github_path(thread):
    """owner/name of a git-remote source on github.com; the reading commands need it."""
    repo = thread["repo"].removeprefix("https://").removesuffix(".git")
    if not repo.startswith("github.com/"):
        raise ValueError(f"{thread['id']}: reading without a clone supports github.com repositories only")
    return repo.removeprefix("github.com/")


def fetch(url, token=None, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "texo"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as response:
        return response.read().decode("utf-8", errors="replace")


def remote_list(thread, path="", token=None):
    """The entries of a folder of the source at its pinned ref."""
    url = (f"https://api.github.com/repos/{github_path(thread)}/contents/{urllib.parse.quote(path.strip('/'))}"
           f"?ref={urllib.parse.quote(thread['ref'])}")
    entries = json.loads(fetch(url, token))
    if isinstance(entries, dict):
        entries = [entries]
    return [{"path": e["path"], "type": e["type"], "size": e.get("size")} for e in entries]


def remote_read(thread, path, token=None):
    """One file of the source at its pinned ref."""
    url = (f"https://raw.githubusercontent.com/{github_path(thread)}/{urllib.parse.quote(thread['ref'])}/"
           f"{urllib.parse.quote(path.strip('/'))}")
    return fetch(url, token, accept="text/plain")


def remote_search(thread, query, token):
    """Code search in the source (GitHub searches its default branch: the hits say where, read at the ref)."""
    if not token:
        raise ValueError("searching a source on github.com needs a token: set GITHUB_TOKEN or GH_TOKEN")
    q = urllib.parse.quote(f"{query} repo:{github_path(thread)}")
    hits = json.loads(fetch(f"https://api.github.com/search/code?q={q}&per_page=20", token))
    return [{"path": item["path"], "name": item["name"]} for item in hits.get("items", [])]


# -- http ---------------------------------------------------------------------------------------

def doctor_http(thread, url_key="url"):
    request = urllib.request.Request(thread[url_key], method="HEAD", headers={"User-Agent": "texo"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return "ok", f"{thread[url_key]} answers {response.status}"
    except urllib.error.HTTPError as error:
        # a server that refuses HEAD or wants a token still answers: it is reachable
        if error.code in (401, 403, 405):
            return "ok", f"{thread[url_key]} answers {error.code}"
        return "error", f"{thread[url_key]} answers {error.code}"
    except (urllib.error.URLError, TimeoutError) as error:
        return "error", f"{thread[url_key]} not reachable: {getattr(error, 'reason', error)}"


# -- cli ----------------------------------------------------------------------------------------

def cli_version(thread):
    if not shutil.which(thread["command"]):
        return None
    result = run([thread["command"], *(thread.get("version_args") or ["--version"])], timeout=TIMEOUT)
    return (result.stdout + result.stderr).strip()


def mount_cli(thread, allow_install):
    version = cli_version(thread)
    if version is not None and thread["version"] in version:
        return "ok", f"{thread['command']} {thread['version']}"
    install = thread.get("install")
    if not install:
        found = f"found {version[:60]!r}" if version else "not in PATH"
        return "error", f"{thread['command']} {thread['version']} needed, {found}; no install command declared"
    if not allow_install:
        return "pending", f"would run: {install} (texo mount --yes)"
    result = subprocess.run(install, shell=True, capture_output=True, text=True, timeout=900)
    if result.returncode:
        return "error", f"{install} failed: {result.stderr.strip()[:200]}"
    version = cli_version(thread)
    if version is None or thread["version"] not in version:
        return "error", f"{install} ran, but {thread['command']} is not at {thread['version']}"
    return "ok", f"installed {thread['command']} {thread['version']}"


def doctor_cli(thread):
    version = cli_version(thread)
    if version is None:
        return "error", f"{thread['command']} not in PATH (texo mount)"
    if thread["version"] not in version:
        return "error", f"{thread['command']} is {version[:60]!r}, the fabric pins {thread['version']}"
    return "ok", f"{thread['command']} {thread['version']}"


# -- mcp ----------------------------------------------------------------------------------------

def events(body):
    """The JSON-RPC messages of a server-sent events body."""
    data = []
    for line in body.splitlines() + [""]:
        if line.startswith("data:"):
            data.append(line[5:].strip())
        elif not line.strip() and data:
            yield json.loads("\n".join(data))
            data = []


def mcp_session(ask):
    """What an MCP client does first, through ask (a message in, its answer or None out): initialize, the
    notification initialized, tools/list page after page. (status, message, tools): the name of the server
    or the error, and its tools, None when it did not list them."""
    answer = ask({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": MCP_PROTOCOL, "capabilities": {},
                             "clientInfo": {"name": "texo-doctor", "version": "1"}}})
    if not answer or "result" not in answer:
        return "error", "the server did not answer initialize", None
    info = answer["result"].get("serverInfo") or {}
    message = f"MCP server {info.get('name', '?')} {info.get('version', '')}".strip()
    ask({"jsonrpc": "2.0", "method": "notifications/initialized"})
    tools, cursor = [], None
    for page in range(MCP_PAGES):
        answer = ask({"jsonrpc": "2.0", "id": 2 + page, "method": "tools/list",
                      "params": {"cursor": cursor} if cursor else {}})
        if not answer or not isinstance(answer.get("result"), dict):
            return "ok", message, None
        tools += [tool for tool in answer["result"].get("tools") or [] if isinstance(tool, dict)]
        cursor = answer["result"].get("nextCursor")
        if not cursor:
            break
    return "ok", message, tools


def mcp_stdio_tools(command, env=None, cwd=None):
    """Start an MCP server over stdio and ask it who it is and which tools it has (mcp_session)."""
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   text=True, env=env, cwd=cwd)
    except OSError as error:
        return "error", f"{command[0]} cannot start: {error}", None
    lines = queue.Queue()

    def read():
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=read, daemon=True).start()

    def ask(message):
        try:
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
        except OSError:
            return None
        deadline = time.monotonic() + MCP_TIMEOUT
        while "id" in message:
            try:
                line = lines.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                return None
            if line is None:
                return None
            try:
                answer = json.loads(line)
            except ValueError:
                continue
            if isinstance(answer, dict) and answer.get("id") == message["id"]:
                return answer
        return None

    try:
        return mcp_session(ask)
    finally:
        for pipe in (process.stdin, process.stdout):
            try:
                pipe.close()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def mcp_stdio_handshake(command, env=None, cwd=None):
    """The name of an MCP server over stdio, or the error: mcp_stdio_tools without the tools."""
    return mcp_stdio_tools(command, env, cwd)[:2]


def mcp_http_tools(url, token=None, opener=None):
    """Ask an MCP server over Streamable HTTP who it is and which tools it has (mcp_session), with the token
    as bearer. A real call, not a HEAD: a server that answers a HEAD may still refuse the protocol. A server
    that wants a login the fabric has no credential for is reachable, and its tools are not listed."""
    opener = opener or urllib.request.urlopen
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "User-Agent": "texo"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    session = {}

    def ask(message):
        request = urllib.request.Request(url, data=json.dumps(message).encode(), method="POST",
                                         headers=dict(headers, **session))
        with opener(request, timeout=TIMEOUT) as response:
            if response.headers.get("Mcp-Session-Id"):
                session["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
            body = response.read().decode("utf-8", errors="replace")
            kind = response.headers.get("Content-Type", "")
        if "id" not in message or not body.strip():
            return None
        answers = events(body) if "text/event-stream" in kind else [json.loads(body)]
        return next((a for a in answers if isinstance(a, dict) and a.get("id") == message["id"]), None)

    try:
        return mcp_session(ask)
    except urllib.error.HTTPError as error:
        error.close()
        if error.code in (401, 403) and not token:
            return "ok", f"{url} answers {error.code}: it wants a login of the assistant", None
        if error.code in (401, 403):
            return "error", f"{url} answers {error.code}: the credential is refused", None
        return "error", f"{url} answers {error.code}", None
    except (urllib.error.URLError, TimeoutError) as error:
        return "error", f"{url} not reachable: {getattr(error, 'reason', error)}", None
    except ValueError:
        return "error", f"{url} does not answer as an MCP server", None


def write_audit(thread, status, message, tools):
    """What doctor says of an MCP thread once its tools are listed: (status, message). A thread declared
    writes = "never" is checked against what its tools declare (annotations.readOnlyHint), never against their
    names: a tool that says it writes is an error, one that says nothing a warning."""
    if status != "ok":
        return status, message
    never = thread.get("writes", "never") == "never"
    if tools is None:
        if never:
            return "warning", f"{message}; its tools were not listed: writes = \"never\" is not checked"
        return status, message
    writers, silent = tools_that_write(tools)
    message = f"{message}; {len(tools)} tools, {len(writers)} that write"
    if never and writers:
        return "error", f"{message}: writes = \"never\", but they declare that they write: {', '.join(writers)}"
    if never and silent:
        return "warning", f"{message}; writes = \"never\", and these do not say whether they write: {', '.join(silent)}"
    if silent:
        message += f", {len(silent)} that do not say"
    return "ok", message


def tools_that_write(tools):
    """(the names of the tools that declare they write, of those that do not say), sorted. readOnlyHint is
    the only word of a tool on it: without it the protocol assumes nothing, and neither does doctor."""
    writers, silent = [], []
    for tool in tools:
        annotations = tool.get("annotations")
        hint = annotations.get("readOnlyHint") if isinstance(annotations, dict) else None
        if hint is False:
            writers.append(str(tool.get("name")))
        elif hint is not True:
            silent.append(str(tool.get("name")))
    return sorted(writers), sorted(silent)
