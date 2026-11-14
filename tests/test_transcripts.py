import json
import tempfile
import unittest
from pathlib import Path

from texo import transcripts


def lines(*entries):
    return "".join(json.dumps(entry) + "\n" for entry in entries)


def by_message(role, content, **more):
    return {"type": role, "message": {"content": content}, **more}


def step(index, kind, source="MODEL", **more):
    return {"step_index": index, "type": kind, "source": source, "status": "DONE", **more}


def shape(events):
    return [(e["kind"], e["phase"], e["target"], e["ok"]) for e in events]


class TestTranscripts(unittest.TestCase):

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "transcript.jsonl"

    def test_messages_made_of_blocks(self):
        self.path.write_text(lines(
            by_message("user", "the orders are not confirmed"),
            by_message("user", "<notice>not the person</notice>"),
            by_message("user", "from another agent", origin={"kind": "agent"}),
            by_message("assistant", [
                {"type": "tool_use", "id": "a", "name": "Edit", "input": {"file_path": "/w/mail.py"}},
                {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "make test"}},
                {"type": "tool_use", "id": "c", "name": "mcp__memoria__task", "input": {"task_id": 7}},
                {"type": "tool_use", "id": "d", "name": "Read", "input": {"file_path": "/w/x"}}]),
            by_message("user", [
                {"type": "tool_result", "tool_use_id": "b", "is_error": True, "content": [{"type": "text", "text": "1 failed"}]},
                {"type": "tool_result", "tool_use_id": "a", "content": "done"},
                {"type": "tool_result", "tool_use_id": "unknown", "is_error": True, "content": "lost"}]),
        ))
        adapter = transcripts.Adapter()
        events = adapter.read(self.path)
        self.assertEqual(shape(events), [
            ("request", None, None, None),
            ("edit", "call", "/w/mail.py", None), ("command", "call", "make test", None),
            ("memory", "call", "task", None), ("other", "call", None, None),
            ("command", "result", "make test", False), ("edit", "result", "/w/mail.py", True),
            ("other", "result", None, False)])
        self.assertEqual(events[3]["args"], {"task_id": 7})
        self.assertEqual(events[5]["text"], "1 failed")
        self.assertEqual(sorted(adapter.pending), ["c", "d"], "the calls without a result wait")

    def test_steps(self):
        self.path.write_text(lines(
            step(0, "USER_INPUT", source="USER", content="the orders are not confirmed"),
            step(1, "PLANNER_RESPONSE", tool_calls=[
                {"name": "write_to_file", "args": {"TargetFile": "/w/a.py"}},
                {"name": "edit_file", "args": json.dumps({"Path": "/w/b.py"})},
                {"name": "run_command", "args": {"CommandLine": "make test"}},
                {"name": "run_command", "args": {"CommandLine": "ls"}},
                {"name": "call_mcp_tool", "args": {"ServerName": "memoria", "ToolName": "task_note",
                                                  "Arguments": {"task_id": 7, "confirm": True}}},
                {"name": "call_mcp_tool", "args": {"ServerName": "other", "ToolName": "task"}}]),
            step(2, "CODE_ACTION"), step(3, "CODE_ACTION", status="ERROR"),
            step(4, "RUN_COMMAND", exit_code=2, content="boom"),
            step(5, "GENERIC", content="a.py b.py"),
            step(6, "SYSTEM_MESSAGE", source="SYSTEM", content="not a result"),
            step(7, "GENERIC"), step(8, "GENERIC"),
            step(9, "GENERIC", content="no call waits for this"),
            step(10, "PLANNER_RESPONSE", tool_calls=[{"name": "run_command", "args": {"CommandLine": "pytest"}}]),
            step(11, "GENERIC", content="Traceback (most recent call last)\n  ..."),
        ))
        events = transcripts.Adapter().read(self.path)
        self.assertEqual(shape(events), [
            ("request", None, None, None),
            ("edit", "call", "/w/a.py", None), ("edit", "call", "/w/b.py", None),
            ("command", "call", "make test", None), ("command", "call", "ls", None),
            ("memory", "call", "task_note", None), ("other", "call", None, None),
            ("edit", "result", "/w/a.py", True), ("edit", "result", "/w/b.py", False),
            ("command", "result", "make test", False),
            ("command", "result", "ls", None),
            ("memory", "result", "task_note", True), ("other", "result", None, True),
            ("command", "call", "pytest", None), ("command", "result", "pytest", False)],
            "the results follow the calls of the step, in their order; a command that does not say how it ended "
            "is unknown, unless its text reads as a failure")
        self.assertEqual(events[5]["args"], {"task_id": 7, "confirm": True})

    def test_a_read_goes_on_where_the_last_one_stopped(self):
        whole = lines(by_message("user", "one"),
                      by_message("assistant", [{"type": "tool_use", "id": "a", "name": "Bash",
                                                "input": {"command": "make test --password hunter2hunter2"}}]))
        result = lines(by_message("user", [{"type": "tool_result", "tool_use_id": "a", "is_error": True, "content": "no"}]))
        half = len(result) // 2
        self.path.write_text(whole + result[:half])
        adapter = transcripts.Adapter(keep=lambda text: text.replace("hunter2hunter2", "[kept out]"))
        self.assertEqual(shape(adapter.read(self.path)),
                         [("request", None, None, None), ("command", "call", "make test --password hunter2hunter2", None)],
                         "a line still being written waits")
        self.assertEqual(adapter.offset, len(whole.encode()))
        state = json.loads(json.dumps(adapter.state()))
        self.assertNotIn("hunter2", json.dumps(state), "the state is a file: it keeps what the caller lets it keep")
        self.assertEqual(transcripts.Adapter(state).read(self.path), [], "nothing new, nothing read again")
        with open(self.path, "a") as handle:
            handle.write(result[half:])
        again = transcripts.Adapter(state)
        self.assertEqual(shape(again.read(self.path)), [("command", "result", "make test --password [kept out]", False)],
                         "the result finds its call in the state of the read before")
        self.assertFalse(again.restarted)

    def test_a_file_written_again_is_read_from_its_beginning(self):
        self.path.write_text(lines(by_message("user", "one"), by_message("user", "two"), by_message("user", "three")))
        adapter = transcripts.Adapter()
        adapter.read(self.path)
        self.path.write_text(lines(by_message("user", "after the compaction")))
        again = transcripts.Adapter(adapter.state())
        self.assertEqual([e["text"] for e in again.read(self.path)], ["after the compaction"])
        self.assertTrue(again.restarted)

    def test_what_is_not_a_message_or_a_step_is_skipped(self):
        self.path.write_text('not json\n[1, 2]\n"text"\n42\nnull\n{"type": "summary"}\n'
                             + lines({"type": "user", "message": "not an object"},
                                     by_message("assistant", "a text, not blocks"),
                                     by_message("assistant", [7, {"type": "tool_use", "name": "Bash", "input": "x"}]),
                                     by_message("user", [None, {"type": "tool_result"}]),
                                     step(1, "PLANNER_RESPONSE", tool_calls=[None, {"name": None, "args": "{"}]),
                                     by_message("user", "still read")))
        events = transcripts.Adapter().read(self.path)
        self.assertEqual(events[-1]["text"], "still read")
        self.assertEqual(transcripts.Adapter().read(self.path.with_name("missing.jsonl")), [])
        self.assertEqual(transcripts.Adapter({"offset": "x", "pending": [], "last_calls": {}}).state(),
                         {"offset": 0, "pending": {}, "last_calls": []}, "a state that is not one is no state")
