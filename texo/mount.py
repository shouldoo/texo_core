"""texo mount and texo doctor: compose the working folder of an organisation and check that it holds.

mount reads the configuration of the organisation from its hub (packs and threads, merged with texo.toml), installs
the packs of the marketplace and the threads that need it, checks versions and declarations, writes the MCP
configuration of every assistant (the hub as the server memoria, the MCP threads through texo run-thread, so no
credential is ever written in a file), links the skills, and writes the files the assistants read: AGENTS.md (the
limits), ARCHITECTURE.md (where the agent works, the folders of the skills included), DESIGN.md (how it
writes), CLAUDE.md and GEMINI.md that import them, .texo/THREADS.md. doctor checks that the hub, every thread and every
credential are there, without showing a credential.
"""
import contextlib
import datetime
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from . import __version__, files, hub, packs, threads

try:
    import fcntl
except ImportError:  # no advisory locks on this system: two mounts at once are not kept apart
    fcntl = None
from .config import ConfigError, Fabric

ASSISTANTS = ("claude", "gemini", "antigravity")
MCP_DRIVERS = ("mcp-stdio", "mcp-http")
HUB_SERVER = "memoria"
# what texo mount answers: all mounted, an error, or mounted from the configuration kept in the folder
# because the hub did not answer (a script can tell the three apart)
MOUNTED, FAILED, FROM_CACHE = 0, 1, 3
# how long mount waits for the hub to accept a connection, before it falls back on the configuration it kept;
# the answer itself may take longer (hub.TIMEOUT)
CONNECT_TIMEOUT = 5
# how long a mount waits for another one at work in the same folder
LOCK_WAIT = 60
LOCK_FILE = "mount.lock"
ENVIRONMENT_FILE = "environment.json"


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
        for check in manifest.get("check") or []:
            problems += [("error", f"pack {name}: {problem}") for problem in check_problems(check)]
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
        if thread.get("data_class") == "personal" and thread.get("origin") != "local":
            problems.append(("error", f"{thread.get('id')}: a personal thread is declared only in texo.toml, "
                                      "never in the hub or in a pack"))
    personal = [t.get("id") for t in fabric.threads if t.get("data_class") == "personal"]
    if personal:
        problems.append(("info", f"personal threads: {', '.join(personal)}: nothing passes between them and the hub "
                                 "or the threads of the organisation"))
    problems += check_hooks(fabric)
    return problems


def check_hooks(fabric):
    """The problems of the [[hook]] of texo.toml; hooks the hub lists are never written."""
    problems = []
    if (fabric.remote or {}).get("hooks"):
        problems.append(("warning", "the hub lists hooks: ignored, a hook is declared only in texo.toml"))
    ids = [hook.get("id") for hook in fabric.hooks]
    for duplicate in sorted({i for i in ids if ids.count(i) > 1}, key=str):
        problems.append(("error", f"hook {duplicate} declared twice"))
    for hook in fabric.hooks:
        hid = hook.get("id") or "?"
        if hid in (NOTE_HOOK, RULES_HOOK):
            problems.append(("error", f"hook {hid}: this id is the one of a hook texo mount writes"))
        if not threads.ID.match(hook.get("id") or ""):
            problems.append(("error", f"hook {hid}: id is one lowercase word (letters, digits, - or _)"))
        if hook.get("event") not in ASSISTANT_EVENTS:
            problems.append(("error", f"hook {hid}: event is one of {', '.join(ASSISTANT_EVENTS)}"))
        if not isinstance(hook.get("command"), str) or not hook["command"].strip():
            problems.append(("error", f"hook {hid}: command is the command to run"))
        if "matcher" in hook and not isinstance(hook["matcher"], str):
            problems.append(("error", f"hook {hid}: matcher is a string"))
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
        "- personal (i dati della persona: famiglia, vita privata) sta fuori da quella scala: nulla passa tra un",
        "  filo personal e il hub o gli altri fili, in nessuna direzione.",
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


def is_guest(fabric):
    """Whether the folder is the guest of a repository: a git repository with an AGENTS.md mount did not write.
    There mount touches no file the repository tracks and adds nothing to its .gitignore: what it generates is
    excluded in the repository's own exclude file, the rules of the core go to .texo/, and the hook of the
    start of a session tells the agent where they are."""
    rules = fabric.root / "AGENTS.md"
    if not (fabric.root / ".git").exists() or not rules.is_file():
        return False
    return GENERATED not in rules.read_text(encoding="utf-8", errors="replace")


