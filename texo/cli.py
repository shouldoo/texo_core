"""texo: the command line of Texo.

The commands of the memory (texo/hub.py) talk to the hub as the person; the other commands work
on the working folder the current directory belongs to (or --root):

    texo init <hub url> <organisation>   make the current folder a working folder of the organisation, then mount
    texo mount [--yes] [--offline]   the configuration of the hub: packs, threads, assistants, skills, AGENTS.md
    texo doctor                   check that the hub and every thread answer and every credential is there
    texo threads                  the threads of the folder (also a tool of the MCP server memoria)
    texo thread <id> ls|read|search ...   read a git-remote source at its pinned ref, without cloning it
    texo seed [--apply --yes]     the seed of the packs into the hub (administrators)
    texo where [--pack <name>]    where the core (or an installed pack) is on this machine
    texo config                   the configuration of the organisation in its hub: packs and threads
    texo config-set <file> [--apply --yes]   administrators: the hub made to say what the file says
    texo run-thread <id>          started by the assistants: an MCP thread with its credentials
    texo mcp                      the MCP server memoria over stdio
"""
import base64
import json
import os
import sys
import tomllib
from pathlib import Path

from . import bridge, hooks, hub, mount, packs, seed, setup_assistants, threads
from .config import ConfigError, Fabric, find_root, hub_settings, write_texo_toml

LOCAL = ("init", "mount", "doctor", "threads", "thread", "run-thread", "version", "where", "hook")


def extend(sub):
    p = sub.add_parser("init", help="make the current folder a working folder of the organisation, then mount")
    p.add_argument("hub_url")
    p.add_argument("organisation", help="the slug of the organisation: ~/.config/texo/<slug>.env")
    p = sub.add_parser("mount", help="the configuration of the hub: packs, threads, assistants, skills, AGENTS.md")
    p.add_argument("--yes", action="store_true", help="run the install commands of the cli threads")
    p.add_argument("--offline", action="store_true", help="the configuration read last time, without the hub")
    p = sub.add_parser("hook", help="called by the hooks of an assistant (its JSON on stdin): the proposal of the "
                                   "session note in .texo/proposals/, and once per session the request to propose it")
    p.add_argument("event", choices=hooks.EVENTS)
    p = sub.add_parser("where", help="where the core, or an installed pack, is on this machine")
    p.add_argument("--pack")
    sub.add_parser("doctor", help="check the hub, the threads and the credentials")
    sub.add_parser("threads", help="the threads of the folder, as texo mount left them")
    p = sub.add_parser("thread", help="read a git-remote source at its pinned ref")
    p.add_argument("thread_id")
    p.add_argument("action", choices=("ls", "read", "search"))
    p.add_argument("argument", nargs="?", default="", help="the path (ls, read) or the query (search)")
    p = sub.add_parser("seed", help="the seed of the packs into the hub: a dry run, then --apply --yes")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("run-thread", help="an MCP thread with its credentials (started by the assistants)")
    p.add_argument("thread_id")
    sub.add_parser("version")
    sub.add_parser("config", help="the configuration of the organisation in its hub: packs and threads")
    p = sub.add_parser("config-set", help="administrators: the configuration of the hub from a TOML file")
    p.add_argument("file", help="TOML with [[pack]] and/or [[thread]] (a list left out is not touched), "
                                "optional [texo] organisation")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--yes", action="store_true")


def fabric_of(args):
    root = find_root(args.root)
    if not root:
        raise ConfigError("no texo.toml above the current directory: run texo init in a working folder, or pass --root")
    return Fabric(root)


def local(args, out, err):
    if args.command == "version":
        from . import __version__
        out.write(f"texo {__version__}\n")
        return 0
    if args.command == "hook":
        try:
            return hooks.run(args.event, root=find_root(args.root) if args.root else None, out=out)
        except Exception:  # noqa: BLE001 - a hook never fails the assistant
            return 0
    if args.command == "init":
        root = Path(args.root or os.getcwd()).resolve()
        write_texo_toml(root, args.organisation, args.hub_url)
        out.write(f"[ok] {root / 'texo.toml'}\n")
        setup_assistants.trust(root, args.organisation, out)
        return mount.mount(Fabric(root), out=out)
    if args.command == "where" and not args.pack:
        out.write(f"{Path(__file__).resolve().parent.parent}\n")
        return 0
    fabric = fabric_of(args)
    if args.command == "where":
        pack = next((p for p in fabric.packs if p.get("name") == args.pack), None)
        if not pack:
            raise ConfigError(f"no pack {args.pack} in the configuration of the organisation")
        out.write(f"{packs.folder(fabric, pack)}\n")
        return 0
    if args.command == "mount":
        return mount.mount(fabric, allow_install=args.yes, out=out, offline=args.offline)
    if args.command == "doctor":
        return mount.doctor(fabric, out=out)
    if args.command == "threads":
        client = hub.Hub("", "")
        client.threads = mount.load_state(fabric).get("threads", [])
        data = hub.op_threads(client, {})
        out.write((json.dumps(data, indent=2, ensure_ascii=False) if args.json else hub.render("threads", data)) + "\n")
        return 0
    thread = mount.thread_by_id(fabric, args.thread_id)
    if args.command == "run-thread":
        bridge.run_thread(fabric, thread)
        return 0
    if thread.get("driver") != "git-remote":
        raise ConfigError(f"{thread['id']} is not a git-remote source: {mount.how_to_use(thread)}")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if args.action == "ls":
        data = threads.remote_list(thread, args.argument, token)
        out.write("\n".join(f"{e['path']}{'/' if e['type'] == 'dir' else ''}" for e in data) + "\n")
    elif args.action == "read":
        out.write(threads.remote_read(thread, args.argument, token))
    else:
        data = threads.remote_search(thread, args.argument, token)
        out.write("\n".join(e["path"] for e in data) + ("\n" if data else "no hit\n"))
    return 0


