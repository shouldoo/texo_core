#!/usr/bin/env python3
"""check_attribution.py — no AI assistant named as author in a commit message or a pull request description.

Every Texo repository: the assistant or its maker are never named as author in a commit, and no Co-Authored-By
names an assistant. Assistants add such lines on their own (a co-author trailer, a «Generated
with» footer, a session link); this check stops them wherever they would land.

    python3 scripts/check_attribution.py --message <file>      # the commit-msg hook (setup/git-hooks/commit-msg)
    python3 scripts/check_attribution.py --range <base>..<head> # the commits of a pull request or a push (CI)
    python3 scripts/check_attribution.py --env PR_BODY          # the description of a pull request (CI)

Exit 1 with the offending lines, 0 when clean. Standard library only.
"""
import argparse
import os
import re
import subprocess
import sys

ASSISTANTS = r"(claude|anthropic|copilot|gemini|openai|chatgpt|gpt-\d|codex|cursor|devin|aider|antigravity)"
FORBIDDEN = [
    (re.compile(rf"^\s*co-authored-by:.*{ASSISTANTS}", re.IGNORECASE), "co-author trailer of an assistant"),
    (re.compile(r"generated (with|by) \[?(claude|copilot|gemini|cursor|codex)", re.IGNORECASE),
     "«generated with» footer of an assistant"),
    (re.compile(r"^\s*claude-session:", re.IGNORECASE), "session link of an assistant"),
    (re.compile(r"noreply@anthropic\.com|claude\.ai/code/session", re.IGNORECASE), "address of an assistant"),
]


def offending(text: str) -> list[str]:
    """The lines of the text that name an assistant as author, each with the reason."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue  # a comment of the commit template (git strips it), e.g. the help of the hook itself
        for pattern, reason in FORBIDDEN:
            if pattern.search(line):
                found.append(f"line {number}: {reason}: {line.strip()}")
                break
    return found


def commits(revision_range: str) -> list[tuple[str, str]]:
    """(short hash, message) of the commits in the range, merges included."""
    out = subprocess.run(["git", "log", "--format=%h%x00%B%x01", revision_range],
                         capture_output=True, text=True, check=True).stdout
    return [tuple(chunk.strip("\n").split("\x00", 1)) for chunk in out.split("\x01") if chunk.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", help="a commit message file (the commit-msg hook)")
    group.add_argument("--range", help="a git revision range, e.g. origin/main..HEAD")
    group.add_argument("--env", help="the name of an environment variable holding a text (a PR description)")
    args = parser.parse_args(argv)
    errors = []
    if args.message:
        with open(args.message, encoding="utf-8") as handle:
            errors = [f"commit message, {line}" for line in offending(handle.read())]
    elif args.range:
        for short, message in commits(args.range):
            errors += [f"commit {short}, {line}" for line in offending(message)]
    else:
        errors = [f"{args.env}, {line}" for line in offending(os.environ.get(args.env, ""))]
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print("An assistant is never named as author of a commit or a pull request: remove these lines.",
              file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