def tracked_paths(fabric):
    """The paths mount writes that the repository of a guest folder tracks: they are the repository's, mount
    leaves them as they are. Empty when the folder is not a guest."""
    if not is_guest(fabric):
        return set()
    result = threads.run(["git", "ls-files", "--", ".mcp.json", ".claude", ".gemini", ".agents"], cwd=fabric.root)
    return set(result.stdout.split("\n")) - {""} if result.returncode == 0 else set()


def merge_json(path, update, mode=None):
    """Merge into a JSON file, never dropping what the person set; mode for files that hold a profile."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    update(data)
    files.write_text(path, json.dumps(data, indent=2) + "\n", mode=mode)


# the events of the assistant and the event of texo hook each one calls
HOOK_EVENTS = (("Stop", "stop"), ("PreCompact", "precompact"), ("SessionEnd", "session-end"))
# the events a [[hook]] of texo.toml may declare
ASSISTANT_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Notification", "Stop",
                    "SubagentStop", "PreCompact", "SessionEnd")
HOOKS_FILE = ".agents/hooks.json"
# the key, in HOOKS_FILE, of the hook of the proposal of the session note, and the events it is written for
# there: only those the assistant that reads the file is known to raise and to take in this form
NOTE_HOOK = "texo-note"
NOTE_HOOK_EVENTS = (("Stop", "stop"),)
# the key, there, of the hook that tells the agent where the rules are in a folder mounted as a guest
RULES_HOOK = "texo-rules"
# the events of HOOKS_FILE that are about a tool: their entry is {matcher, hooks: [command]}. The entry of every
# other event is the command itself: an assistant that reads the file refuses all of it, and loads no hook, when
# it finds the nested form there
TOOL_EVENTS = ("PreToolUse", "PostToolUse")


def declared_hooks(fabric):
    """The [[hook]] of texo.toml as mount writes them: {root} becomes the working folder."""
    return [{"id": hook["id"], "event": hook["event"], "matcher": hook.get("matcher"),
             "command": hook["command"].replace("{root}", str(fabric.root))} for hook in fabric.hooks]


def hook_entry(hook):
    entry = {"hooks": [{"type": "command", "command": hook["command"]}]}
    if hook.get("matcher") is not None:
        entry = {"matcher": hook["matcher"], **entry}
    return entry


def hooks_file_entry(hook):
    """A [[hook]] as HOOKS_FILE wants it: nested with its matcher for an event about a tool, the command alone
    for any other event (which has no matcher there: the hook runs each time the event happens)."""
    if hook["event"] in TOOL_EVENTS:
        return hook_entry(hook)
    return {"type": "command", "command": hook["command"]}


def check_hooks_file(fabric):
    """The problems of HOOKS_FILE: (level, message). One entry in the wrong form and the assistant that reads
    the file loads none of its hooks, without saying so to the person."""
    path = fabric.root / HOOKS_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [("error", f"{HOOKS_FILE} cannot be read ({error}): no hook of the file is loaded")]
    problems = []
    for hid, events in data.items() if isinstance(data, dict) else []:
        for event, entries in events.items() if isinstance(events, dict) else []:
            for entry in entries if isinstance(entries, list) else []:
                commands = entry.get("hooks") if isinstance(entry, dict) and event in TOOL_EVENTS else [entry]
                if not isinstance(commands, list) or not commands or not all(
                        isinstance(c, dict) and c.get("command") for c in commands):
                    problems.append(("error", f"{HOOKS_FILE}: the hook {hid} ({event}) is not in the form the "
                                              "assistant reads, so no hook of the file is loaded: texo mount"))
    return problems


def hooks_update(fabric):
    """The hooks of the proposal of the session note (texo hook) in the settings of the assistant: ours are
    replaced, what the person set stays."""
    command = texo_command(fabric)

    def ours(entry):
        return any("texo" in h.get("command", "") and " hook " in h.get("command", "")
                   for h in entry.get("hooks", []) if isinstance(h, dict))

    declared = declared_hooks(fabric)
    guest = is_guest(fabric)
    # the commands of the hooks mount wrote last time and writes now: replaced, never doubled
    written = {h.get("command") for h in load_state(fabric).get("hooks", [])} | {h["command"] for h in declared}

    def mine(entry):
        return any(h.get("command") in written for h in entry.get("hooks", []) if isinstance(h, dict))

    def apply(data):
        hooks = data.setdefault("hooks", {})
        for event in list(hooks):
            hooks[event] = [entry for entry in hooks[event] if not (isinstance(entry, dict) and mine(entry))]
            if not hooks[event]:
                del hooks[event]
        # in a guest folder the start of a session is where the rules of the core reach the agent
        events = HOOK_EVENTS + ((("SessionStart", "session-start"),) if guest else ())
        for event, argument in events + (() if guest else (("SessionStart", None),)):
            kept = [entry for entry in hooks.get(event, []) if isinstance(entry, dict) and not ours(entry)]
            if argument:
                kept.append({"hooks": [{"type": "command",
                                        "command": f"{command} --root {fabric.root} hook {argument}"}]})
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)
        for hook in declared:
            hooks.setdefault(hook["event"], []).append(hook_entry(hook))
    return apply


def write_hooks_file(fabric, out):
    """.agents/hooks.json, one key per hook: the hook of the proposal of the session note (texo hook), then the
    [[hook]] of texo.toml; the keys of a previous mount are replaced, those the person wrote stay."""
    declared = declared_hooks(fabric)
    previous = [h.get("id") for h in load_state(fabric).get("hooks", [])]
    command = f"{texo_command(fabric)} --root {fabric.root}"

    def apply(data):
        for hid in [*previous, RULES_HOOK]:
            data.pop(hid, None)
        data[NOTE_HOOK] = {event: [{"type": "command", "command": f"{command} hook {argument}"}]
                           for event, argument in NOTE_HOOK_EVENTS}
        if is_guest(fabric):
            data[RULES_HOOK] = {"SessionStart": [{"type": "command", "command": f"{command} hook session-start"}]}
        for hook in declared:
            data[hook["id"]] = {hook["event"]: [hooks_file_entry(hook)]}
    merge_json(fabric.root / HOOKS_FILE, apply)
    names = [NOTE_HOOK] + ([RULES_HOOK] if is_guest(fabric) else []) + [h["id"] for h in declared]
    out.write(f"[ok] {HOOKS_FILE}: {', '.join(names)}\n")


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

    tracked = tracked_paths(fabric)

    def ours(name, label):
        """Whether mount may write the file: one the repository of a guest folder tracks is left as it is."""
        if name in tracked:
            out.write(f"[warning] {label}: {name} is tracked by the repository, left as it is: what mount would "
                      "write there is missing for that assistant\n")
        return name not in tracked

    if ours(".mcp.json", "Claude Code"):
        merge_json(fabric.root / ".mcp.json", update("mcpServers", "claude"))
        out.write("[ok] Claude Code: .mcp.json\n")
    if ours(".claude/settings.local.json", "Claude Code"):
        merge_json(fabric.root / ".claude" / "settings.local.json", hooks_update(fabric))
        out.write("[ok] Claude Code: .claude/settings.local.json (hooks)\n")
    if ours(HOOKS_FILE, "hooks"):
        write_hooks_file(fabric, out)
    if ours(".gemini/settings.json", "Gemini CLI"):
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
    """Every skill linked where each assistant looks for them. A link that already leads to its skill stays; one
    of a previous mount that leads elsewhere, or to a skill no longer there, is replaced or removed; what the
    person put there that is not a link is never touched."""
    found, shadowed = skill_sources(fabric)
    for message in shadowed:
        out.write(f"[info] {message}\n")
    tracked = tracked_paths(fabric)
    for folder in SKILL_DIRS:
        target_dir = fabric.root / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        wanted = {name: os.path.relpath(source, target_dir) for name, (_layer, source) in found.items()}
        for entry in target_dir.iterdir():
            # a link the repository of a guest folder tracks is the repository's
            if (entry.is_symlink() and wanted.get(entry.name) != os.readlink(entry)
                    and f"{folder}/{entry.name}" not in tracked):
                entry.unlink(missing_ok=True)
        for name, source in wanted.items():
            link = target_dir / name
            if not link.is_symlink() and not link.exists():
                with contextlib.suppress(FileExistsError):
                    link.symlink_to(source)
    out.write(f"[ok] skills: {len(found)} linked in {', '.join(SKILL_DIRS)}\n")
    return sorted(found)


def check_problems(check):
    """The problems of a [[check]] of a pack.toml: a command that counts as a check (a test runner, a linter, a
    build) for the candidate of a lesson the hook of the session note finds."""
    if not isinstance(check, dict) or not isinstance(check.get("name"), str) or not check["name"].strip():
        return ["a [[check]] has a name"]
    try:
        re.compile(check.get("pattern"))
    except (TypeError, re.error) as error:
        return [f"check {check['name']}: pattern is a regular expression ({error})"]
    return []


def write_checks(fabric, out):
    """The [[check]] of the packs in .texo/checks.json, where the hook of the session note reads them next to
    those of the core; no check, no file."""
    checks = [{"name": check["name"], "pattern": check["pattern"], "origin": f"pack {pack['name']}"}
              for pack in fabric.packs for check in (packs.manifest(fabric, pack) or {}).get("check") or []]
    path = fabric.state_dir / "checks.json"
    if checks:
        files.write_text(path, json.dumps({"checks": checks}, indent=2, ensure_ascii=False) + "\n")
        out.write(f"[ok] checks of the packs: {', '.join(check['name'] for check in checks)}\n")
    elif path.is_file():
        path.unlink()


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


def exclude_file(fabric):
    """The file of a repository that keeps paths out of git without being versioned itself."""
    result = threads.run(["git", "rev-parse", "--git-path", "info/exclude"], cwd=fabric.root)
    path = result.stdout.strip() if result.returncode == 0 else ""
    return (fabric.root / path) if path else fabric.root / ".git" / "info" / "exclude"


def ignore_generated(fabric, out):
    """The files mount generates and the working folders stay out of git: the missing lines go to .gitignore,
    or, in a guest folder, to the exclude file of the repository, with texo.toml, so that no tracked file
    changes and git status stays as it was."""
    guest = is_guest(fabric)
    path = exclude_file(fabric) if guest else fabric.root / ".gitignore"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    wanted = list(IGNORED) + [f"{folder}/" for folder in work_dirs(fabric)]
    wanted.append(HOOKS_FILE)
    if guest:
        wanted.append("texo.toml")
    # the files of the assistants mount wrote; those the person wrote are theirs to version
    wanted += [name for name in AGENT_FILES + POINTERS if (fabric.root / name).is_file()
               and GENERATED in (fabric.root / name).read_text(encoding="utf-8")]
    missing = [entry for entry in wanted if entry not in lines]
    if missing:
        block = ["", "# generated by texo mount"] if lines else ["# generated by texo mount"]
        files.write_text(path, "\n".join(lines + block + missing) + "\n")
        name = os.path.relpath(path, fabric.root) if guest else ".gitignore"
        out.write(f"[ok] {name}: {', '.join(missing)}\n")


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


def config_hash(remote):
    """The fingerprint of a configuration read from the hub: sha256 of its canonical JSON, without the day it
    was read. Computed here, so the hub needs no field for it."""
    content = {key: value for key, value in (remote or {}).items() if key != "fetched"}
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_environment(fabric):
    try:
        return json.loads((fabric.state_dir / ENVIRONMENT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def refresh(fabric, out, client=None):
    """The configuration of the organisation from its hub, kept in .texo/config.json with its fingerprint in
    .texo/environment.json; the copy kept there when the hub does not answer. True when the hub answered."""
    try:
        client = client or hub.Hub(*fabric.hub())
        # a hub that does not even accept a connection is given up soon; one that answers slowly is waited for
        if hasattr(client, "check_reachable"):
            client.check_reachable(CONNECT_TIMEOUT)
        remote = client.call("config")
    except (ConfigError, hub.HubError) as error:
        kept = fabric.remote.get("fetched")
        out.write(f"[warning] hub: {error}; " + (f"the configuration read on {kept} is used\n" if kept else
                                                 "only texo.toml is used\n"))
        return False
    if remote.get("organisation") and remote["organisation"] != fabric.organisation:
        out.write(f"[warning] the hub names the organisation {remote['organisation']}, texo.toml "
                  f"{fabric.organisation}: the credentials file is named after texo.toml\n")
    remote["fetched"] = datetime.date.today().isoformat()
    fingerprint = config_hash(remote)
    unchanged = load_environment(fabric).get("config_hash") == fingerprint
    fabric.save_remote(remote)
    files.write_text(fabric.state_dir / ENVIRONMENT_FILE, json.dumps(
        {"config_hash": fingerprint, "config_read": remote["fetched"], "core": __version__}, indent=2) + "\n")
    out.write(f"[ok] hub: {len(remote.get('packs') or [])} packs, {len(remote.get('threads') or [])} threads"
              f"{', as at the last mount' if unchanged else ''}\n")
    return True


AGENT_FILES = ("AGENTS.md", "ARCHITECTURE.md", "DESIGN.md")
POINTERS = ("CLAUDE.md", "GEMINI.md")
# the rules the person writes for this folder: mount never writes it, AGENTS.md leads to it
LOCAL_RULES = "AGENTS.local.md"
LOCAL_SECTION = f"""
## Le regole di questa cartella

