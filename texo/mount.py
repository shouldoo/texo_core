"""texo mount and texo doctor: compose the working folder of an organisation and check that it holds.

mount reads the configuration of the organisation from its hub (packs and threads, merged with texo.toml), installs
the packs of the marketplace and the threads that need it, checks versions and declarations, writes the MCP
configuration of every assistant (the hub as the server memoria, the MCP threads through texo run-thread, so no
credential is ever written in a file), links the skills, and writes the files the assistants read: AGENTS.md (the
limits), ARCHITECTURE.md (where the agent works, the folders of the skills included), DESIGN.md (how it
writes), CLAUDE.md and GEMINI.md that import them, .texo/THREADS.md. doctor checks that the hub, every thread and every
credential are there, without showing a credential.
"""
import datetime
import json
import os
import re
import sys
from pathlib import Path

from . import __version__, hub, packs, threads
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


def check_fabric(fabric):
    """The problems of the composition: (level, message), level error, warning or info. The packs are checked
    once installed (their pack.toml)."""
    problems = []
    if not fabric.texo.get("hub_url"):
        problems.append(("error", "[texo] hub_url is missing"))
    declared = {thread.get("id") for thread in fabric.threads}
    for pack in fabric.packs:
        name = pack.get("name") or "?"
        if not re.match(r"^[a-z][a-z0-9_]*$", name) or not version_tuple(pack.get("version")):
            problems.append(("error", f"pack {name}: a pack has a name (one lowercase word) and a version (v1.2.0)"))
            continue
        manifest = packs.manifest(fabric, pack)
        if manifest is None:
            continue
        info = manifest.get("pack") or {}
        if version_tuple(info.get("version")) != version_tuple(pack.get("version")):
            problems.append(("error", f"pack {name}: the configuration asks {pack.get('version')}, the marketplace "
                                      f"tag holds {info.get('version')}"))
        if not satisfies(__version__, info.get("core")):
            problems.append(("error", f"pack {name} needs core {info.get('core')}, the core is {__version__}: "
                                      "update texo (setup/install.sh)"))
        for suggested in manifest.get("suggested_thread") or []:
            if suggested.get("id") not in declared:
                problems.append(("info", f"pack {name} suggests the thread {suggested.get('id')}: "
                                         f"{suggested.get('why') or suggested.get('guide') or ''}".rstrip(": ")))
    ids = [thread.get("id") for thread in fabric.threads]
    for duplicate in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(("error", f"thread {duplicate} declared twice"))
    if HUB_SERVER in ids:
        problems.append(("error", f"{HUB_SERVER} is the hub, always mounted: give the thread another id"))
    for thread in fabric.threads:
        problems += threads.check(thread)
        if str(thread.get("origin", "")).startswith("pack "):
            problems += packs.thread_problems(thread)
    return problems


# -- the files the agents read ------------------------------------------------------------------

def how_to_use(thread):
    driver, tid = thread["driver"], thread["id"]
    if driver == "git-remote":
        return f"`texo thread {tid} ls|read|search` (letto a {thread['ref']}, mai clonato)"
    if driver == "git-mirror":
        return f"`rg` in `{threads.mirror_dir(thread)}` (sola lettura, a {thread['ref']})"
    if driver == "http":
        return f"<{thread['url']}>"
    if driver == "cli":
        return f"il comando `{thread['command']}`"
    return f"gli strumenti del server MCP `{tid}`"


def threads_markdown(fabric, states):
    lines = [
        "# I fili di questa cartella",
        "",
        "Generato da `texo mount` dalla configurazione dell'organizzazione: non modificarlo. Il hub (il server MCP",
        "`memoria`) è sempre montato.",
        "",
        "- Cita la fonte che hai letto (il filo e il percorso o l'indirizzo), mai ciò che ne ricordi.",
        "- Chiedi alla persona prima di qualsiasi scrittura di un connettore o di uno strumento; un filo con",
        "  writes never è in sola lettura.",
        "- data_class dice che cosa un filo può ricevere: public (niente dell'organizzazione), org (i dati",
        "  dell'organizzazione), customer (anche i dati dei suoi clienti). Non mandare mai a un filo dati di una",
        "  classe sopra la sua.",
        "- Un filo che non risponde: dillo e prosegui senza; `texo doctor` dice perché.",
        "",
        "| Filo | Tipo | data_class | writes | Come | Guida |",
        "|---|---|---|---|---|---|",
    ]
    for thread in fabric.threads:
        guide = " ".join((thread.get("guide") or "").split()).replace("|", "\\|")
        status = states.get(thread["id"], {}).get("status")
        mark = "" if status in (None, "ok") else f" ({status})"
        lines.append(f"| `{thread['id']}`{mark} | {thread['type']} | {thread['data_class']} | "
                     f"{thread.get('writes', 'never')} | {how_to_use(thread)} | {guide} |")
    if not fabric.threads:
        lines.append("| — | | | | | nessun filo dichiarato |")
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


