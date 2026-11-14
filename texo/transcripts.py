"""The transcript of a session as one stream of events, whichever assistant wrote it, read a piece at a time.

Two formats are known. In the first, each line is a message of the person or of the assistant, made of blocks:
a call of a tool is a block of the assistant, its result a block of the next message of the person, tied to the
call by an id. In the second, each line is a step: a step of the planner carries the calls, the steps after it
carry their results, in the order of the calls.

An event is a dict {kind, phase, tool, target, args, ok, text}:
  kind    request | edit | command | memory | other
  phase   call (the assistant asked for it) or result (how it ended); a request has neither
  tool    the name the assistant gives the tool
  target  the path of an edit, the command line of a command, the name of a tool of the memory
  args    for a tool of the memory, its arguments; empty otherwise
  ok      on a result: True, False, or None when the transcript does not say how the call ended
  text    the words of a request, or the beginning of the result of a call that failed

What an event carries is as the transcript has it: whoever keeps or shows it redacts it first (hooks.redact).
The names of the tools are tables here: a new assistant, or a new generation of names, is a line in a table.
"""
import json
import os
import re

# first format: the tools that change a file and the argument that names it; the tool that runs a command
EDITS_BY_MESSAGE = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path",
                    "NotebookEdit": "notebook_path"}
COMMANDS_BY_MESSAGE = {"Bash": "command"}
# second format: two generations of names for the same tools
EDITS_BY_STEP = {"edit_file": "Path", "write_file": "Path", "replace_file_content": "TargetFile",
                 "write_to_file": "TargetFile"}
COMMANDS_BY_STEP = {"run_command": "CommandLine"}
MCP_BY_STEP = "call_mcp_tool"
MEMORY_SERVER = "memoria"
# a text of the person that is not theirs: a notice, a message of another agent, a system turn
NOT_A_REQUEST = ("<", "[Subagent hand-back]", "Another Claude session sent a message")
# the result of a command in the second format often says nothing but its text
FAILURE_TEXT = re.compile(r"Traceback \(most recent call last\)|^\w*(?:Error|Exception): |\bFAILED\b|\bFAIL:|"
                          r"\d+ failed|command not found|No such file or directory", re.M)
MAX_TEXT = 4000
MAX_PENDING = 200


