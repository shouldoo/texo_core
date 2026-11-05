"""texo mount and texo doctor: compose the fabric of a customer and check that it holds.

mount reads texo.toml and the manifests of the industries, checks versions and declarations, installs the
threads that need it, writes the MCP configuration of every assistant (the hub as the server memoria, the MCP
threads through texo run-thread, so no credential is ever written in a file) and generates .texo/THREADS.md,
the index of the threads that the files of the assistants import. doctor checks that every thread answers
and every credential is there, without showing it.
"""
import json
import os
import re
import sys
import tomllib
from pathlib import Path

from . import __version__, threads
from .config import ConfigError, Fabric

ASSISTANTS = ("claude", "gemini", "antigravity")
MCP_DRIVERS = ("mcp-stdio", "mcp-http")
HUB_SERVER = "memoria"


# -- versions -----------------------------------------------------------------------------------

def version_tuple(text):
    numbers = re.findall(r"\d+", str(text or ""))
    return tuple(int(n) for n in numbers) if numbers else None


def satisfies(version, constraint):
    """Whether a version meets a constraint such as ">=1.0, <2"; an empty constraint always holds."""
    have = version_tuple(version)
    for part in [p.strip() for p in str(constraint or "").split(",") if p.strip()]:
        match = re.match(r"(>=|<=|==|>|<)?\s*v?(.+)", part)
        operator, wanted = match.group(1) or "==", version_tuple(match.group(2))
        size = max(len(have), len(wanted))
        a, b = have + (0,) * (size - len(have)), wanted + (0,) * (size - len(wanted))
        if not {">=": a >= b, "<=": a <= b, "==": a == b, ">": a > b, "<": a < b}[operator]:
            return False
    return True


def industry_manifest(fabric, industry):
    path = fabric.industry_dir(industry) / "texo_industry.toml"
    if not path.is_file():
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: {error}") from None


def check_fabric(fabric):
    """The problems of the composition: (level, message), level error, warning or info."""
    problems = []
    core = fabric.texo.get("core")
    if not core:
        problems.append(("error", "[texo] core is missing: the tag of texo_core mounted in core/"))
    elif version_tuple(core) != version_tuple(__version__):
        problems.append(("error", f"[texo] core is {core}, the mounted core is {__version__}: update the submodule"))
    if not fabric.texo.get("hub_url"):
        problems.append(("error", "[texo] hub_url is missing"))
    names = {industry.get("name") for industry in fabric.industries}
    declared = {thread.get("id") for thread in fabric.threads}
    for industry in fabric.industries:
        name = industry.get("name") or "?"
        manifest = industry_manifest(fabric, industry)
        if manifest is None:
            problems.append(("error", f"industry {name}: no texo_industry.toml in {fabric.industry_dir(industry)} "
                                      "(git submodule update --init)"))
            continue
        info = manifest.get("industry") or {}
        if version_tuple(info.get("version")) != version_tuple(industry.get("version")):
            problems.append(("error", f"industry {name}: texo.toml pins {industry.get('version')}, the submodule "
                                      f"is {info.get('version')}"))
        if not satisfies(__version__, info.get("core")):
            problems.append(("error", f"industry {name} needs core {info.get('core')}, the core is {__version__}"))
        for required in info.get("requires") or []:
            if required not in names:
                problems.append(("error", f"industry {name} requires the industry {required}"))
        for suggested in manifest.get("suggested_thread") or []:
            if suggested.get("id") not in declared:
                problems.append(("info", f"industry {name} suggests the thread {suggested.get('id')}: "
                                         f"{suggested.get('why') or suggested.get('guide') or ''}".rstrip(": ")))
    ids = [thread.get("id") for thread in fabric.threads]
    for duplicate in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(("error", f"thread {duplicate} declared twice"))
    if HUB_SERVER in ids:
        problems.append(("error", f"{HUB_SERVER} is the hub, always mounted: give the thread another id"))
    for thread in fabric.threads:
        problems += threads.check(thread)
    return problems


# -- the files the agents read ------------------------------------------------------------------

def how_to_use(thread):
    driver, tid = thread["driver"], thread["id"]
    if driver == "git-remote":
        return f"`texo thread {tid} ls|read|search` (read at {thread['ref']}, never cloned)"
    if driver == "git-mirror":
        return f"`rg` in `{threads.mirror_dir(thread)}` (read only, at {thread['ref']})"
    if driver == "http":
        return f"<{thread['url']}>"
    if driver == "cli":
        return f"the command `{thread['command']}`"
    return f"the tools of the MCP server `{tid}`"