# the events of the assistant and the event of texo hook each one calls
HOOK_EVENTS = (("Stop", "stop"), ("PreCompact", "precompact"), ("SessionEnd", "session-end"))


def hooks_update(fabric):
    """The hooks of the proposal of the session note (texo hook) in the settings of the assistant: ours are
    replaced, what the person set stays."""
    command = texo_command(fabric)

    def ours(entry):
        return any("texo" in h.get("command", "") and " hook " in h.get("command", "")
                   for h in entry.get("hooks", []) if isinstance(h, dict))

    def apply(data):
        hooks = data.setdefault("hooks", {})
        for event, argument in HOOK_EVENTS:
            kept = [entry for entry in hooks.get(event, []) if isinstance(entry, dict) and not ours(entry)]
            kept.append({"hooks": [{"type": "command",
                                    "command": f"{command} --root {fabric.root} hook {argument}"}]})
            hooks[event] = kept
    return apply


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
    merge_json(fabric.root / ".claude" / "settings.local.json", hooks_update(fabric))
    out.write("[ok] Claude Code: .claude/settings.local.json (hooks)\n")
    merge_json(fabric.root / ".gemini" / "settings.json", update("mcpServers", "gemini", entry=dict))
    out.write("[ok] Gemini CLI: .gemini/settings.json\n")
    profile = Path(os.environ.get("TEXO_AGY_PROFILE", f"~/.antigravity-texo-{fabric.organisation}")).expanduser()
    if profile.is_dir():
        merge_json(profile / ".gemini" / "config" / "mcp_config.json", update("mcpServers", "antigravity", entry=dict),
                   mode=0o600)
        out.write(f"[ok] Antigravity: {profile}\n")
    return sorted(mcp_servers(fabric, "claude"))


SKILL_DIRS = (".agents/skills", ".claude/skills")
IGNORED = (".texo/", ".mcp.json", ".gemini/settings.json", ".claude/settings.local.json", ".agents/skills/",
           ".claude/skills/")


def skill_sources(fabric):
    """The skills of the working folder by name: its own (skills/) win over a pack's, a pack's over those of a
    thread (a mirror that carries skills), and these over the core's."""
    core = Path(__file__).resolve().parent.parent
    layers = [("core", core / "skills")]
    layers += [(f"thread {t['id']}", threads.mirror_dir(t) / t["skills"]) for t in fabric.threads
               if t.get("driver") == "git-mirror" and t.get("skills")]
    layers += [(f"pack {p['name']}", packs.folder(fabric, p) / "skills") for p in fabric.packs]
    layers.append(("this folder", fabric.root / "skills"))
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


def work_dirs(fabric):
    """The working folders the packs declare (work_dirs in pack.toml): created by mount, never versioned."""
    folders = []
    for pack in fabric.packs:
        manifest = packs.manifest(fabric, pack) or {}
        for folder in (manifest.get("pack") or {}).get("work_dirs") or []:
            folder = str(folder).strip("/")
            if folder and ".." not in Path(folder).parts and folder not in folders:
                folders.append(folder)
    return folders


def ignore_generated(fabric, out):
    """The files mount generates and the working folders stay out of git: the missing lines go to .gitignore."""
    path = fabric.root / ".gitignore"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    wanted = list(IGNORED) + [f"{folder}/" for folder in work_dirs(fabric)]
    # the files of the assistants mount wrote; those the person wrote are theirs to version
    wanted += [name for name in AGENT_FILES + POINTERS if (fabric.root / name).is_file()
               and GENERATED in (fabric.root / name).read_text(encoding="utf-8")]
    missing = [entry for entry in wanted if entry not in lines]
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


GENERATED = "<!-- generated by texo mount: the rules live in the core and in the hub, not here -->"


