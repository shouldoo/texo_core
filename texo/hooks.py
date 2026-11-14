"""texo hook <event>: the proposal of the session note, from the hooks of an assistant.

An assistant that supports hooks calls `texo hook stop` at the end of each of its turns, `texo hook precompact`
before it compacts the conversation and `texo hook session-end` when the session closes, with the JSON the
assistant gives on stdin (the id of the session and the path of its transcript, at least). The hook reads the
transcript and leaves in `.texo/proposals/` the material of the session note the skill texo-sessione asks for
at the end of the work: the tasks the session worked on, what the person asked in their own words, the files
changed, the commits, the errors met; secrets are redacted before anything is written. Once per session, at the
end of a turn that worked on a task without writing its note, the hook asks the agent to propose the note to
the person; nothing is written in the hub by the hook, ever: the agent proposes, the person says yes.

The command never fails the assistant: outside a working folder, without a transcript, on any error it says
nothing and exits 0.
"""
import datetime
import json
import re
import sys
from pathlib import Path

from .config import find_root

EVENTS = ("stop", "precompact", "session-end")
PROPOSALS = ".texo/proposals"
# the tools of the memory that name a task, by the name an assistant gives them (mcp__memoria__task, task)
TASK_TOOLS = ("task", "context", "task_note", "log_time")
NOTE_TOOLS = ("task_note",)
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
MAX_REQUESTS = 6
MAX_CHARS = 400
MAX_ITEMS = 12
TASK_IN_COMMAND = re.compile(r"\btexo\s+(?:task|task-note|log-time)\s+(\d+)|\btexo\s+context\s+--task\s+(\d+)")
NOTE_IN_COMMAND = re.compile(r"\btexo\s+task-note\s+\d+.*--yes")
COMMIT_MESSAGE = re.compile(r"git\s+commit\b[^\n]*?-m\s+(?:\"([^\"]+)\"|'([^']+)')")
SECRET_NAME = r"\w*(?:api[_-]?key|token|secret|password|passwd)\w*"
REDACTIONS = (
    # a private key, from its header to its footer or to the end of the text: before anything cuts the text
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), "[REDACTED]"),
    # user:password@ in a URL
    (re.compile(r"\b([a-z][a-z0-9+.\-]*://[^\s/:@]+):[^\s/@]+@"), r"\1:[REDACTED]@"),
    # a named value: NAME=value, name: value, "name": "value"
    (re.compile(rf"(?i)({SECRET_NAME}[\"']?)(\s*[:=]\s*)([\"']?)[^\s\"',}}]+"), r"\1\2\3[REDACTED]"),
    # an option and its value: --db_password value
    (re.compile(rf"(?i)(--?{SECRET_NAME})(\s+)(?!-)\S+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)\b(bearer)\s+(\S+)"), r"\1 [REDACTED]"),
    (re.compile(r"\b(sk|ghp|gho|ghs|ghu|ghr|github_pat|glpat|xox[abprs])[-_][A-Za-z0-9_\-]{12,}"), "[REDACTED]"),
    # an API key of the hub (Odoo): forty hexadecimal digits and the suffix of its keys
    (re.compile(r"\b[0-9a-f]{40}_oak\b"), "[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "[REDACTED]"),
    (re.compile(r"\b[0-9a-f]{48,}\b"), "[REDACTED]"),
)


def redact(text):
    """The text without what looks like a credential: a key, a token, a password named or recognisable."""
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


NOT_A_REQUEST = ("<", "[Subagent hand-back]", "Another Claude session sent a message")


def is_request(text):
    """A text the person wrote, not a notice, a message of another agent or a system turn."""
    text = (text or "").lstrip()
    return bool(text) and not any(text.startswith(mark) for mark in NOT_A_REQUEST)


def short(text, limit=MAX_CHARS):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def clean(text, limit=MAX_CHARS):
    """A text of the transcript as the proposal keeps it: redacted whole, then on one line and cut. In this
    order: cut first, a secret on several lines would lose the marks that make it recognisable."""
    return short(redact(text or ""), limit)


def tool_name(name):
    """The name of a tool of the memory as the hub names it: the MCP prefix of the assistant dropped."""
    return (name or "").rsplit("__", 1)[-1]


def read_transcript(path):
    """The messages of a transcript (one JSON object per line, the format of the assistants that keep one):
    [(role, content)] with content a string or a list of blocks; a line that is not JSON is skipped."""
    messages = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") in ("user", "assistant") and isinstance(entry.get("message"), dict):
                    origin = (entry.get("origin") or {}).get("kind")
                    if entry["type"] == "user" and origin not in (None, "human"):
                        continue  # a message another agent or the assistant put in the turn of the person
                    messages.append((entry["type"], entry["message"].get("content")))
    except OSError:
        return []
    return messages


