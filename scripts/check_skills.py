#!/usr/bin/env python3
"""check_skills.py — validate the structure of the skills of a Texo repository (CI).

Every directory under skills/ must contain a SKILL.md whose YAML frontmatter has `name` equal to the
directory name and a non-empty `description`. Standard library only.

    python3 scripts/check_skills.py [--root <repository>]
"""
import argparse
import re
import sys
from pathlib import Path


def frontmatter(text: str) -> list[str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    return text[4:end].splitlines() if end != -1 else None


def check(skill_dir: Path) -> list[str]:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return [f"{skill_dir}: missing SKILL.md"]
    lines = frontmatter(skill_file.read_text(encoding="utf-8"))
    if lines is None:
        return [f"{skill_file}: missing or malformed YAML frontmatter"]
    errors = []
    name = next((m.group(1).strip() for line in lines if (m := re.match(r"name:\s*(.*)", line))), None)
    if name != skill_dir.name:
        errors.append(f"{skill_file}: name {name!r} does not match directory {skill_dir.name!r}")
    for i, line in enumerate(lines):
        m = re.match(r"description:\s*(.*)", line)
        if m:
            inline = m.group(1).strip()
            body = [ln for ln in lines[i + 1:] if ln.startswith((" ", "\t")) and ln.strip()]
            if inline in ("", ">", ">-", "|", "|-") and not body:
                errors.append(f"{skill_file}: empty description")
            break
    else:
        errors.append(f"{skill_file}: missing description")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="the skills of a Texo repository")
    parser.add_argument("--root", default=".", help="the repository (default: the current directory)")
    skills = Path(parser.parse_args(argv).root).resolve() / "skills"
    if not skills.is_dir():
        print("no skills/: nothing to check")
        return 0
    errors = [e for d in sorted(skills.iterdir()) if d.is_dir() for e in check(d)]
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        return 1
    print("skills check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
