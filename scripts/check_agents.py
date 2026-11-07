#!/usr/bin/env python3
"""check_agents.py — keep a Texo repository independent from any one AI assistant (CI).

- CLAUDE.md and GEMINI.md, where present, are pointers: they import AGENTS.md and hold no rules of their own;
- every SKILL.md frontmatter uses only the portable keys `name` and `description`;
- the rules, skills, docs and playbooks name actions by what they do, not by one assistant's tool names,
  variables or configuration paths.

    python3 scripts/check_agents.py [--root <repository>]

Standard library only.
"""
import argparse
import re
import sys
from pathlib import Path

POINTERS = ("CLAUDE.md", "GEMINI.md")
POINTER_MAX_LINES = 8
PORTABLE_KEYS = {"name", "description"}
SCANNED = ("AGENTS.md", "skills", "docs", "playbooks", "conventions", "reference", "knowledge", "setup/templates/cartella")
ASSISTANT_SPECIFIC = [
    (re.compile(r"`(Read|Write|Edit|MultiEdit|Bash|Grep|Glob|TodoWrite|AskUserQuestion|WebFetch|WebSearch|"
                r"NotebookEdit|SlashCommand)`"), "tool name of one assistant"),
    (re.compile(r"\$\{?CLAUDE_[A-Z_]+"), "Claude Code variable"),
    (re.compile(r"\$ARGUMENTS\b"), "slash-command argument"),
    (re.compile(r"\.claude/(skills|commands|agents|settings)|\.gemini/(config|settings)"),
     "configuration path of one assistant"),
]
# the documents that explain how texo mount configures each assistant name their files
EXPLAINS_ASSISTANTS = ("docs/fili.md", "README.md")


def check_pointers(root: Path) -> list[str]:
    errors = []
    for name in POINTERS:
        path = root / name
        if not path.is_file():
            continue
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not any(ln.strip().startswith("@") and ln.strip().endswith("AGENTS.md") for ln in lines):
            errors.append(f"{name}: does not import AGENTS.md")
        if len(lines) > POINTER_MAX_LINES:
            errors.append(f"{name}: {len(lines)} lines; rules belong in AGENTS.md, keep this file a pointer")
    return errors


def frontmatter_keys(text: str) -> list[str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return [m.group(1) for ln in text[4:end].splitlines() if (m := re.match(r"([A-Za-z_-]+):", ln))]


def check_frontmatter(root: Path) -> list[str]:
    errors = []
    for skill in sorted((root / "skills").glob("*/SKILL.md")):
        keys = frontmatter_keys(skill.read_text(encoding="utf-8"))
        extra = sorted(set(keys or []) - PORTABLE_KEYS)
        if extra:
            errors.append(f"{skill.relative_to(root)}: non-portable frontmatter keys {extra}")
    return errors


def scanned_files(root: Path):
    for base in SCANNED:
        path = root / base
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from sorted(path.rglob("*.md"))


def check_text(root: Path) -> list[str]:
    errors = []
    for path in scanned_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in EXPLAINS_ASSISTANTS:
            continue
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern, what in ASSISTANT_SPECIFIC:
                if m := pattern.search(line):
                    errors.append(f"{rel}:{no}: {what} {m.group(0)!r}")
    return errors


def check(root: Path) -> list[str]:
    return check_pointers(root) + check_frontmatter(root) + check_text(root)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="a Texo repository, independent from any one assistant")
    parser.add_argument("--root", default=".", help="the repository (default: the current directory)")
    errors = check(Path(parser.parse_args(argv).root).resolve())
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        return 1
    print("agents check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