def threads_markdown(fabric, states):
    lines = [
        "# Threads of this fabric",
        "",
        "Generated by `texo mount` from texo.toml: do not edit. The hub (the MCP server `memoria`) is always mounted.",
        "",
        "- Cite the source you read (the thread and the path or the address), never what you remember of it.",
        "- Ask the person before anything a connector or a tool writes; a thread with writes never is read only.",
        "- data_class says what a thread may receive: public (nothing of the organisation), org (the organisation's",
        "  own data), customer (the data of its customers too). Never send a thread data of a class above its own.",
        "- A thread that does not answer: say so and go on without it; `texo doctor` says why.",
        "",
        "| Thread | Type | data_class | writes | How | Guide |",
        "|---|---|---|---|---|---|",
    ]
    for thread in fabric.threads:
        guide = " ".join((thread.get("guide") or "").split()).replace("|", "\\|")
        status = states.get(thread["id"], {}).get("status")
        mark = "" if status in (None, "ok") else f" ({status})"
        lines.append(f"| `{thread['id']}`{mark} | {thread['type']} | {thread['data_class']} | "
                     f"{thread.get('writes', 'never')} | {how_to_use(thread)} | {guide} |")
    if not fabric.threads:
        lines.append("| — | | | | | no thread declared |")
    return "\n".join(lines) + "\n"


def texo_command(fabric):
    """The launcher of this core, as the assistants run it."""
    return str((Path(__file__).resolve().parent.parent / "bin" / "texo"))


def mcp_servers(fabric, assistant):
    """The MCP servers of an assistant: the hub, then the MCP threads meant for it."""
    command = texo_command(fabric)
    root = str(fabric.root)
    servers = {HUB_SERVER: {"command": command, "args": ["--root", root, "mcp"]}}
    for thread in fabric.threads:
        if thread.get("driver") not in MCP_DRIVERS:
            continue
        if thread.get("assistants") and assistant not in thread["assistants"]:
            continue
        servers[thread["id"]] = {"command": command, "args": ["--root", root, "run-thread", thread["id"]]}
    return servers