Questa cartella ha regole proprie in `{LOCAL_RULES}`, scritte dalla persona e versionate con la cartella: leggile
all'apertura. Valgono insieme a queste; dove le due dicono cose diverse, vale la più prudente.
"""
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
    if (fabric.root / LOCAL_RULES).is_file():
        lines.append(f"- Regole proprie della cartella: `{LOCAL_RULES}`, della persona, mai scritto da `texo mount`.")
    if is_guest(fabric):
        lines.append("- Modo ospite: la cartella è un repository con le sue regole (`AGENTS.md`), che `texo mount` "
                     "non tocca. Questo file e gli altri generati stanno in `.texo/`; l'hook di avvio sessione dice "
                     "all'agente dove sono.")
    if fabric.hooks:
        declared = ", ".join(f"`{h['id']}` ({h['event']})" for h in fabric.hooks)
        lines.append(f"- Hook dichiarati in `texo.toml`: {declared}.")
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
    local = (fabric.root / LOCAL_RULES).is_file()
    files = {
        "AGENTS.md": f"{GENERATED}\n{source(core / 'AGENTS.md')}\n" + (LOCAL_SECTION if local else ""),
        "ARCHITECTURE.md": f"{GENERATED}\n{source(TEMPLATES / 'ARCHITECTURE.md')}\n\n{folder}",
        "DESIGN.md": f"{GENERATED}\n{design.rstrip()}\n",
    }
    imported = AGENT_FILES[:1] + ((LOCAL_RULES,) if local else ()) + AGENT_FILES[1:]
    pointer = GENERATED + "\n" + "".join(f"@{name}\n" for name in imported) + "@.texo/THREADS.md\n"
    files.update({name: pointer for name in POINTERS})
    return files


def write_agent_files(fabric, out):
    """The files the assistants read. In a guest folder (is_guest) the repository has its own: the three files
    of the core go to .texo/, no pointer is written, and the hook of the start of a session tells the agent
    where they are (hooks.session_start)."""
    generated = agent_files(fabric)
    if is_guest(fabric):
        for name in AGENT_FILES:
            files.write_text(fabric.state_dir / name, generated[name])
        out.write(f"[ok] guest of a repository with its own AGENTS.md: {', '.join(AGENT_FILES)} in .texo/, given "
                  "to the agent by the hook of the start of a session; no tracked file is touched\n")
        return
    for name in AGENT_FILES:
        # what a mount as a guest left: here the rules are at the root, and the hook has nothing to say
        (fabric.state_dir / name).unlink(missing_ok=True)
    for name, content in generated.items():
        path = fabric.root / name
        if path.exists() and GENERATED not in path.read_text(encoding="utf-8"):
            out.write(f"[info] {name} is yours, left as it is: make it lead to the rules of the core "
                      f"({Path(__file__).resolve().parent.parent / 'AGENTS.md'}) and to .texo/THREADS.md\n")
            continue
        files.write_text(path, content)
    out.write(f"[ok] {', '.join(AGENT_FILES + POINTERS)}\n")


@contextlib.contextmanager
def mount_lock(fabric, out, wait=None):
    """One mount at a time in a folder: the second waits for the first, then mounts on what it left. Gives
    whether the folder is ours: False when the other mount is still at work after wait seconds."""
    fabric.state_dir.mkdir(exist_ok=True)
    wait = LOCK_WAIT if wait is None else wait
    with open(fabric.state_dir / LOCK_FILE, "a", encoding="utf-8") as handle:
        if fcntl is None:
            yield True
            return
        deadline, waited = time.monotonic() + wait, False
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                if not waited:
                    out.write("[info] another texo mount is at work in this folder: waiting for it\n")
                    waited = True
                time.sleep(0.1)
        try:
            if waited:
                # what the other mount read from the hub, not what this process read before waiting
                fabric.remote = fabric.cached_remote()
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def mount(fabric, allow_install=False, out=sys.stdout, client=None, offline=False, lock_wait=None):
    """Mount the folder: MOUNTED, FAILED, or FROM_CACHE when all is mounted but the hub did not answer and the
    configuration kept in the folder was used (with --offline the person asked for it: MOUNTED)."""
    with mount_lock(fabric, out, lock_wait) as ours:
        if not ours:
            out.write("[error] another texo mount is still at work in this folder: nothing mounted, try again\n")
            return FAILED
        return mount_folder(fabric, allow_install, out, client, offline)


def mount_folder(fabric, allow_install, out, client, offline):
    answered = offline or refresh(fabric, out, client)
    failed = False
    for pack in fabric.packs:
        if not re.match(r"^[a-z][a-z0-9_]*$", pack.get("name") or "") or not version_tuple(pack.get("version")):
            continue
        status, message = packs.install(fabric, pack)
        out.write(f"[{status}] pack {pack['name']} {pack['version']}: {message}\n")
        failed |= status == "error"
    if report(check_fabric(fabric), out) or failed:
        out.write("Nothing mounted: fix the errors (the configuration in the hub, or texo.toml).\n")
        return FAILED
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
    files.write_text(fabric.state_dir / "THREADS.md", threads_markdown(fabric, states))
    write_checks(fabric, out)
    servers = write_assistants(fabric, out)
    skills = link_skills(fabric, out)
    for folder in work_dirs(fabric):
        (fabric.root / folder).mkdir(parents=True, exist_ok=True)
    write_agent_files(fabric, out)
    ignore_generated(fabric, out)
    state = {"core": __version__, "packs": fabric.packs,
             "threads": [dict(t, **states[t["id"]]) for t in fabric.threads],
             "mcp_servers": [name for name in servers if name != HUB_SERVER], "skills": skills,
             "hooks": [{k: h[k] for k in ("id", "event", "command")} for h in declared_hooks(fabric)]}
    files.write_text(fabric.state_dir / "threads.json", json.dumps(state, indent=2) + "\n")
    out.write("[ok] .texo/THREADS.md\n")
    if any(s["status"] == "pending" for s in states.values()):
        out.write("Some threads wait for an installation: texo mount --yes runs the commands listed above.\n")
    if failed:
        return FAILED
    return MOUNTED if answered else FROM_CACHE


def doctor(fabric, out=sys.stdout, client=None):
    failed = report(check_fabric(fabric) + check_hooks_file(fabric), out)
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
    doctor_hub_tools(client, out)
    return False


def doctor_hub_tools(client, out):
    """The tools of the hub against the ones this core asks a confirmation for (hub.WRITE_TOOLS): the hub says
    which of its tools write, and the two lists must agree on the tools both know. Never an error: an older
    hub says nothing, and the session still works."""
    status, message, tools = client.tools()
    if tools is None:
        out.write(f"[warning] hub tools: not listed ({message})\n")
        return
    writers, silent = threads.tools_that_write(tools)
    names = {str(tool.get("name")) for tool in tools}
    if silent:
        out.write(f"[warning] hub tools: {len(tools)}, {len(silent)} that do not say whether they write "
                  f"(a hub before texo_mcp 20.0.1.5.0?): {', '.join(silent)}\n")
        return
    known = set(hub.OPERATIONS)
    only_hub = sorted((set(writers) & known) - set(hub.WRITE_TOOLS))
    only_core = sorted((set(hub.WRITE_TOOLS) & names) - set(writers))
    if only_hub or only_core:
        out.write(f"[warning] hub tools: the hub and this core do not agree on what writes"
                  f"{'; no confirmation asked here for: ' + ', '.join(only_hub) if only_hub else ''}"
                  f"{'; the hub says they only read: ' + ', '.join(only_core) if only_core else ''}\n")
        return
    out.write(f"[ok] hub tools: {len(tools)}, {len(writers)} that write, as this core expects\n")


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
        token = fabric.secret(thread["auth"]) if thread.get("auth") else None
        return threads.write_audit(thread, *threads.mcp_http_tools(thread["url"], token))
    if driver == "mcp-stdio":
        env = thread_env(fabric, thread)
        return threads.write_audit(thread, *threads.mcp_stdio_tools(
            [thread["command"], *thread.get("args", [])], env=env, cwd=fabric.root))
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