def refresh(fabric, out, client=None):
    """The configuration of the organisation from its hub, kept in .texo/config.json; the copy kept there when
    the hub does not answer."""
    try:
        remote = (client or hub.Hub(*fabric.hub())).call("config")
    except (ConfigError, hub.HubError) as error:
        kept = fabric.remote.get("fetched")
        out.write(f"[warning] hub: {error}; " + (f"the configuration read on {kept} is used\n" if kept else
                                                 "only texo.toml is used\n"))
        return
    if remote.get("organisation") and remote["organisation"] != fabric.organisation:
        out.write(f"[warning] the hub names the organisation {remote['organisation']}, texo.toml "
                  f"{fabric.organisation}: the credentials file is named after texo.toml\n")
    remote["fetched"] = datetime.date.today().isoformat()
    fabric.save_remote(remote)
    out.write(f"[ok] hub: {len(remote.get('packs') or [])} packs, {len(remote.get('threads') or [])} threads\n")


AGENT_FILES = ("AGENTS.md", "ARCHITECTURE.md", "DESIGN.md")
POINTERS = ("CLAUDE.md", "GEMINI.md")
TEMPLATES = Path(__file__).resolve().parent.parent / "setup" / "templates" / "cartella"


def this_folder(fabric, core, skills):
    """The part of ARCHITECTURE.md that is this folder: the organisation, the hub, the core, the packs, the threads."""
    remote = fabric.remote or {}
    names = ", ".join(f"`{p['name']}` {p['version']}" for p in fabric.packs) or "nessuno"
    lines = ["## Questa cartella", "",
             f"- Organizzazione: `{fabric.organisation}`" + (f" ({remote['company']})" if remote.get("company") else "")
             + f"; hub: {fabric.texo.get('hub_url')}" + (f"; configurazione letta il {remote['fetched']}" if
                                                        remote.get("fetched") else "") + ".",
             f"- Core: `{core}`, versione {__version__}.",
             f"- Pacchetti: {names}.",
             f"- Fili: {len(fabric.threads)}, indice in `.texo/THREADS.md`.",
             f"- Skill: {len(skills)} collegate, nelle cartelle qui sotto."]
    folders = work_dirs(fabric)
    if folders:
        lines.append("- Cartelle di lavoro dei pacchetti, fuori da git: " + ", ".join(f"`{f}/`" for f in folders) + ".")
    lines += ["- Proposte delle note di sessione: `.texo/proposals/`.",
              f"- Credenziali: `~/.config/texo/{fabric.organisation}.env`, mai in questa cartella."]
    return "\n".join(lines) + "\n"


def packs_design(fabric):
    """The style the packs bring: the DESIGN.md at the root of each pack, when it has one."""
    parts = []
    for pack in fabric.packs:
        path = packs.folder(fabric, pack) / "DESIGN.md"
        if path.is_file():
            body = path.read_text(encoding="utf-8").strip()
            body = re.sub(r"^# .*\n+", "", body)  # the title of the pack's file: the section names the pack
            parts.append(f"### Pacchetto `{pack['name']}`\n\n{body}\n")
    if not parts:
        return ""
    return "## Lo stile dei pacchetti\n\n" + "\n".join(parts) + "\n"


def skill_folders(fabric):
    """The part of ARCHITECTURE.md that says where the skills are: the folders the assistants read, and the
    folder each skill comes from, by origin, with the full path."""
    found, _shadowed = skill_sources(fabric)
    origin = {"core": "core", "this folder": "questa cartella"}
    by_folder = {}
    for name, (layer, source) in sorted(found.items()):
        label = origin.get(layer) or layer.replace("pack ", "pacchetto ").replace("thread ", "filo ")
        by_folder.setdefault((label, str(source.parent)), []).append(name)
    rank = {"core": 0, "filo": 1, "pacchetto": 2, "questa": 3}
    lines = ["## Le cartelle delle skill", "", "Collegate qui, dove ogni assistente le cerca:", ""]
    lines += [f"- `{fabric.root / folder}/`" for folder in SKILL_DIRS]
    lines += ["", "Da dove viene ciascuna, nell'ordine di precedenza (l'ultima vince a parità di nome):", ""]
    for (label, folder), names in sorted(by_folder.items(), key=lambda item: rank.get(item[0][0].split()[0], 9)):
        lines.append(f"- {label}: `{folder}/`: " + ", ".join(f"`{name}`" for name in names) + ".")
    return "\n".join(lines) + "\n", sorted(found)


