"""Tests of scripts/check_attribution.py (python -m unittest discover -s scripts/tests)."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import check_attribution  # noqa: E402
import strip_pr_attribution  # noqa: E402

SCRIPT = pathlib.Path(check_attribution.__file__)


class TestOffending(unittest.TestCase):

    def test_the_lines_that_name_an_assistant_as_author(self):
        for line in ("Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
                     "co-authored-by: GitHub Copilot <copilot@github.com>",
                     "Co-authored-by: gemini-code-assist[bot] <bot@users.noreply.github.com>",
                     "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
                     "Claude-Session: https://claude.ai/code/session_123"):
            self.assertEqual(len(check_attribution.offending(f"fix: a thing\n\n{line}\n")), 1, line)

    def test_a_person_as_co_author_and_ordinary_text_are_clean(self):
        message = ("feat(memory): the reranker reads the chatter\n\n"
                   "The cards of the list scenario are measured as before.\n"
                   "Co-authored-by: Paola Rossi <paola@example.org>\n")
        self.assertEqual(check_attribution.offending(message), [])

    def test_the_comments_of_the_commit_template_are_skipped(self):
        self.assertEqual(check_attribution.offending("fix: x\n# Co-Authored-By: Claude is refused by the hook\n"), [])


class TestCommandLine(unittest.TestCase):

    def run_script(self, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              env={**os.environ, **(env or {})}, check=False)

    def test_a_message_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
            handle.write("fix: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
        self.addCleanup(os.unlink, handle.name)
        done = self.run_script("--message", handle.name)
        self.assertEqual(done.returncode, 1)
        self.assertIn("co-author trailer of an assistant", done.stderr)

    def test_a_pull_request_description(self):
        self.assertEqual(self.run_script("--env", "PR_BODY", env={"PR_BODY": "## What\n\nA fix."}).returncode, 0)
        self.assertEqual(self.run_script("--env", "PR_BODY", env={
            "PR_BODY": "A fix.\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"}).returncode, 1)

    def test_a_range_of_commits(self):
        log = "abc1234\x00fix: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n\x01def5678\x00fix: y\n\x01"
        with mock.patch.object(check_attribution.subprocess, "run",
                               return_value=mock.Mock(stdout=log)) as run:
            self.assertEqual(check_attribution.main(["--range", "origin/main..HEAD"]), 1)
        self.assertEqual(run.call_args.args[0][-1], "origin/main..HEAD")


class TestStripPullRequest(unittest.TestCase):

    def test_only_the_lines_of_the_assistant_go(self):
        body = ("## What\n\nA fix, reviewed with Paola.\n\n"
                "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n")
        self.assertEqual(strip_pr_attribution.cleaned(body), "## What\n\nA fix, reviewed with Paola.\n")
        self.assertEqual(strip_pr_attribution.cleaned("## What\n\nA fix.\n"), "## What\n\nA fix.\n")


if __name__ == "__main__":
    unittest.main()
