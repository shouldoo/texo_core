#!/usr/bin/env python3
"""check_okf.py — the knowledge of an industry as an Open Knowledge Format bundle (CI).

knowledge/ is the procedural memory of an industry; its names follow Open Knowledge Format
(OKF v0.2, https://github.com/GoogleCloudPlatform/open-knowledge-format; docs/memoria.md,
«Nomenclatura»), like the memory the hub serves. Every Markdown file is a concept:

    ---
    type: "Reference"                   # required: Reference, Playbook, Pattern, Convention, Ontology, Index
    title: "Models & ORM — Delta Odoo 19"
    description: "One line: what the file is for."
    tags: ["models", "v19"]
    ---

Values are JSON, which is YAML (a plain scalar is accepted too). The root index is INDEX.md, kept
in capitals because the whole industry points to it: a concept of type Index with the okf_version
of the bundle, where OKF would have an index.md without frontmatter.

    python3 scripts/check_okf.py [--root <repository>]           # check, exit 1 on an error
    python3 scripts/check_okf.py [--root <repository>] --write   # give a frontmatter to the files that have none

--write derives the frontmatter from the file: the type from its folder, the title from its
first heading, the description from its first quoted line (else its first paragraph), the tags
from its name and its version. Read the descriptions it writes before committing them.
Standard library only.
"""
import argparse
import json
import re
import sys
from pathlib import Path

BUNDLE = "knowledge"
OKF_VERSION = "0.2"
REQUIRED = ("type", "title", "description")
DESCRIPTION = 160
KEY = re.compile(r"^([a-z_]+):\s*(.*)$")
VERSION = re.compile(r"^v(\d+)$")
# A sentence ends before a capital, not at an abbreviation such as «es.».
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý«`(])")
# Opening sentences that many files share: their description starts from the title instead.
GENERIC = ("Pattern comuni", "Da leggere INSIEME", "Contenuto valido solo")


def split(text):
    """(frontmatter lines, body) of a file; (None, text) without a frontmatter."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 3)
    if end == -1:
        return None, text
    return text[4:end].split("\n"), text[end + 5:]


def value(raw):
    """A frontmatter value: JSON (which is YAML), else a plain scalar."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except ValueError:
        if raw[:1] in "[{\"'":
            raise
        return raw


def parse(text):
    """The frontmatter of a concept as a dict, or None; ValueError on a line that is not key: value."""
    lines, _body = split(text)
    if lines is None:
        return None
    meta = {}
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = KEY.match(line)
        if not match:
            raise ValueError(f"not a key: value line: {line!r}")
        meta[match[1]] = value(match[2])
    return meta


def check_file(path, rel):
    errors = []
    try:
        meta = parse(path.read_text(encoding="utf-8"))
    except ValueError as error:
        return [f"{rel}: frontmatter: {error}"]
    if meta is None:
        return [f"{rel}: no frontmatter (python3 scripts/check_okf.py --write)"]
    for key in REQUIRED:
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            errors.append(f"{rel}: no {key}")
    if "tags" in meta and not (isinstance(meta["tags"], list) and all(isinstance(t, str) for t in meta["tags"])):
        errors.append(f"{rel}: tags is a list of strings")
    if rel == f"{BUNDLE}/INDEX.md" and meta.get("okf_version") != OKF_VERSION:
        errors.append(f"{rel}: the root index carries okf_version {OKF_VERSION!r}")
    if path.name == "index.md":
        errors.append(f"{rel}: index.md is reserved by OKF; the index of knowledge/ is INDEX.md")
    return errors


def check(root):
    errors = []
    for path in sorted((root / BUNDLE).rglob("*.md")):
        errors += check_file(path, path.relative_to(root).as_posix())
    return errors


# -- writing --------------------------------------------------------------------------------

def okf_type(rel):
    parts = rel.split("/")
    if rel == f"{BUNDLE}/INDEX.md":
        return "Index"
    if rel == f"{BUNDLE}/core-conventions.md":
        return "Convention"
    if parts[1] == "playbooks":
        return "Playbook"
    if parts[1] == "patterns":
        return "Pattern"
    if parts[1:3] == ["reference", "ontology"] and parts[-1] != "README.md":
        return "Ontology"
    return "Reference"


def tags(rel):
    parts = rel[:-3].split("/")[1:]
    result = []
    for part in parts:
        if VERSION.match(part):
            result.append(part)
        elif part in ("legacy", "ontology"):
            result.append(part)
    stem = parts[-1].lower()
    if stem not in ("readme", "index") and not VERSION.match(stem):
        result.insert(0, stem)
    return list(dict.fromkeys(result))


def sentence(text, title, limit=DESCRIPTION):
    """The first sentence that says something of its own: not the regime line of a design file, and
    led by the title when it is one that many files share."""
    text = re.sub(r"\*\*|__", "", " ".join(text.split()))
    sentences = [s for s in SENTENCE.split(text) if s and not s.startswith("Regime:")]
    first = sentences[0] if sentences else title
    if first.startswith(GENERIC):
        first = f"{title}: {first[0].lower()}{first[1:]}"
    return first if len(first) <= limit else first[:limit - 1].rstrip() + "…"


def derive(text, rel):
    """The frontmatter of a file that has none, from its content and its place."""
    lines = text.split("\n")
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), Path(rel).stem)
    quote, paragraph, seen_title = [], [], False
    for line in lines:
        if line.startswith("# "):
            seen_title = True
            continue
        if not seen_title:
            continue
        if line.startswith(">"):
            quote.append(line.lstrip("> ").strip())
        elif quote:
            break
        elif line.strip() and not line.startswith(("#", "|", "```", "-", "*")) and not paragraph:
            paragraph.append(line.strip())
        elif paragraph and line.strip() and not line.startswith(("#", "|", "```")):
            paragraph.append(line.strip())
        elif paragraph:
            break
    meta = {"type": okf_type(rel), "title": title,
            "description": sentence(" ".join(quote or paragraph), title), "tags": tags(rel)}
    if meta["type"] == "Index":
        meta["okf_version"] = OKF_VERSION
    return meta


def frontmatter(meta):
    return "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in meta.items() if v not in (None, [])) + "---\n"


def write(root, out=sys.stdout):
    written = 0
    for path in sorted((root / BUNDLE).rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        if split(text)[0] is not None:
            continue
        rel = path.relative_to(root).as_posix()
        meta = derive(text, rel)
        path.write_text(frontmatter(meta) + "\n" + text, encoding="utf-8")
        out.write(f"{rel}: {meta['type']}: {meta['description']}\n")
        written += 1
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description="knowledge/ as an Open Knowledge Format bundle.")
    parser.add_argument("--write", action="store_true", help="give a frontmatter to the files that have none")
    parser.add_argument("--root", default=".", help="the repository (default: the current directory)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not (root / BUNDLE).is_dir():
        print(f"no {BUNDLE}/: nothing to check")
        return 0
    if args.write:
        write(root)
    errors = check(root)
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("okf check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