def agent_files(fabric):
    """The files the assistants read, from the core and the configuration of the organisation: AGENTS.md (the
    limits), ARCHITECTURE.md (where the agent works, with this folder and the folders of its skills), DESIGN.md
    (how it writes, with the style of the packs); CLAUDE.md and GEMINI.md import them with the index of the
    threads."""
    core = Path(__file__).resolve().parent.parent

    def source(path):
        return path.read_text(encoding="utf-8").replace("<core>", str(core)).rstrip()

    folders, skills = skill_folders(fabric)
    folder = this_folder(fabric, core, skills) + "\n" + folders
    design = source(TEMPLATES / "DESIGN.md")
    marker = "## Lo stile dell'organizzazione"
    if marker in design:
        before, after = design.split(marker, 1)
        design = before + packs_design(fabric) + marker + after
    files = {
        "AGENTS.md": f"{GENERATED}\n{source(core / 'AGENTS.md')}\n",
        "ARCHITECTURE.md": f"{GENERATED}\n{source(TEMPLATES / 'ARCHITECTURE.md')}\n\n{folder}",
        "DESIGN.md": f"{GENERATED}\n{design.rstrip()}\n",
    }
    pointer = GENERATED + "\n" + "".join(f"@{name}\n" for name in AGENT_FILES) + "@.texo/THREADS.md\n"
    files.update({name: pointer for name in POINTERS})
    return files


def write_agent_files(fabric, out):
    for name, content in agent_files(fabric).items():
        path = fabric.root / name
        if path.exists() and GENERATED not in path.read_text(encoding="utf-8"):
            out.write(f"[info] {name} is yours, left as it is: make it lead to the rules of the core "
                      f"({Path(__file__).resolve().parent.parent / 'AGENTS.md'}) and to .texo/THREADS.md\n")
            continue
        path.write_text(content, encoding="utf-8")
    out.write(f"[ok] {', '.join(AGENT_FILES + POINTERS)}\n")


def mount(fabric, allow_install=False, out=sys.stdout, client=None, offline=False):
    if not offline:
        refresh(fabric, out, client)
    failed = False
    for pack in fabric.packs:
        if not re.match(r"^[a-z][a-z0-9_]*$", pack.get("name") or "") or not version_tuple(pack.get("version")):
            continue
        status, message = packs.install(fabric, pack)
        out.write(f"[{status}] pack {pack['name']} {pack['version']}: {message}\n")
        failed |= status == "error"
    if report(check_fabric(fabric), out) or failed:
        out.write("Nothing mounted: fix the errors (the configuration in the hub, or texo.toml).\n")
        return 1
    states = {}
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
    for folder in work_dirs(fabric):
        (fabric.root / folder).mkdir(parents=True, exist_ok=True)
    write_agent_files(fabric, out)
    ignore_generated(fabric, out)
    state = {"core": __version__, "packs": fabric.packs,
             "threads": [dict(t, **states[t["id"]]) for t in fabric.threads],
             "mcp_servers": [name for name in servers if name != HUB_SERVER], "skills": skills}
    (fabric.state_dir / "threads.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    out.write("[ok] .texo/THREADS.md\n")
    if any(s["status"] == "pending" for s in states.values()):
        out.write("Some threads wait for an installation: texo mount --yes runs the commands listed above.\n")
    return 1 if failed else 0


def doctor(fabric, out=sys.stdout, client=None):
    failed = report(check_fabric(fabric), out)
    try:
        url, token = fabric.hub()
        out.write("[ok] hub token present\n")
    except ConfigError as error:
        out.write(f"[error] hub: {error}\n")
        failed = True
    else:
        failed |= doctor_hub(fabric, client or hub.Hub(url, token), out)
    for pack in fabric.packs:
        installed = packs.manifest(fabric, pack) is not None
        out.write(f"[{'ok' if installed else 'error'}] pack {pack.get('name')} {pack.get('version')}: "
                  f"{'installed' if installed else 'not installed (texo mount)'}\n")
        failed |= not installed
    for thread in fabric.threads:
        try:
            status, message = doctor_thread(fabric, thread)
        except ConfigError as error:
            status, message = "error", str(error)
        out.write(f"[{status}] {thread.get('id')}: {message}\n")
        failed |= status == "error"
    return 1 if failed else 0


def doctor_hub(fabric, client, out):
    """The hub asked as the person: the token is accepted, the person has a role, the hub names the organisation
    of texo.toml. True when something fails."""
    try:
        person = client.call("whoami")
        remote = client.call("config")
    except hub.HubError as error:
        out.write(f"[error] hub{' ' + str(error.status) if error.status else ''}: {error}\n")
        return True
    out.write(f"[ok] hub: {person.get('login')}, role {person.get('role')}\n")
    if remote.get("organisation") and remote["organisation"] != fabric.organisation:
        out.write(f"[warning] the hub names the organisation {remote['organisation']}, texo.toml "
                  f"{fabric.organisation}: the credentials file is named after texo.toml\n")
    return False


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
    raise ConfigError(f"no thread {thread_id} in the configuration of the organisation")


def load(root):
    return Fabric(root)
