import sys


def hook_event(argv):
    """The event of `texo [--root DIR] hook <event>`, with its root, or None: the command an assistant runs at
    each of its turns is answered here, without loading the rest of the CLI (the client of the hub above all)."""
    root, words = None, list(argv)
    if words[:1] == ["--root"] and len(words) > 1:
        root, words = words[1], words[2:]
    elif words and words[0].startswith("--root="):
        root, words = words[0].split("=", 1)[1], words[1:]
    return (words[1], root) if len(words) == 2 and words[0] == "hook" else None


def main():
    hook = hook_event(sys.argv[1:])
    if hook:
        from . import hooks
        if hook[0] in hooks.EVENTS:
            try:
                from .config import find_root
                return hooks.run(hook[0], root=find_root(hook[1]) if hook[1] else None)
            except Exception:  # noqa: BLE001 - a hook never fails the assistant
                return 0
    from .cli import main as cli
    return cli()


sys.exit(main())