def text_of(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return " ".join(block.get("text") or "" for block in content if isinstance(block, dict))


def event(kind, phase=None, tool=None, target=None, args=None, ok=None, text=None):
    return {"kind": kind, "phase": phase, "tool": tool, "target": target, "args": args or {}, "ok": ok,
            "text": text}


def as_dict(value):
    """The arguments of a call: an object, or the JSON text of one."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


class Adapter:
    """The events of a transcript, from where the last read stopped. Its state (the offset in the file and the
    calls still waiting for their result) is JSON: a read can stop anywhere and the next one, in another
    process, goes on from there."""

    def __init__(self, state=None, keep=None):
        """keep: what makes a text fit to be kept in the state, a file (the redaction of the caller)."""
        state = state if isinstance(state, dict) else {}
        self.keep = keep or (lambda text: text)
        self.offset = state.get("offset") if isinstance(state.get("offset"), int) else 0
        pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
        last_calls = state.get("last_calls") if isinstance(state.get("last_calls"), list) else []
        self.pending = {key: call for key, call in pending.items() if self.is_call(call)}
        self.last_calls = [call for call in last_calls if self.is_call(call)]
        self.restarted = False

    @staticmethod
    def is_call(call):
        return isinstance(call, list) and len(call) == 3

    def state(self):
        """Where the read stopped, to give to the next Adapter. Of a call that waits for its result it keeps the
        beginning of the target, made fit to be kept."""
        return {"offset": self.offset,
                "pending": {key: [kind, tool, self.kept(target)] for key, (kind, tool, target) in self.pending.items()},
                "last_calls": [[kind, tool, self.kept(target)] for kind, tool, target in self.last_calls]}

    def read(self, path):
        """The events of what the file gained since the last read. Only whole lines are taken: a line the
        assistant is still writing waits for the next read. A file shorter than where the last read stopped was
        written again: the read starts from its beginning and `restarted` says so."""
        self.restarted = False
        events = []
        try:
            if os.path.getsize(path) < self.offset:
                self.offset, self.pending, self.last_calls, self.restarted = 0, {}, [], True
            with open(path, "rb") as handle:
                handle.seek(self.offset)
                data = handle.read()
        except OSError:
            return events
        end = data.rfind(b"\n") + 1
        for raw in data[:end].splitlines():
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            if isinstance(entry, dict):
                events.extend(self.entry(entry))
        self.offset += end
        return events

    def entry(self, entry):
        if "step_index" in entry:
            return self.step(entry)
        if entry.get("type") in ("user", "assistant") and isinstance(entry.get("message"), dict):
            return self.message(entry)
        return []

    # -- first format: messages made of blocks ---------------------------------------------------------------
    def message(self, entry):
        events, content = [], entry["message"].get("content")
        if entry["type"] == "user":
            origin = entry.get("origin")
            if (origin.get("kind") if isinstance(origin, dict) else None) not in (None, "human"):
                return events  # a message another agent or the assistant put in the turn of the person
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
            for block in blocks if isinstance(blocks, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = (block.get("text") or "").lstrip()
                    if text and not text.startswith(NOT_A_REQUEST):
                        events.append(event("request", text=text[:MAX_TEXT]))
                elif block.get("type") == "tool_result":
                    call = self.pending.pop(str(block.get("tool_use_id")), None) or ["other", None, None]
                    failed = bool(block.get("is_error"))
                    events.append(event(call[0], "result", call[1], call[2], ok=not failed,
                                        text=text_of(block.get("content"))[:MAX_TEXT] if failed else None))
            return events
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name, args = block.get("name") or "", as_dict(block.get("input"))
            if name in EDITS_BY_MESSAGE:
                call = event("edit", "call", name, args.get(EDITS_BY_MESSAGE[name]))
            elif name in COMMANDS_BY_MESSAGE:
                call = event("command", "call", name, args.get(COMMANDS_BY_MESSAGE[name]))
            elif name.startswith(f"mcp__{MEMORY_SERVER}__"):
                call = event("memory", "call", name, name.rsplit("__", 1)[-1], args)
            else:
                call = event("other", "call", name)
            events.append(call)
            if block.get("id") and len(self.pending) < MAX_PENDING:
                self.pending[str(block["id"])] = [call["kind"], name, call["target"]]
        return events

    # -- second format: steps ---------------------------------------------------------------------------------
    def step(self, entry):
        kind = entry.get("type")
        if kind == "USER_INPUT":
            text = text_of(entry.get("content")).lstrip()
            return [event("request", text=text[:MAX_TEXT])] if text else []
        if kind == "PLANNER_RESPONSE":
            events, self.last_calls = [], []
            calls = entry.get("tool_calls")
            for call in calls if isinstance(calls, list) else []:
                if not isinstance(call, dict):
                    continue
                name, args = call.get("name") or "", as_dict(call.get("args"))
                if name in EDITS_BY_STEP:
                    made = event("edit", "call", name, args.get(EDITS_BY_STEP[name]))
                elif name in COMMANDS_BY_STEP:
                    made = event("command", "call", name, args.get(COMMANDS_BY_STEP[name]))
                elif name == MCP_BY_STEP and args.get("ServerName") == MEMORY_SERVER:
                    made = event("memory", "call", name, args.get("ToolName"), as_dict(args.get("Arguments")))
                else:
                    made = event("other", "call", name)
                events.append(made)
                self.last_calls.append([made["kind"], name, made["target"]])
            return events
        if not self.last_calls or entry.get("source") != "MODEL":
            return []
        call = self.last_calls.pop(0)
        content = text_of(entry.get("content"))
        if "exit_code" in entry:
            ok = entry["exit_code"] == 0
        elif entry.get("status") == "ERROR" or entry.get("error"):
            ok = False
        elif call[0] == "command":
            # the transcript does not say how the command ended: only a text that reads as a failure does
            ok = False if FAILURE_TEXT.search(content) else None
        else:
            ok = True
        return [event(call[0], "result", call[1], call[2], ok=ok, text=content[:MAX_TEXT] if ok is False else None)]

    def kept(self, target):
        return self.keep(target[:MAX_TEXT])[:400] if isinstance(target, str) else None