def config_payload(path, apply):
    """The payload of admin/config from a TOML file: the lists it has, the slug if it names one."""
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    payload = {"apply": bool(apply)}
    if "pack" in data:
        payload["packs"] = data["pack"]
    if "thread" in data:
        payload["threads"] = data["thread"]
    if (data.get("texo") or {}).get("organisation"):
        payload["slug"] = data["texo"]["organisation"]
    if len(payload) == 1:
        raise ConfigError(f"{path} has no [[pack]], no [[thread]] and no [texo] organisation: nothing to set")
    return payload


def render_config(data):
    lines = [f"organisation {data.get('organisation')} ({data.get('company')})"]
    lines += [f"pack {p['name']} {p['version']}" for p in data.get("packs") or []]
    lines += [f"thread {t['id']} [{t['type']}, {t['driver']}, {t['data_class']}, writes {t.get('writes', 'never')}]"
              for t in data.get("threads") or []]
    return "\n".join(lines)


def render_changes(answer):
    counts = ", ".join(f"{n} {status}" for status, n in sorted(answer["counts"].items())) or "nothing"
    lines = [f"{counts}{'' if answer['applied'] else ' (dry run: texo config-set <file> --apply --yes)'}"]
    for item in answer["items"]:
        if item["status"] != "unchanged":
            changes = f" ({', '.join(item['changes'])})" if item.get("changes") else ""
            lines.append(f"  [{item['status']}] {item['kind']} {item['key']}{changes}")
    return "\n".join(lines)


def connect(args):
    url, token = hub_settings(args.root)
    client = hub.Hub(url, token)
    root = find_root(args.root)
    if root:
        client.threads = mount.load_state(Fabric(root)).get("threads", [])
    return client


def main(argv=None, out=sys.stdout, err=sys.stderr):
    args = hub.build_parser(extend).parse_args(argv)
    try:
        if args.command in LOCAL:
            return local(args, out, err)
        client = connect(args)
        if args.command == "mcp":
            hub.serve_mcp(client)
            return 0
        if args.command == "config":
            data = client.call("config")
            out.write((json.dumps(data, indent=2, ensure_ascii=False) if args.json else render_config(data)) + "\n")
            return 0
        if args.command == "config-set":
            if args.apply and not args.yes:
                err.write("refused: --apply writes to the hub and needs --yes, after the person agreed\n")
                return 2
            answer = client.call("admin/config", config_payload(args.file, args.apply))
            out.write(render_changes(answer) + "\n")
            return 0
        if args.command == "seed":
            if args.apply and not args.yes:
                err.write("refused: --apply writes to the hub and needs --yes, after the person agreed\n")
                return 2
            return seed.seed(fabric_of(args), client, apply=args.apply, out=out)
        name = args.command.replace("-", "_")
        skip = ("command", "json", "yes", "okf", "root")
        values = {key: value for key, value in vars(args).items() if key not in skip}
        if args.okf:
            values["format"] = "okf"
        if name in hub.WRITE_TOOLS and not args.yes:
            err.write("refused: a write needs --yes, after the person agreed in the session\n")
            return 2
        if name == "document_write" and values.pop("text_file", None):
            with open(args.text_file, encoding="utf-8") as handle:
                values["text"] = handle.read()
        if name == "document_write" and values.pop("file", None):
            with open(args.file, "rb") as handle:
                values["data"] = base64.b64encode(handle.read()).decode()
            values["name"] = values.get("name") or os.path.basename(args.file)
        if name == "query":
            values["domain"] = json.loads(values["domain"]) if values.get("domain") else []
            values["fields"] = [f.strip() for f in values["fields"].split(",")] if values.get("fields") else []
        data = hub.OPERATIONS[name](client, values)
    except hub.HubError as error:
        err.write(f"error{' ' + str(error.status) if error.status else ''}: {error}\n")
        return 1
    except ConfigError as error:
        err.write(f"error: {error}\n")
        return 1
    except ValueError as error:
        err.write(f"error: {error}\n")
        return 2
    out.write((json.dumps(data, indent=2, ensure_ascii=False) if args.json else hub.render(name, data)) + "\n")
    return 0