def extract(messages, root=None):
    """What the session note is made of: {tasks, requests, files, commits, errors, note_written}."""
    found = {"tasks": [], "requests": [], "files": [], "commits": [], "errors": [], "note_written": False}

    def add(key, value):
        if value and value not in found[key] and len(found[key]) < MAX_ITEMS:
            found[key].append(value)

    for role, content in messages:
        if role == "user":
            if isinstance(content, str):
                if is_request(content) and len(found["requests"]) < MAX_REQUESTS:
                    found["requests"].append(clean(content))
                continue
            for block in content or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and is_request(block.get("text")) \
                        and len(found["requests"]) < MAX_REQUESTS:
                    found["requests"].append(clean(block.get("text")))
                elif block.get("type") == "tool_result" and block.get("is_error"):
                    inner = block.get("content")
                    text = inner if isinstance(inner, str) else " ".join(
                        b.get("text", "") for b in inner or [] if isinstance(b, dict))
                    add("errors", clean(text, 200))
            continue
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name, arguments = tool_name(block.get("name")), block.get("input") or {}
            if name in TASK_TOOLS and arguments.get("task_id"):
                add("tasks", int(arguments["task_id"]))
            if name in NOTE_TOOLS and arguments.get("confirm") is True:
                found["note_written"] = True
            if block.get("name") in EDIT_TOOLS and arguments.get("file_path"):
                path = arguments["file_path"]
                if root and str(path).startswith(str(root)):
                    path = str(Path(path).relative_to(root))
                add("files", redact(str(path)))
            if block.get("name") == "Bash" and isinstance(arguments.get("command"), str):
                command = arguments["command"]
                for match in TASK_IN_COMMAND.finditer(command):
                    add("tasks", int(match.group(1) or match.group(2)))
                if NOTE_IN_COMMAND.search(command):
                    found["note_written"] = True
                for match in COMMIT_MESSAGE.finditer(command):
                    add("commits", clean(match.group(1) or match.group(2), 120))
    return found


def proposal_text(session_id, found, today):
    """The proposal as a Markdown file: what the hook found, then the four parts of the note to fill."""
    lines = ["---", f"session: {session_id}", f"written: {today}",
             f"tasks: [{', '.join(str(t) for t in found['tasks'])}]", "---", "",
             "# Proposta di nota di task", "",
             "Materiale raccolto dalla trascrizione della sessione dall'hook (`texo hook`), con i segreti oscurati. "
             "La nota si propone alla persona e si scrive solo dopo il suo sì "
             "(`texo task-note <id> \"<testo>\" --keywords ... --yes`); poi questo file si cancella.", ""]

    def section(title, items, empty):
        lines.append(f"## {title}")
        lines.append("")
        if items:
            lines.extend(f"- {redact(item) if isinstance(item, str) else item}" for item in items)
        else:
            lines.append(empty)
        lines.append("")

    section("Task toccati", found["tasks"], "- nessun task riconosciuto: chiedere alla persona quale")
    section("Richieste della persona", found["requests"], "- nessuna")
    section("File toccati", found["files"], "- nessuno")
    section("Commit", found["commits"], "- nessuno")
    section("Errori incontrati", found["errors"], "- nessuno")
    lines += ["## La nota, da scrivere", "",
              "- **Sintomo o richiesta**, con le parole di chi l'ha sollevata:", "- **Causa o contesto**:",
              "- **Che cosa si è fatto o deciso**, e lo stato:",
              "- **Parole chiave** (5-10: sinonimi, il termine locale e quello inglese, la sigla e la sua "
              "espansione):", ""]
    return "\n".join(lines)


def proposal_path(root, session_id, today):
    name = f"{today}-{(session_id or 'session')[:8]}"
    return Path(root) / PROPOSALS / f"{name}.md"


def run(event, stdin=sys.stdin, out=sys.stdout, root=None, today=None):
    """One event of an assistant: read its JSON, read the transcript, write or drop the proposal, and at the end
    of a turn ask the agent, once per session, to propose the note. Always exits 0 and says nothing unless it
    asks."""
    try:
        payload = json.loads(stdin.read() or "{}")
    except ValueError:
        return 0
    root = Path(root) if root else find_root(Path(payload.get("cwd") or Path.cwd()))
    if not root or not isinstance(payload, dict):
        return 0
    transcript = payload.get("transcript_path")
    session_id = payload.get("session_id") or ""
    if not transcript:
        return 0
    found = extract(read_transcript(transcript), root)
    today = today or datetime.date.today().isoformat()
    path = proposal_path(root, session_id, today)
    asked = path.with_suffix(".asked")
    if found["note_written"]:
        # the note is in the hub: the proposal did its work
        for stale in (path, asked):
            if stale.exists():
                stale.unlink()
        return 0
    if not (found["tasks"] or found["files"]):
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(proposal_text(session_id, found, today), encoding="utf-8")
    if event != "stop" or payload.get("stop_hook_active") or asked.exists():
        return 0
    asked.write_text(today + "\n", encoding="utf-8")
    worked = (f"ha lavorato sul task {', '.join(str(t) for t in found['tasks'])}" if found["tasks"]
              else "ha cambiato dei file senza un task riconosciuto (chiedi alla persona quale)")
    relative = path.relative_to(root)
    out.write(json.dumps({"decision": "block", "reason": (
        f"Prima di chiudere il turno: la sessione {worked} e la nota di task non è stata "
        f"scritta. Proponi alla persona la nota (skill texo-sessione, § 5) partendo da {relative}, che l'hook ha "
        "preparato con il materiale della sessione; scrivila solo dopo il suo sì, poi cancella il file. Se la "
        "persona non la vuole, prosegui.")}, ensure_ascii=False) + "\n")
    return 0
