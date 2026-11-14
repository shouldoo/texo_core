import io
import json
import os
import subprocess
import sys
import tempfile
import time
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

    def test_each_event_reads_only_what_the_transcript_gained(self):
        self.session_with_work()
        self.run_hook("precompact")
        kept = self.root / ".texo" / "hooks" / "abcdef1234.json"
        state = json.loads(kept.read_text())
        self.assertEqual(state["transcript"]["offset"], self.path.stat().st_size)
        self.assertEqual(state["found"]["tasks"], [22])
        self.assertNotIn("hunter2", kept.read_text(), "the state holds no secret either")
        self.assertEqual([p.name for p in kept.parent.iterdir()], [kept.name], "no temporary file is left")
        # the first lines change under the hook: it does not read them again
        text = self.path.read_text().replace("texo task 22", "texo task 99")
        self.path.write_text(text + json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": str(self.root / "progetti/x/new.py")}}]}}) + "\n")
        self.run_hook("precompact")
        proposal = (self.root / ".texo" / "proposals" / "2026-11-06-abcdef12.md").read_text()
        self.assertIn("tasks: [22]", proposal)
        self.assertIn("- progetti/x/mail.py", proposal, "what was found before stays")
        self.assertIn("- progetti/x/new.py", proposal)
        # a transcript written again, shorter (a compaction): from its beginning, what was found forgotten
        transcript(self.path, ("assistant", [{"type": "tool_use", "name": "mcp__memoria__task", "input": {"task_id": 5}}]))
        self.run_hook("precompact")
        self.assertEqual(json.loads(kept.read_text())["found"]["tasks"], [5])
        # a state that cannot be read is no state; the end of the session takes the state away
        kept.write_text("{")
        self.run_hook("precompact")
        self.assertEqual(json.loads(kept.read_text())["found"]["tasks"], [5])
        old = kept.with_name("long-ago.json")
        old.write_text("{}")
        os.utime(old, (time.time() - 40 * 86400,) * 2)
        self.run_hook("precompact", session="another/../session")
        self.assertEqual(sorted(p.name for p in kept.parent.iterdir()), ["abcdef1234.json", "another_.._session.json"],
                         "a new session takes away the states of those that ended long ago")
        self.run_hook("session-end")
        self.assertFalse(kept.exists())

    def test_the_other_format_and_the_other_names_of_the_fields(self):
        steps = [
            {"step_index": 0, "source": "USER", "type": "USER_INPUT", "content": "il report non parte"},
            {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "tool_calls": [
                {"name": "call_mcp_tool", "args": {"ServerName": "memoria", "ToolName": "context",
                                                  "Arguments": {"task_id": 31}}},
                {"name": "replace_file_content", "args": {"TargetFile": str(self.root / "progetti/y/report.py")}},
                {"name": "run_command", "args": {"CommandLine": "git commit -m 'fix(report): the date'"}}]},
            {"step_index": 2, "source": "MODEL", "type": "GENERIC"},
            {"step_index": 3, "source": "MODEL", "type": "CODE_ACTION"},
            {"step_index": 4, "source": "MODEL", "type": "RUN_COMMAND", "exit_code": 1, "content": "nothing to commit"},
        ]
        self.path.write_text("".join(json.dumps(s) + "\n" for s in steps))
        out = io.StringIO()
        payload = {"hookEventName": "Stop", "conversationId": "0123456789", "transcriptPath": str(self.path),
                   "cwd": str(self.root)}
        self.assertEqual(hooks.run("stop", stdin=io.StringIO(json.dumps(payload)), out=out, root=self.root,
                                   today="2026-11-06"), 0)
        proposal = (self.root / ".texo" / "proposals" / "2026-11-06-01234567.md").read_text()
        for expected in ("tasks: [31]", "- il report non parte", "- progetti/y/report.py", "- fix(report): the date",
                         "- nothing to commit"):
            self.assertIn(expected, proposal)
        self.assertEqual(out.getvalue(), "", "an assistant whose hook is not known to take the request is not asked")

    def test_the_command_of_the_hook_does_not_load_the_client_of_the_hub(self):
        self.session_with_work()
        payload = json.dumps({"session_id": "abcdef1234", "transcript_path": str(self.path), "cwd": str(self.root)})
        core = Path(__file__).resolve().parent.parent
        for arguments in (["--root", str(self.root), "hook", "stop"], [f"--root={self.root}", "hook", "stop"],
                          ["hook", "stop"]):
            done = subprocess.run([sys.executable, "-X", "importtime", "-m", "texo", *arguments], input=payload,
                                  capture_output=True, text=True, cwd=core, check=False)
            self.assertEqual(done.returncode, 0, done.stderr[-500:])
            self.assertNotIn("urllib.request", done.stderr)
            self.assertNotIn("texo.cli", done.stderr)
        self.assertTrue(list((self.root / ".texo" / "proposals").glob("*.md")))
        done = subprocess.run([sys.executable, "-m", "texo", "hook", "unknown"], input="{}", capture_output=True,
                              text=True, cwd=core, check=False)
        self.assertEqual(done.returncode, 2, "an event that is not one is still refused by the CLI")

    def test_redaction(self):
        # the fixtures are built at run time: a secret scanner must not read them in this file
        fixtures = "TEXO_HUB_TOKEN=abc123 and " + "sk-" + "ABCDEFGHIJKLMNOP" + " and " + "AKIA" + "ABCDEFGHIJKLMNOP"
        self.assertEqual(hooks.redact(fixtures), "TEXO_HUB_TOKEN=[REDACTED] and [REDACTED] and [REDACTED]")
        self.assertEqual(hooks.redact("the token is in ~/.config/texo/acme.env"),
                         "the token is in ~/.config/texo/acme.env", "a word is not a value")
        self.assertEqual(hooks.redact("Authorization: Bearer abc.def"), "Authorization: Bearer [REDACTED]")
        self.assertEqual(hooks.redact("nothing to hide here"), "nothing to hide here")

    def test_redaction_of_a_corpus_made_here(self):
        # every value is made at each run: a file under version control holds nothing that looks like a secret
        import base64
        import secrets
        word = lambda n: "".join(secrets.choice("abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(n))  # noqa: E731
        pem_body = "\n".join(base64.b64encode(secrets.token_bytes(48)).decode() for _ in range(6))
        # the armour is put together here, so that the scan of the repository for secrets finds no key in this file
        dashes, label = "-" * 5, "RSA PRIVATE" + " KEY"
        pem = f"{dashes}BEGIN {label}{dashes}\n{pem_body}\n{dashes}END {label}{dashes}"
        hub_key = secrets.token_hex(20) + "_oak"
        cases = {
            "an assignment": ("password = {}", word(16)), "a bearer": ("Authorization: Bearer {}", word(40)),
            "a prefixed key": ("{}", "ghp_" + word(36)), "a gitlab token": ("{}", "glpat-" + word(20)),
            "a url": ("postgres://odoo:{}@db:5432/x", word(14)), "an option": ("odoo-bin --db_password {} -d x", word(12)),
            "a json key": ('{{"access_token": "{}"}}', word(40)), "a header": ("X-Api-Key: {}", word(32)),
            "an environment variable": ("PGPASSWORD={} psql -h db", word(12)),
            "a key of the hub": ("{}", hub_key), "a key of the hub as an option": ("texo init --token {}", hub_key),
            "a long hexadecimal": ("{}", secrets.token_hex(32)),
        }
        for name, (template, value) in cases.items():
            self.assertNotIn(value, hooks.redact(template.format(value)), name)
        for name, text in (("a private key", pem), ("a private key in an error", "cannot load the key " + pem + " at line 3")):
            done = hooks.clean(text, 200)
            self.assertIn("[REDACTED]", done, name)
            self.assertFalse(any(line in done for line in pem_body.splitlines()), name)
        self.assertNotIn(pem_body[:40], hooks.redact(pem[:150]), "a private key already cut loses what is left of it")
        for text in ("commit " + secrets.token_hex(20), secrets.token_hex(16), "il token di accesso va rinnovato",
                     "the url is https://hub.example/texo/mcp", "pass the option --yes to mount"):
            self.assertEqual(hooks.redact(text), text, "not a secret")


if __name__ == "__main__":
    unittest.main()
