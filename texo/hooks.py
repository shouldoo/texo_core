"""texo hook <event>: the proposal of the session note, from the hooks of an assistant.

An assistant that supports hooks calls `texo hook stop` at the end of each of its turns, `texo hook precompact`
before it compacts the conversation and `texo hook session-end` when the session closes, with the JSON the
assistant gives on stdin (the id of the session and the path of its transcript, at least). The hook reads the
transcript and leaves in `.texo/proposals/` the material of the session note the skill texo-sessione asks for
at the end of the work: the tasks the session worked on, what the person asked in their own words, the files
changed, the commits, the errors met; secrets are redacted before anything is written. Once per session, at the
end of a turn that worked on a task without writing its note, the hook asks the agent to propose the note to
the person; nothing is written in the hub by the hook, ever: the agent proposes, the person says yes.

The transcript is read through texo.transcripts, which knows the formats of the assistants, and a piece at a
time: next to the proposals the hook keeps, for each session, where it stopped reading and what it found
(`.texo/hooks/<session>.json`), so that each event reads only what the transcript gained since the last one.

The command never fails the assistant: outside a working folder, without a transcript, on any error it says
nothing and exits 0.
"""
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

from . import transcripts
from .config import find_root

EVENTS = ("stop", "precompact", "session-end")
PROPOSALS = ".texo/proposals"
STATES = ".texo/hooks"
STATE_DAYS = 30
# the names an assistant gives, in the JSON of its hook, to what the hook reads: the transcript, the session,
# and the turn that goes on because a hook asked it to
TRANSCRIPT_FIELDS = ("transcript_path", "transcriptPath")
SESSION_FIELDS = ("session_id", "conversationId")
CONTINUING_FIELDS = ("stop_hook_active", "continuationActive")
# the tools of the memory that name a task, by the name the hub gives them
TASK_TOOLS = ("task", "context", "task_note", "log_time")
NOTE_TOOLS = ("task_note",)
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


def short(text, limit=MAX_CHARS):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def clean(text, limit=MAX_CHARS):
    """A text of the transcript as the proposal keeps it: redacted whole, then on one line and cut. In this
    order: cut first, a secret on several lines would lose the marks that make it recognisable."""
    return short(redact(text or ""), limit)


def read_transcript(path):
    """The events of a whole transcript (texo.transcripts says what an event is)."""
    return transcripts.Adapter(keep=redact).read(path)


def nothing_found():
    return {"tasks": [], "requests": [], "files": [], "commits": [], "errors": [], "note_written": False}


def task_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract(events, root=None, found=None):
    """What the session note is made of: {tasks, requests, files, commits, errors, note_written}. With found,
    what the events add to what was found before them."""
    found = found if found is not None else nothing_found()

    def add(key, value):
        if value and value not in found[key] and len(found[key]) < MAX_ITEMS:
            found[key].append(value)

    for event in events:
        kind, phase, target = event["kind"], event["phase"], event["target"]
        if kind == "request":
            if len(found["requests"]) < MAX_REQUESTS:
                found["requests"].append(clean(event["text"]))
        elif phase == "result":
            if event["ok"] is False:
                add("errors", clean(event["text"], 200))
        elif kind == "memory":
            if target in TASK_TOOLS:
                add("tasks", task_id(event["args"].get("task_id")))
            if target in NOTE_TOOLS and event["args"].get("confirm") is True:
                found["note_written"] = True
        elif kind == "edit" and target:
            path = str(target)
            if root and path.startswith(str(root)):
                path = str(Path(path).relative_to(root))
            add("files", redact(path))
        elif kind == "command" and isinstance(target, str):
            for match in TASK_IN_COMMAND.finditer(target):
                add("tasks", int(match.group(1) or match.group(2)))
            if NOTE_IN_COMMAND.search(target):
                found["note_written"] = True
            for match in COMMIT_MESSAGE.finditer(target):
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


def state_path(root, session_id):
    return Path(root) / STATES / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', session_id)[:80] or 'session'}.json"


def load_state(path):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found = state.get("found") if isinstance(state, dict) else None
    if not isinstance(found, dict) or set(found) != set(nothing_found()):
        return {}
    return state


def save_state(path, state):
    """Written whole or not at all: to a file of this process, then renamed over the state."""
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
    if new:  # a session begins: the states of the sessions that ended long ago go
        limit = time.time() - STATE_DAYS * 86400
        for old in path.parent.iterdir():
            try:
                if old != path and old.stat().st_mtime < limit:
                    old.unlink()
            except OSError:
                pass


def first(payload, names):
    return next((payload[name] for name in names if payload.get(name)), None)


def run(event, stdin=sys.stdin, out=sys.stdout, root=None, today=None):
    """One event of an assistant: read its JSON, read what the transcript gained, write or drop the proposal,
    and at the end of a turn ask the agent, once per session, to propose the note. Always exits 0 and says
    nothing unless it asks."""
    try:
        payload = json.loads(stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    root = Path(root) if root else find_root(Path(payload.get("cwd") or Path.cwd()))
    transcript = first(payload, TRANSCRIPT_FIELDS)
    session_id = str(first(payload, SESSION_FIELDS) or "")
    if not root or not isinstance(transcript, str):
        return 0
    kept = state_path(root, session_id)
    state = load_state(kept)
    adapter = transcripts.Adapter(state.get("transcript"), keep=redact)
    before = adapter.offset
    events = adapter.read(transcript)
    found = extract(events, root, None if adapter.restarted else state.get("found"))
    if event == "session-end":
        if kept.exists():
            kept.unlink()
    elif adapter.offset != before or adapter.restarted:
        save_state(kept, {"transcript": adapter.state(), "found": found})
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
    if events or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(proposal_text(session_id, found, today), encoding="utf-8")
    # only the assistant whose hook is known to take the request below is asked: for another, the proposal
    # waits in its folder, where the rules of the folder say to look
    if event != "stop" or "transcript_path" not in payload or first(payload, CONTINUING_FIELDS) or asked.exists():
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
