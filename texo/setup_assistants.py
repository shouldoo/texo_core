"""What texo init prepares for the assistants once per working folder: Claude Code trusts the folder, and
Antigravity, when it is installed, gets a profile of its own for the organisation (its MCP servers are filled by
texo mount). Every file is merged, never overwritten, and kept readable by the person only.
"""
import json
import os
import shutil
from pathlib import Path


def merge_private_json(path, update):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    update(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    os.chmod(path, 0o600)


def trust(root, organisation, out):
    root = str(root)
    merge_private_json(Path("~/.claude.json").expanduser(), lambda data: data.setdefault("projects", {}).setdefault(
        root, {}).__setitem__("hasTrustDialogAccepted", True))
    out.write("[ok] Claude Code: folder trusted\n")
    if not (shutil.which("agy") or shutil.which("antigravity")):
        return
    profile = Path(os.environ.get("TEXO_AGY_PROFILE", f"~/.antigravity-texo-{organisation}")).expanduser()
    (profile / ".gemini" / "config").mkdir(parents=True, exist_ok=True)
    (profile / ".gemini" / "antigravity-cli").mkdir(parents=True, exist_ok=True)
    os.chmod(profile, 0o700)
    for item in (".gitconfig", ".ssh", ".local", ".config"):
        source, link = Path.home() / item, profile / item
        if source.exists() and not link.exists():
            link.symlink_to(source)

    def add_root(data):
        trusted = data.setdefault("trustedWorkspaces", [])
        if root not in trusted:
            trusted.append(root)

    merge_private_json(profile / ".gemini" / "antigravity-cli" / "settings.json", add_root)
    out.write(f"[ok] Antigravity profile {profile} (log in once with: HOME=\"{profile}\" agy)\n")
