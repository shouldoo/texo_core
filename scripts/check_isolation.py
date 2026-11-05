#!/usr/bin/env python3
"""check_isolation.py — a Texo repository depends on nothing outside itself and holds no customer.

Checks every tracked text file:
  1. no absolute home paths (/home/<user>/, /Users/<user>/);
  2. no name from the isolation list: the customers, people and places that must never appear in a shared
     repository (core, hub, industry, demo customers), one regular expression per line. The list is never
     versioned: in CI it comes from the secret of the organisation (the variable ISOLATION_PATTERNS), on a
     machine from ~/.config/texo/isolation-forbidden.txt or the file named by ISOLATION_FORBIDDEN;
  3. every `setup/...` or `scripts/...` script a file mentions exists in the repository;
  4. no data/ folder: documents of a customer are never committed.

    python3 scripts/check_isolation.py [--root <repository>]
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_FILE = "~/.config/texo/isolation-forbidden.txt"
# /home/odoo/ is the home of the odoo user inside the official Odoo images, not a local home.
# not after a host name or a path segment: «www.example.org/home/docs/» is a web address, not a home folder
HOME_PATH = re.compile(r"(?<![\w.-])/(?:home|Users)/(?!<|odoo/)[a-z][a-z0-9._-]*/")
SCRIPT_REF = re.compile(r"(?<![\w/.-])((?:setup|scripts)/[A-Za-z0-9_./-]+\.(?:sh|py))\b")
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yml", ".yaml", ".json", ".sql", ".toml", ".txt", ".template", ".xml", ""}
SELF = Path(__file__).resolve()


def tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True).stdout
    return [root / p for p in out.split("\0") if p]


def forbidden_patterns() -> list[str]:
    """The isolation list: the secret of the organisation in CI, a local file on a machine."""
    if os.environ.get("ISOLATION_PATTERNS"):
        lines = os.environ["ISOLATION_PATTERNS"].splitlines()
    else:
        path = Path(os.environ.get("ISOLATION_FORBIDDEN") or FORBIDDEN_FILE).expanduser()
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def check(root: Path, patterns: list[str]) -> list[str]:
    errors = []
    forbidden = re.compile("|".join(patterns), re.IGNORECASE) if patterns else None
    for path in tracked_files(root):
        rel = path.relative_to(root)
        if rel.parts[0] == "data":
            errors.append(f"{rel}: documents of a customer are never committed")
            continue
        if path.resolve() == SELF or path.suffix not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        in_skill = rel.parts[0] == "skills"
        for lineno, line in enumerate(text.splitlines(), 1):
            if HOME_PATH.search(line):
                errors.append(f"{rel}:{lineno}: absolute home path")
            m = forbidden.search(line) if forbidden else None
            if m:
                errors.append(f"{rel}:{lineno}: a name of the isolation list ({m.group(0)})")
            if in_skill:
                continue  # the scripts of a skill are relative to the skill folder
            for ref in SCRIPT_REF.findall(line):
                if not (root / ref).exists() and not (root / "core" / ref).exists():
                    errors.append(f"{rel}:{lineno}: script not found in this repository: {ref}")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="a Texo repository, isolated")
    parser.add_argument("--root", default=".", help="the repository (default: the current directory)")
    root = Path(parser.parse_args(argv).root).resolve()
    patterns = forbidden_patterns()
    errors = check(root, patterns)
    for e in errors:
        print(e)
    if not patterns:
        print("warning: no isolation list (ISOLATION_PATTERNS or ~/.config/texo/isolation-forbidden.txt): "
              "only paths and scripts were checked")
    print(f"{len(errors)} problem(s)" if errors else "isolation check passed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
