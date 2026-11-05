#!/usr/bin/env python3
"""strip_pr_attribution.py — remove from the descriptions of past pull requests the lines that name an AI
assistant as author (the lines scripts/check_attribution.py finds), keeping the rest of the text.

    python3 scripts/strip_pr_attribution.py <owner/repo> [<owner/repo> ...] [--apply] [--backup <dir>]

Without --apply it only lists the pull requests it would change. With --apply each original description is saved
in the backup directory (default: a new temporary one) before `gh pr edit` writes the new one.
Needs gh, logged in with write access to the repositories.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_attribution  # noqa: E402


def cleaned(body: str) -> str:
    bad = {int(error.split(":")[0].split()[1]) for error in check_attribution.offending(body)}
    return "\n".join(line for number, line in enumerate(body.splitlines(), 1) if number not in bad).rstrip() + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("repos", nargs="+")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup")
    args = parser.parse_args(argv)
    backup = pathlib.Path(args.backup or tempfile.mkdtemp(prefix="pr-bodies-"))
    for repo in args.repos:
        prs = json.loads(subprocess.run(
            ["gh", "pr", "list", "-R", repo, "--state", "all", "--limit", "500", "--json", "number,body"],
            capture_output=True, text=True, check=True).stdout)
        todo = [pr for pr in prs if check_attribution.offending(pr["body"] or "")]
        numbers = ", ".join(f"#{pr['number']}" for pr in todo)
        print(f"{repo}: {len(todo)} pull requests to clean: {numbers}")
        if not args.apply:
            continue
        backup.mkdir(parents=True, exist_ok=True)
        for pr in todo:
            (backup / f"{repo.replace('/', '_')}-{pr['number']}.md").write_text(pr["body"], encoding="utf-8")
            subprocess.run(["gh", "pr", "edit", str(pr["number"]), "-R", repo, "--body", cleaned(pr["body"])],
                           capture_output=True, check=True)
        print(f"   cleaned; the original descriptions are in {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
