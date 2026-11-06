import io
import json
import tempfile
import unittest
from pathlib import Path

from texo import hooks


def transcript(path, *entries):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("not json\n")
        for role, content in entries:
            handle.write(json.dumps({"type": role, "message": {"content": content}}) + "\n")


class TestHooks(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "acme"
        self.root.mkdir()
        (self.root / "texo.toml").write_text('[texo]\norganisation = "acme"\nhub_url = "http://hub.test"\n')
        self.path = self.tmp / "session.jsonl"

    def run_hook(self, event, session="abcdef1234", **extra):
        out = io.StringIO()
        payload = {"session_id": session, "transcript_path": str(self.path), "cwd": str(self.root), **extra}
        code = hooks.run(event, stdin=io.StringIO(json.dumps(payload)), out=out, root=self.root, today="2026-11-06")
        return code, out.getvalue()

    def session_with_work(self):
        transcript(
            self.path,
            ("user", "il cliente non riceve più le conferme degli ordini, password=hunter2 nel log"),
            ("assistant", [{"type": "tool_use", "name": "mcp__memoria__context", "input": {"task_id": 22}},
                           {"type": "tool_use", "name": "Edit",
                            "input": {"file_path": str(self.root / "progetti/x/mail.py"), "old_string": "a"}}]),
            ("user", [{"type": "tool_result", "is_error": True, "content": "Traceback: SMTP disabled"}]),
            ("assistant", [{"type": "tool_use", "name": "Bash",
                            "input": {"command": "texo task 22 && git commit -m 'fix(mail): outgoing server'"}}]),
            ("assistant", [{"type": "text", "text": "fatto"}]),
        )

    def test_the_proposal_holds_the_material_of_the_session_without_secrets(self):
        self.session_with_work()
        code, out = self.run_hook("precompact")
        self.assertEqual((code, out), (0, ""), "before a compaction: the proposal, no request")
        proposal = (self.root / ".texo" / "proposals" / "2026-11-06-abcdef12.md").read_text(encoding="utf-8")
        self.assertIn("tasks: [22]", proposal)
        self.assertIn("- il cliente non riceve più le conferme degli ordini, password=[REDACTED] nel log", proposal)
        self.assertIn("- progetti/x/mail.py", proposal)
        self.assertIn("- fix(mail): outgoing server", proposal)
        self.assertIn("- Traceback: SMTP disabled", proposal)
        self.assertNotIn("hunter2", proposal)

    def test_the_end_of_a_turn_asks_once_for_the_note(self):
        self.session_with_work()
        code, out = self.run_hook("stop")
        self.assertEqual(code, 0)
        decision = json.loads(out)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("task 22", decision["reason"])
        self.assertIn(".texo/proposals/2026-11-06-abcdef12.md", decision["reason"])
        self.assertEqual(self.run_hook("stop")[1], "", "asked once per session")
        self.assertEqual(self.run_hook("stop", stop_hook_active=True)[1], "", "never while the agent answers a hook")
        self.assertEqual(self.run_hook("session-end")[1], "", "the end of the session writes, never asks")

    def test_a_note_written_drops_the_proposal(self):
        self.session_with_work()
        self.run_hook("stop")
        proposals = self.root / ".texo" / "proposals"
        self.assertEqual(sorted(p.name for p in proposals.iterdir()),
                         ["2026-11-06-abcdef12.asked", "2026-11-06-abcdef12.md"])
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "mcp__memoria__task_note",
                 "input": {"task_id": 22, "body": "...", "confirm": True}}]}}) + "\n")
        self.assertEqual(self.run_hook("stop"), (0, ""))
        self.assertEqual(list(proposals.iterdir()), [])
        # the command line form counts as well
        transcript(self.path, ("assistant", [{"type": "tool_use", "name": "Bash",
                                              "input": {"command": "texo task-note 22 'x' --keywords a --yes"}}]))
        self.assertTrue(hooks.extract(hooks.read_transcript(self.path))["note_written"])

    def test_only_what_the_person_wrote_is_a_request(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            for text, origin in (("fammi il report", "human"), ("<system-reminder>x</system-reminder>", "human"),
                                 ("Another Claude session sent a message: ...", "human"), ("da un agente", "agent")):
                entry = {"type": "user", "message": {"content": text}, "origin": {"kind": origin}}
                handle.write(json.dumps(entry) + "\n")
            handle.write(json.dumps({"type": "user", "message": {"content": "senza origine"}}) + "\n")
        found = hooks.extract(hooks.read_transcript(self.path))
        self.assertEqual(found["requests"], ["fammi il report", "senza origine"])

    def test_nothing_to_propose_nothing_written(self):
        transcript(self.path, ("user", "che ore sono?"), ("assistant", [{"type": "text", "text": "le dieci"}]))
        self.assertEqual(self.run_hook("stop"), (0, ""))
        self.assertFalse((self.root / ".texo" / "proposals").exists())
        self.assertEqual(hooks.run("stop", stdin=io.StringIO("{"), out=io.StringIO(), root=self.root), 0)
        self.assertEqual(hooks.run("stop", stdin=io.StringIO("{}"), out=io.StringIO(), root=self.root), 0)

    def test_redaction(self):
        self.assertEqual(hooks.redact("TEXO_HUB_TOKEN=abc123 and sk-ABCDEFGHIJKLMNOP and AKIAABCDEFGHIJKLMNOP"),
                         "TEXO_HUB_TOKEN=[REDACTED] and [REDACTED] and [REDACTED]")
        self.assertEqual(hooks.redact("the token is in ~/.config/texo/acme.env"),
                         "the token is in ~/.config/texo/acme.env", "a word is not a value")
        self.assertEqual(hooks.redact("Authorization: Bearer abc.def"), "Authorization: Bearer [REDACTED]")
        self.assertEqual(hooks.redact("nothing to hide here"), "nothing to hide here")


if __name__ == "__main__":
    unittest.main()