def merge_json(path, update, mode=None):
    """Merge into a JSON file, never dropping what the person set; mode for files that hold a profile."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    update(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if mode:
        os.chmod(path, mode)


def write_assistants(fabric, out):
    previous = load_state(fabric).get("mcp_servers", [])

    def update(servers_key, assistant, entry=lambda server: dict(server, type="stdio")):
        def apply(data):
            servers = data.setdefault(servers_key, {})
            for name in previous:
                servers.pop(name, None)
            for name, server in mcp_servers(fabric, assistant).items():
                servers[name] = entry(server)
        return apply

    merge_json(fabric.root / ".mcp.json", update("mcpServers", "claude"))
    out.write("[ok] Claude Code: .mcp.json\n")
    merge_json(fabric.root / ".gemini" / "settings.json", update("mcpServers", "gemini", entry=dict))
    out.write("[ok] Gemini CLI: .gemini/settings.json\n")
    profile = Path(os.environ.get("TEXO_AGY_PROFILE", f"~/.antigravity-texo-{fabric.customer}")).expanduser()
    if profile.is_dir():
        merge_json(profile / ".gemini" / "config" / "mcp_config.json", update("mcpServers", "antigravity", entry=dict),
                   mode=0o600)
        out.write(f"[ok] Antigravity: {profile}\n")
    return sorted(mcp_servers(fabric, "claude"))


SKILL_DIRS = (".agents/skills", ".claude/skills")
IGNORED = (".texo/", ".mcp.json", ".gemini/settings.json", ".agents/skills/", ".claude/skills/")


def skill_sources(fabric):
    """The skills of the fabric by name: the customer's own win over an industry's, an industry's over the core's."""
    core = Path(__file__).resolve().parent.parent
    layers = [("core", core / "skills")]
    layers += [(f"industry {i['name']}", fabric.industry_dir(i) / "skills") for i in fabric.industries]
    layers.append(("customer", fabric.root / "skills"))
    found, shadowed = {}, []
    for layer, folder in layers:
        for skill in sorted(folder.glob("*/SKILL.md")) if folder.is_dir() else []:
            name = skill.parent.name
            if name in found:
                shadowed.append(f"skill {name} of {found[name][0]} replaced by the one of {layer}")
            found[name] = (layer, skill.parent)
    return found, shadowed


def link_skills(fabric, out):
    """Every skill linked where each assistant looks for them; the links of a previous mount are replaced."""
    found, shadowed = skill_sources(fabric)
    for message in shadowed:
        out.write(f"[info] {message}\n")
    for folder in SKILL_DIRS:
        target_dir = fabric.root / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        for entry in target_dir.iterdir():
            if entry.is_symlink():
                entry.unlink()
        for name, (_layer, source) in found.items():
            if not (target_dir / name).exists():
                (target_dir / name).symlink_to(os.path.relpath(source, target_dir))
    out.write(f"[ok] skills: {len(found)} linked in {', '.join(SKILL_DIRS)}\n")
    return sorted(found)


def ignore_generated(fabric, out):
    """The files mount generates stay out of git: the missing lines are added to .gitignore."""
    path = fabric.root / ".gitignore"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    missing = [entry for entry in IGNORED if entry not in lines]
    if missing:
        block = ["", "# generated by texo mount"] if lines else ["# generated by texo mount"]
        path.write_text("\n".join(lines + block + missing) + "\n", encoding="utf-8")
        out.write(f"[ok] .gitignore: {', '.join(missing)}\n")


def load_state(fabric):
    try:
        return json.loads((fabric.state_dir / "threads.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# -- the commands ---------------------------------------------------------------------------------

def report(problems, out):
    for level, message in problems:
        out.write(f"[{level}] {message}\n")
    return any(level == "error" for level, _ in problems)


def mount(fabric, allow_install=False, out=sys.stdout):
    if report(check_fabric(fabric), out):
        out.write("Nothing mounted: fix the errors in texo.toml.\n")
        return 1
    states, failed = {}, False
    for thread in fabric.threads:
        driver = thread["driver"]
        if driver == "git-mirror":
            status, message = threads.mount_git_mirror(thread)
        elif driver == "cli":
            status, message = threads.mount_cli(thread, allow_install)
        else:
            status, message = "ok", "declared"
        for reference in [thread.get("auth"), *(thread.get("env") or {}).values()]:
            if reference and str(reference).startswith("env:") and not fabric.has_secret(reference):
                status, message = "warning", f"{message}; {reference[4:]} is not set"
        states[thread["id"]] = {"status": status, "message": message}
        out.write(f"[{status}] {thread['id']}: {message}\n")
        failed |= status == "error"
    fabric.state_dir.mkdir(exist_ok=True)
    (fabric.state_dir / "THREADS.md").write_text(threads_markdown(fabric, states), encoding="utf-8")
    servers = write_assistants(fabric, out)
    skills = link_skills(fabric, out)
    ignore_generated(fabric, out)
    state = {"core": __version__, "threads": [dict(t, **states[t["id"]]) for t in fabric.threads],
             "mcp_servers": [name for name in servers if name != HUB_SERVER], "skills": skills}
    (fabric.state_dir / "threads.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    out.write("[ok] .texo/THREADS.md\n")
    if any(s["status"] == "pending" for s in states.values()):
        out.write("Some threads wait for an installation: texo mount --yes runs the commands listed above.\n")
    return 1 if failed else 0


def doctor(fabric, out=sys.stdout):
    failed = report(check_fabric(fabric), out)
    try:
        fabric.secret(fabric.texo.get("hub_token") or "env:TEXO_HUB_TOKEN")
        out.write("[ok] hub token present\n")
    except ConfigError as error:
        out.write(f"[error] hub: {error}\n")
        failed = True
    if fabric.texo.get("hub_url"):
        status, message = threads.doctor_http({"url": fabric.texo["hub_url"].rstrip("/") + "/web/login"})
        out.write(f"[{status}] hub: {message}\n")
        failed |= status == "error"
    for thread in fabric.threads:
        try:
            status, message = doctor_thread(fabric, thread)
        except ConfigError as error:
            status, message = "error", str(error)
        out.write(f"[{status}] {thread.get('id')}: {message}\n")
        failed |= status == "error"
    return 1 if failed else 0


def doctor_thread(fabric, thread):
    driver = thread.get("driver")
    if driver == "git-mirror":
        return threads.doctor_git_mirror(thread)
    if driver == "git-remote":
        return threads.doctor_git_remote(thread)
    if driver == "http":
        return threads.doctor_http(thread)
    if driver == "cli":
        return threads.doctor_cli(thread)
    if driver == "mcp-http":
        if thread.get("auth"):
            fabric.secret(thread["auth"])
        return threads.doctor_http(thread)
    if driver == "mcp-stdio":
        env = thread_env(fabric, thread)
        return threads.mcp_stdio_handshake([thread["command"], *thread.get("args", [])], env=env, cwd=fabric.root)
    return "error", f"unknown driver {driver}"


def thread_env(fabric, thread):
    """The environment of a thread process: the person's, plus its declared variables with credentials resolved."""
    env = dict(os.environ)
    for name, value in (thread.get("env") or {}).items():
        env[name] = fabric.secret(value) if str(value).startswith("env:") else str(value)
    return env


def thread_by_id(fabric, thread_id):
    for thread in fabric.threads:
        if thread.get("id") == thread_id:
            return thread
    raise ConfigError(f"no thread {thread_id} in texo.toml")


def load(root):
    return Fabric(root)
