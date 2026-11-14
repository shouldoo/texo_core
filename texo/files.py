"""Writing the files of a working folder: only when the content changes, and never half a file.

texo mount runs again and again on the same folder (a new session, a hook, two terminals). A file whose content
is already right is left alone, so its date says when it last changed and a tool that watches the folder is not
woken for nothing; a file that changes is written next to itself and renamed, so a reader never finds half of it.
"""
import os
from pathlib import Path


def write_text(path, text, mode=None):
    """Write text to path if it is not already there; True when the file was written. A link is followed: the
    file it leads to is the one replaced. mode, for a file that holds a profile, is set either way."""
    path = Path(path)
    target = Path(os.path.realpath(path)) if path.is_symlink() else path
    try:
        same = target.read_text(encoding="utf-8") == text
    except (OSError, ValueError):
        same = False
    if not same:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(text, encoding="utf-8")
            if target.exists():
                os.chmod(temporary, target.stat().st_mode & 0o7777)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    if mode is not None and target.stat().st_mode & 0o7777 != mode:
        os.chmod(target, mode)
    return not same
