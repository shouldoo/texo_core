#!/usr/bin/env python3
"""The client of the hub (the coordination Odoo with texo_hub): the agent's memory, as the person.

One client, two faces, standard library only:
- a command line any assistant with a shell can run (`texo <command>`: text output, --json for the raw answer);
- a local MCP server over stdio (`texo mcp`, the server memoria) for the assistants that load MCP tools.

The memory comes back named as Open Knowledge Format (OKF v0.2, docs/memoria.md): every record a
concept (rules/12, facts/3, projects/2), the pack an index.md, the updates and the chatter a log.md;
--okf on the command line, format okf from MCP. A write says which agent made it (generated_by): the
client of the MCP session (its clientInfo), or --generated-by on the command line.

Every call carries the person's own token (API key with the Texo scope) and runs in Odoo as that
person: roles, access rules and audit are Odoo's. Writes need --yes on the command line and confirm: true
from MCP, after the person agreed in the session. The hub and its token come from the fabric (texo/config.py):
the token is never printed and never passed as an argument.
"""
import argparse
import base64
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

from . import __version__

TIMEOUT = 60
WRITE_TOOLS = ("task_note", "note", "note_append", "note_update", "fact", "fact_append", "fact_update", "lesson", "update", "state", "log_time",
               "confirm", "document_write", "document_remove", "document_convert",
               "sources_collect", "sources_search", "sources_link", "sources_propose", "sources_triage", "sources_card",
               "sources_channel")
SCOPES = ("all", "rules", "notes", "facts", "procedures", "lessons", "documents", "tasks", "sources")
# the mode of a search where the hub has texo_vector: the words, the vectors, or both fused
MODES = ("lexical", "semantic", "hybrid")
KINDS = ("rule", "fact", "procedure")
STATES = ("active", "superseded", "archived")
UPDATE_STATUSES = ("on_track", "at_risk", "off_track", "on_hold", "done")
SEVERITIES = ("never", "must", "prefer")
FORMATS = ("json", "okf")


class HubError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Hub:
    def __init__(self, url, token, opener=None):
        self.url = url.rstrip("/")
        self.token = token
        self.opener = opener or urllib.request.urlopen
        # the agent that writes through this client, as <producer>/<version> (OKF generated.by)
        self.generated_by = None
        # the threads of the fabric, as texo mount left them (.texo/threads.json)
        self.threads = []

    def call(self, route, payload=None):
        """POST a json2 route as the person; the answer or a HubError with Odoo's message."""
        request = urllib.request.Request(
            f"{self.url}/texo/v1/{route}", method="POST",
            data=json.dumps(payload or {}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"})
        try:
            with self.opener(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode() or "null")
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")
            error.close()
            try:
                message = json.loads(body).get("message") or body
            except ValueError:
                message = body
            if error.code == 401:
                message = "the token is invalid or expired: create a new one in Odoo (Preferences, Security, New API Key, scope Texo)"
            raise HubError(error.code, (message or "").strip()[:500]) from None
        except urllib.error.URLError as error:
            raise HubError(0, f"Odoo not reachable at {self.url}: {error.reason}") from None


# -- operations: one function per route, shared by the CLI and the MCP server ----------

def _format(payload, args):
    """format okf asks the hub for the files of an OKF bundle instead of its JSON."""
    if args.get("format"):
        payload["format"] = args["format"]
    return payload


def _generated_by(payload, hub, args):
    """Who writes: the agent the call names, else the client of the session."""
    who = args.get("generated_by") or getattr(hub, "generated_by", None)
    if who:
        payload["generated_by"] = who
    return payload


def op_whoami(hub, _):
    return hub.call("whoami")


def op_rules(hub, args):
    """The rules of the session; with an activity, only the rules of the organisation that concern it."""
    return hub.call("memory/rules", {"activity": args["activity"]} if (args or {}).get("activity") else {})


def op_my_work(hub, args):
    return hub.call("project/my_work", {"limit": args.get("limit") or 50})


def op_task(hub, args):
    return hub.call("project/task", _format({"task_id": args["task_id"], "messages": args.get("messages") or 10}, args))


def op_task_note(hub, args):
    """What happened on a task, what was decided and why: an internal note in its chatter, written to be found
    later; its keywords are merged into the search keywords of the task."""
    payload = {"task_id": args["task_id"], "body": args["body"]}
    if args.get("keywords"):
        payload["keywords"] = args["keywords"]
    return hub.call("project/task_note", payload)


def op_context(hub, args):
    """The pack of a task or a project; of neither, the pack of the organisation itself (the company, by section).
    With the activity of the session, only the rules that concern it."""
    payload = {"messages": args.get("messages") or 5}
    if args.get("task_id"):
        payload["task_id"] = args["task_id"]
    elif args.get("project_id"):
        payload["project_id"] = args["project_id"]
    elif args.get("company_id"):
        payload["company_id"] = args["company_id"]
    if args.get("activity"):
        payload["activity"] = args["activity"]
    if args.get("max_tokens"):
        payload["max_tokens"] = args["max_tokens"]
    return hub.call("memory/context", _format(payload, args))


def op_search(hub, args):
    payload = {"query": args["query"], "related_terms": args.get("related_terms") or [],
               "scope": args.get("scope") or "all", "applies_to": args.get("applies_to"),
               "limit": args.get("limit") or 5}
    # only when asked: a hub without texo_vector answers lexically and the configured mode holds
    if args.get("mode"):
        payload["mode"] = args["mode"]
    if args.get("show_expired"):
        payload["show_expired"] = True
    if args.get("as_of"):
        payload["as_of"] = args["as_of"]
    if args.get("max_tokens"):
        payload["max_tokens"] = args["max_tokens"]
    return hub.call("memory/search", payload)


def op_read(hub, args):
    """One rule, fact or lesson; or any concept by its OKF id (rules/12, facts/3, documents/9, tasks/7)."""
    payload = _format({"max_chars": args.get("max_chars") or 6000}, args)
    for key in ("concept", "lesson_id", "fact_id", "note_id"):
        if args.get(key):
            # a fact is a note: its id is a note id
            payload["note_id" if key == "fact_id" else key] = args[key]
            return hub.call("memory/read", payload)
    raise HubError(0, "give a note, a fact, a lesson or a concept")


def op_note(hub, args):
    """A note on a task (not a rule), a project, a customer or, with none, the organisation (the company): a rule
    (the default), a fact or a procedure."""
    payload = {key: args.get(key) for key in (
        "name", "body", "kind", "section", "task_id", "project_id", "partner_id", "company_id", "state", "expires",
        "valid_from", "source_ref", "document_id", "severity", "activities", "keywords", "applies_to")
        if args.get(key) is not None}
    if payload.get("kind", "rule") == "rule":
        payload.setdefault("state", "draft")
    return hub.call("memory/note", _generated_by(payload, hub, args))


def op_note_append(hub, args):
    """A dated, signed paragraph at the end of a fact or a procedure."""
    payload = {"note_id": args.get("note_id") or args.get("fact_id")}
    payload.update({key: args[key] for key in ("text", "keywords") if args.get(key) is not None})
    return hub.call("memory/note_append", payload)


def op_note_update(hub, args):
    """Replace the text of a note (with the version read), its title, section, keywords or dates, or mark it verified."""
    payload = {"note_id": args.get("note_id") or args.get("fact_id")}
    payload.update({key: args[key] for key in (
        "expected_version", "body", "name", "section", "keywords", "applies_to", "expires", "valid_from", "verified")
        if args.get(key) not in (None, False)})
    return hub.call("memory/note_update", payload)


def op_fact(hub, args):
    """A fact: a note of kind fact, on a task, a project, a customer or, with none, the organisation."""
    return op_note(hub, dict(args, kind="fact"))


def op_fact_append(hub, args):
    return op_note_append(hub, args)


def op_fact_update(hub, args):
    return op_note_update(hub, args)


def op_lesson(hub, args):
    """A finding without the customer: a technical fact learned on a project."""
    payload = {key: args.get(key) for key in (
        "finding", "solution", "tags", "title", "applies_to", "verified", "state", "source_ref", "activities",
        "keywords")
        if args.get(key) is not None}
    payload.setdefault("state", "draft")
    return hub.call("memory/lesson", _generated_by(payload, hub, args))


def op_project(hub, args):
    return hub.call("project/project", _format({"project_id": args["project_id"]}, args))


def op_log(hub, args):
    """The history of a project (updates, milestones reached) or of a task (its chatter), as an OKF log.md."""
    payload = {key: args[key] for key in ("project_id", "task_id", "limit") if args.get(key)}
    return hub.call("project/log", payload)


def op_update(hub, args):
    """A project update: the new present of the project."""
    payload = {key: args.get(key) for key in ("project_id", "name", "status", "description", "progress")
               if args.get(key) is not None}
    return hub.call("project/update", payload)


def op_state(hub, args):
    payload = {"state": args["state"]}
    for key in ("note_id", "lesson_id", "fact_id", "superseded_by_id"):
        if args.get(key):
            payload[key] = args[key]
    return hub.call("memory/state", payload)


def op_log_time(hub, args):
    payload = {"task_id": args["task_id"], "hours": args["hours"], "description": args["description"]}
    if args.get("date"):
        payload["date"] = args["date"]
    return hub.call("project/log_time", payload)


def op_review(hub, _):
    return hub.call("memory/review")


def op_confirm(hub, args):
    payload = {"note_id": args["note_id"]}
    if args.get("expires"):
        payload["expires"] = args["expires"]
    return hub.call("memory/confirm", payload)


def op_documents(hub, args):
    payload = {}
    for key in ("task_id", "project_id", "partner_id", "company_id"):
        if args.get(key):
            payload[key] = args[key]
    return hub.call("document/list", payload)


def op_document(hub, args):
    return hub.call("document/read", _format({"document_id": args["document_id"], "text": bool(args.get("text")),
                                              "max_chars": args.get("max_chars") or 6000, "offset": args.get("offset") or 0}, args))


def op_document_write(hub, args):
    payload = {key: args.get(key) for key in (
        "name", "url", "data", "summary", "task_id", "project_id", "partner_id", "company_id", "read_on", "fingerprint",
        "text", "document_id", "keywords") if args.get(key) is not None}
    payload["keep_text"] = not args.get("no_text", False) if "keep_text" not in args else bool(args["keep_text"])
    return hub.call("document/write", payload)


def op_document_remove(hub, args):
    return hub.call("document/remove", {"document_id": args["document_id"]})


def op_document_convert(hub, args):
    """The file of an attachment converted by the service of the hub, when an administrator named one."""
    return hub.call("document/convert", {"document_id": args["document_id"]})


def op_document_attachment(hub, args):
    """The file of an attachment the person may read, saved in a folder (never printed):
    the answer carries where it is, its name, type, size and fingerprint."""
    result = hub.call("document/attachment", {"attachment_id": args["attachment_id"]})
    out_dir = args.get("out") or tempfile.mkdtemp(prefix="attachment-")
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.basename(result.get("name") or "") or f"attachment-{result['id']}"
    path = os.path.join(out_dir, name)
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(result.pop("data")))
    result["path"] = path
    return result


def op_ask(hub, args):
    from .grounder import ground_query
    prompt = args.get("prompt") or args.get("query") or args.get("ask")
    if not prompt:
        raise ValueError("Missing prompt for ask")
    grounded = ground_query(prompt, limit=args.get("limit") or 20)
    result = hub.call("search_read", grounded)
    result["grounded"] = {"model": grounded["model"], "domain": grounded["domain"], "fields": grounded["fields"]}
    return result


def op_query(hub, args):
    if args.get("ask") or not args.get("model"):
        return op_ask(hub, args)
    payload = {"model": args["model"], "domain": args.get("domain") or [], "fields": args.get("fields") or [],
               "limit": args.get("limit") or 20}
    return hub.call("search_read", payload)


def _payload(args, keys):
    """The arguments given, among keys, for a route."""
    return {key: args[key] for key in keys if args.get(key) not in (None, "", [])}


# -- the external sources (texo_sources, optional): the triage of Odoo, in the session ---------------

def op_sources_due(hub, args):
    return hub.call("sources/due", _payload(args, ("project_id",)))


def op_sources_find(hub, args):
    return hub.call("sources/find", _payload(args, ("query", "persons", "themes", "channel", "date_from", "date_to",
                                                    "states", "limit")))


def op_sources_inbox(hub, args):
    return hub.call("sources/inbox", _payload(args, ("watched_only", "limit")))


def op_sources_collect(hub, args):
    payload = _payload(args, ("channel_ids",))
    if args.get("overdue_only") is not None:
        payload["overdue_only"] = bool(args["overdue_only"])
    return hub.call("sources/collect", payload)


def op_sources_search(hub, args):
    return hub.call("sources/search", _payload(args, ("query", "channel_ids", "limit", "since")))


def op_sources_link(hub, args):
    return hub.call("sources/link", _payload(args, ("url", "title")))


def op_sources_propose(hub, args):
    payload = _payload(args, ("item_id", "action", "themes", "card", "doubts", "questions"))
    return hub.call("sources/propose", _generated_by(payload, hub, args))


def op_sources_triage(hub, args):
    return hub.call("sources/triage", _payload(args, ("item_ids", "decision", "themes", "note")))


def op_sources_card(hub, args):
    payload = _payload(args, ("item_id", "abstract", "quotes", "persons", "bodies", "places", "themes", "acts",
                              "event_date", "stance", "relevance", "keywords", "related_ids"))
    if args.get("submit") is not None:
        payload["submit"] = bool(args["submit"])
    return hub.call("sources/card", payload)


def op_sources_channel(hub, args):
    payload = _payload(args, ("name", "website", "kind", "look_for", "every_days", "project_id", "feeds"))
    if isinstance(payload.get("feeds"), str):
        payload["feeds"] = json.loads(payload["feeds"])
    return hub.call("sources/channel", payload)


def op_threads(hub, _):
    """The threads of the fabric: no call to the hub."""
    keys = ("id", "type", "driver", "data_class", "writes", "guide", "status", "message", "ref", "url", "command")
    return {"threads": [{k: t[k] for k in keys if t.get(k) is not None} for t in hub.threads]}


OPERATIONS = {
    "threads": op_threads,
    "whoami": op_whoami, "rules": op_rules, "my_work": op_my_work, "task": op_task, "task_note": op_task_note,
    "context": op_context,
    "search": op_search, "read": op_read, "note": op_note, "note_append": op_note_append, "note_update": op_note_update,
    "fact": op_fact, "fact_append": op_fact_append,
    "fact_update": op_fact_update, "lesson": op_lesson, "project": op_project, "log": op_log,
    "update": op_update, "state": op_state, "log_time": op_log_time,
    "review": op_review, "confirm": op_confirm, "documents": op_documents, "document": op_document,
    "document_write": op_document_write, "document_remove": op_document_remove, "document_attachment": op_document_attachment,
    "document_convert": op_document_convert,
    "query": op_query,
    "ask": op_ask,
    "sources_due": op_sources_due, "sources_find": op_sources_find, "sources_inbox": op_sources_inbox,
    "sources_collect": op_sources_collect, "sources_search": op_sources_search, "sources_link": op_sources_link,
    "sources_propose": op_sources_propose, "sources_triage": op_sources_triage, "sources_card": op_sources_card,
    "sources_channel": op_sources_channel,
}


# -- text rendering for the command line ------------------------------------------------

def _document_line(document):
    """A document as one line: what it is, where its original is, what it holds."""
    where = document.get("url") or document.get("mimetype") or "-"
    record = document.get("record") or {}
    return (f"{document['id']}  {document['title']}  ({document['type']}: {where}; on {record.get('model')} {record.get('id')})"
            f"{'  text' if document.get('has_text') else ''}{'  changed ' + document['changed_on'] if document.get('changed_on') else ''}")


def _document_tag(document):
    return f"{document['id']} {document['title']}" + (" (changed)" if document.get("changed_on") else "")


def _warning(warning):
    if warning.get("project_id"):
        return f"project {warning['project_id']} {warning['warning']}"
    if warning.get("warning"):
        return f"{warning['warning']} ({warning.get('count')})"
    return f"{warning['id']} {warning['title']} ({warning['stale']})"


def render_okf(data):
    """An OKF answer as text: each file after a comment with its path, as the MCP server of the hub gives it."""
    return "\n".join(f"<!-- okf: {f['path']} -->\n{f['text']}" for f in data["files"])


def render(name, data):
    if isinstance(data, dict) and data.get("format") == "okf":
        return render_okf(data)
    if isinstance(data, dict) and data.get("existing"):
        # an idempotent write (note, fact, lesson, task-note): the hub gave the record back, nothing was written
        return "already in the memory, nothing written:\n" + render(name, {k: v for k, v in data.items() if k != "existing"})
    if name == "whoami":
        return f"{data['name']} ({data['login']}), role {data['role']}"
    if name == "threads":
        return "\n".join(f"{t['id']} [{t['type']}, {t['data_class']}, writes {t.get('writes', 'never')}]"
                         f"{' ' + t['status'] if t.get('status') not in (None, 'ok') else ''}: {t.get('guide', '')}"
                         for t in data["threads"]) or "no thread mounted (texo mount)"
    if name == "rules":
        own = len(data.get("company_rules") or [])
        return f"role: {data['role']} ({own} rules of the organisation)\n{data['rules']}"
    if name == "my_work":
        rows = [f"{t['id']}  {t['name']}  [{t.get('project') or '-'} / {t.get('customer') or '-'}]  {t.get('stage') or ''}"
                for t in data["tasks"]]
        return "\n".join(rows) or "no open tasks"
    if name == "search":
        rows = []
        for r in data["results"]:
            tag = ("lesson" if r.get("lesson") else "document" if r.get("document") else "task" if r.get("task")
                   else "card" if r.get("source") else r.get("kind") or "note")
            tag += f"/{r['state']}" if r.get("state") else ""
            # which search found it, where the hub has vectors: lexical, semantic, both
            found = f"  ({r['match']}{', ' + str(r['similarity']) if r.get('similarity') is not None else ''})" \
                if r.get("match") else ""
            # a document says which passage answered: its path, and where to read it (document --offset)
            passage = r.get("passage") or {}
            others = [p for p in r.get("passages") or [] if p.get("start") != passage.get("start")]
            where = (f"\n    {passage.get('path') or '(no heading)'}  (offset {passage.get('start')})"
                     + "".join(f"\n      also: {p.get('path') or '(no heading)'}  (offset {p.get('start')})"
                               for p in others)
                     if passage else "")
            # a card says where and when: its channel and the date of the event
            if r.get("source"):
                where = "\n    " + " · ".join(filter(None, [r.get("channel"), r.get("event_date"), r.get("url")]))
            if r.get("stale"):
                tag += f", {r['stale']}"
            rows.append(f"{r['id']}  [{tag}]  {r['title']}{found}{where}\n    {r.get('snippet') or ''}")
        # how the search ran (a hub from 20.0.1.1.0 of texo_memory says it): the mode used, the reranker, the time
        if data.get("mode"):
            rows.append(f"({data['mode']}, rerank {data.get('rerank', 'off')}, {data.get('latency_ms', '?')} ms"
                        + (f"; budget {data['budget']['tokens']}/{data['budget']['max_tokens']} tokens, "
                           f"{data['budget']['skipped']} skipped" if data.get("budget") else "") + ")")
        return "\n".join(rows) or "nothing found"
    if name in ("project", "update"):
        return "\n".join(_project_lines(data if name == "project" else {"now": data}))
    if name == "context":
        lines = [f"role: {data['role']}" + (f"  (rules of: {', '.join(data['activities'])})" if data.get("activities") else "")]
        if data.get("task"):
            task = data["task"]
            milestone = task.get("milestone")
            lines.append(f"task {task['id']}: {task['name']}"
                         + (f"  (milestone {milestone['name']}{', reached' if milestone['reached'] else ''})" if milestone else ""))
        if data.get("project"):
            lines += _project_lines(data["project"])
        for level in data["levels"]:
            head = f"{level['model']} {level['id']}: {level.get('name') or ''}"
            if level["model"] == "res.company":
                head += "  (the organisation)"
            if level.get("skipped"):
                lines.append(f"{head}  ({level['skipped']})")
                continue
            lines.append(head)
            for rule in level.get("rules", []):
                text = f": {rule['body']}" if rule.get("body") else "  (text: read --note)"
                lines.append(f"  - rule {rule['id']}{' [' + rule['severity'] + ']' if rule.get('severity') else ''}"
                             f" {rule['title']}{text}"
                             f"{'  (activities: ' + ', '.join(rule['activities']) + ')' if rule.get('activities') else ''}")
            for key in ("facts", "procedures"):
                if level.get(key):
                    lines.append(f"  {key}: " + ", ".join(
                        f"{f['id']} {f['title']}" + (f" [{f['section']}]" if f.get("section") else "")
                        + (f" ({f['stale']})" if f.get("stale") else "") for f in level[key]))
            if level.get("documents"):
                lines.append("  documents: " + ", ".join(_document_tag(d) for d in level["documents"]))
        if data.get("sections"):
            lines.append("sections: " + ", ".join(s["code"] for s in data["sections"]))
        if data["pending"]:
            lines.append("draft rules: " + ", ".join(f"{p['id']} {p['title']} ({p.get('author')})" for p in data["pending"]))
        if data.get("pending_lessons"):
            lines.append("draft lessons to review: " + ", ".join(f"{l['id']} {l['title']}" for l in data["pending_lessons"]))
        if data["warnings"]:
            lines.append("warnings: " + ", ".join(_warning(w) for w in data["warnings"]))
        if data.get("budget"):
            budget = data["budget"]
            lines.append(f"budget: {budget['tokens']}/{budget['max_tokens']} tokens; cut: "
                         + (", ".join(budget["trimmed"]) or "nothing"))
        if data["lessons"]:
            lines.append("lessons:")
            lines += [f"  - {l['id']} {l['title']}" + (f"  [{', '.join(l['tags'])}]" if l.get("tags") else "")
                      for l in data["lessons"]]
        sources = data.get("sources")
        if sources:
            lines.append(f"external sources: {sources['candidates']} candidates to sort ({sources['candidates_watched']} "
                         f"with watched words), {sources['to_write']} cards to write, {sources['to_approve']} to approve")
            lines += [f"  - overdue: {c['id']} {c['name']}" + (f" (look for: {c['look_for']})" if c.get("look_for") else "")
                      for c in sources["channels_due"]]
        return "\n".join(lines)
    if name == "review":
        lines = [f"role: {data['role']}"]
        for key, label in (("drafts", "draft rules to decide"), ("stale", "active rules to re-check")):
            if data[key]:
                lines.append(f"{label}:")
                lines += [f"  - {n['id']} {n['title']} ({n['anchor']['model']} {n['anchor']['id']}"
                          f"{', ' + n['stale'] if n.get('stale') else ''}): {n['body'][:100]}" for n in data[key]]
        if data.get("projects_without_now"):
            lines.append("projects without a recent update:")
            lines += [f"  - {p['project_id']} {p['name']} ({p['warning']}, last {p['last_update'] or 'never'})"
                      for p in data["projects_without_now"]]
        if data.get("draft_lessons"):
            lines.append("draft lessons: " + ", ".join(f"{l['id']} {l['title']}" for l in data["draft_lessons"]))
        if data.get("duplicates"):
            lines.append("near-duplicate lessons:")
            lines += [f"  - {d['lesson_id']} {d['title']} ~ {d['other_id']} {d['other_title']} ({d['ratio']}%)"
                      for d in data["duplicates"]]
        return "\n".join(lines) if len(lines) > 1 else lines[0] + "\nnothing to review"
    if name in ("read", "note", "note_append", "note_update", "fact", "fact_append", "fact_update") and "body" in data:
        head = f"{data.get('kind') or 'note'} {data['id']}: {data['title']}"
        for key in ("state", "severity", "section", "verified", "valid_from", "expires", "superseded_on", "stale", "version"):
            if data.get(key):
                head += f"  {key} {data[key]}"
        return head + "\n" + data["body"] + ("\n(cut: read with a larger --max-chars)" if data.get("truncated") else "")
    if name == "documents":
        return "\n".join(_document_line(d) for d in data["documents"]) or "no documents"
    if name == "document":
        lines = [_document_line(data)]
        for key in ("read_on", "fingerprint", "changed_on"):
            if data.get(key):
                lines.append(f"{key}: {data[key]}")
        lines.append(f"summary: {data.get('summary') or '-'}")
        if "text" in data:
            lines.append(f"--- text ({data.get('text_total')} chars"
                         f"{', next offset ' + str(data['text_next_offset']) if data.get('text_next_offset') else ''})")
            lines.append(data["text"])
        return "\n".join(lines)
    if name == "document_remove":
        return f"{data['id']} {data['title']}: out of the memory"
    if name == "document_convert":
        return f"{data['id']} {data['title']}: converted by {data.get('converter')}, {data.get('chars')} characters of text"
    if name == "document_attachment":
        return (f"saved {data['path']}  ({data['name']}, {data.get('mimetype') or '-'}, {data['size']} bytes, "
                f"sha256 {data['sha256']}{', record ' + data['record']['model'] + ' ' + str(data['record']['id']) if data.get('record') else ''})")
    if name in ("sources_find", "sources_inbox", "sources_search", "sources_triage"):
        if name == "sources_inbox":
            head = [f"{data['total']} candidates, {data['watched']} with watched words"]
            items = data["candidates"]
            to_write = data.get("to_write") or []
            if to_write or data.get("to_write_total"):
                lines = head + [_source_line(i) for i in items]
                lines.append(f"{data.get('to_write_total', len(to_write))} cards to write")
                for card in to_write:
                    line = _source_line(card) + ("\n    sent back" if card.get("sent_back") else "")
                    line += "".join(f"\n    note: {note}" for note in card.get("notes") or [])
                    lines.append(line)
                return "\n".join(lines)
        elif name == "sources_search":
            head = [f"{data['new']} new candidates" + (f"; not read: {', '.join(data['errors'])}" if data["errors"] else "")
                    + (f"; no search feed: {', '.join(data['without_search'])}" if data["without_search"] else "")]
            items = [dict(i, _known=True) for i in data["known"]] + data["found"]
        else:
            head, items = [], data
        return "\n".join(head + [_source_line(i) for i in items]) or "nothing found"
    return json.dumps(data, indent=2, ensure_ascii=False)


def _source_line(item):
    """A card or a candidate as one line, its proposal and doubts on the next."""
    date = item.get("event_date") or (item.get("published_on") or "")[:10]
    line = (f"{item['id']}  [{item['state']}{', known' if item.get('_known') else ''}]  {date}  {item['channel']}"
            f"{'  *' if item.get('watched') else ''}\n    {item['title']}\n    {item['url']}")
    proposal = item.get("proposal")
    if proposal:
        line += (f"\n    proposal: {proposal['action']}" + (f", themes {', '.join(proposal['themes'])}" if proposal['themes'] else "")
                 + (f", doubts {', '.join(proposal['doubts'])}" if proposal['doubts'] else ""))
    return line


def _project_lines(project):
    """The project as text: description, roadmap, present."""
    lines = []
    if project.get("id"):
        head = f"project {project['id']}: {project['name']}"
        if project.get("customer"):
            head += f"  [{project['customer']}]"
        lines.append(head)
        if project.get("description"):
            lines.append("  " + project["description"].replace("\n", "\n  "))
    if project.get("milestones"):
        lines.append("milestones:")
        for m in project["milestones"]:
            state = "reached " + (m.get("reached_date") or "") if m["reached"] else ("OVERDUE " if m.get("overdue") else "") + (m.get("deadline") or "no deadline")
            lines.append(f"  - {m['name']} ({state.strip()}; tasks {m['open_tasks']} open, {m['closed_tasks']} closed)")
    now = project.get("now")
    if now:
        lines.append(f"now: update {now['id']} {now['date']} {now['title']} [{now['status']}, {now['progress']}%] by {now['author']}")
        if now.get("description"):
            lines.append("  " + now["description"].replace("\n", "\n  "))
    elif "now" in project:
        lines.append("now: no update yet")
    if project.get("warnings"):
        lines.append("warnings: " + ", ".join(project["warnings"]))
    return lines


# -- MCP server over stdio ----------------------------------------------------------------

def tool_schemas():
    """The tools of the MCP server."""
    integer, string = {"type": "integer"}, {"type": "string"}
    confirm = {"type": "boolean", "description": "true only after the person agreed in the session"}
    okf = {"type": "string", "enum": list(FORMATS),
           "description": "okf: the files of an Open Knowledge Format bundle (markdown with YAML frontmatter)"}
    generated_by = {"type": "string", "description": "who you are, as <producer>/<version> (e.g. claude-code/2.1); "
                                                     "default: the client of this session"}
    section = {"type": "string", "description": "the section of the note: profile, operations, compliance, sector, offer "
                                                "or another of the organisation's (the pack of the organisation lists them)"}
    strings = {"type": "array", "items": string}
    tools = [
        {"name": "threads", "description": "The threads of this fabric: the sources, tools and connectors mounted next to the memory, each with its data_class (what it may receive), writes and guide (when to use it and its limits). Never send a thread data of a class above its own.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "whoami", "description": "Who I am in the coordination Odoo and my hub role (member, lead, admin). Call it first.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "rules", "description": "The rules of the session (the common ones, then the active rules of the organisation, each with its severity), with my role and the activities of the organisation. They are already in the instructions of this server: call it again only after a rule changed. With activity, only the rules of the organisation that concern it.",
         "inputSchema": {"type": "object", "properties": {"activity": string}}},
        {"name": "my_work", "description": "My open tasks.",
         "inputSchema": {"type": "object", "properties": {"limit": integer}}},
        {"name": "task", "description": "One task: summary, description, subtasks, latest messages, worklog. With format okf, the task as an OKF concept (tasks/<id>.md) and its chatter as its log.",
         "inputSchema": {"type": "object", "properties": {"task_id": integer, "messages": integer, "format": okf}, "required": ["task_id"]}},
        {"name": "task_note", "description": "After the person's yes: an internal note in the chatter of a task (plain text), written to be found later: the symptom or request in the words of who reported it, the technical cause, what was done or decided and why, the state. keywords: 5 to 10 synonyms and other names (Italian and English, acronym and expansion, the word of a non-technical person; no generic words), merged into the search keywords of the task, which the search weighs above the chatter.",
         "inputSchema": {"type": "object", "properties": {"task_id": integer, "body": string, "keywords": strings, "confirm": confirm},
                         "required": ["task_id", "body", "confirm"]}},
        {"name": "context", "description": "The context pack of a task or project: the task with its description, milestone and latest messages; the project with its description, milestones (the roadmap) and last update (now: its present); the chain with the active rules of each level (the text of a prohibition or an obligation, the title of a preference: read it with read), its facts and procedures by title and its documents; draft rules, warnings (now_missing, now_stale, stale rules) and the lessons that share a tag with the task or its project, by title. Read it before touching code. With neither, the pack of the organisation itself (the company, or company_id), by section. Pass the activity of the session (e.g. code, deploy, data, communication, analysis, migration; several comma-separated) to get only the rules that concern it. With format okf, the pack as an Open Knowledge Format bundle: index.md (every level with its rules, facts, procedures and documents by title and one line, the lessons, the pending items, the warnings), the task and the project as concepts, the binding rules in full (a short one is whole in its index line), log.md (the latest updates of the project, the chatter of the task); read the rest with read and its concept id.",
         "inputSchema": {"type": "object", "properties": {"task_id": integer, "project_id": integer, "company_id": integer, "messages": integer,
                                                          "activity": string, "format": okf,
                                                          "max_tokens": {"type": "integer", "description": "cut the pack to about this many tokens: the messages of the task, the outlines, the lessons, the texts of the project, then the texts of the rules (never a rule); the pack says what was cut (budget)"}}}},
        {"name": "search", "description": "Search the rules, facts and procedures I may read, the documents of the memory (title, summary, keywords and text) and the lessons of every project. Put the person's words in query and synonyms, translations and other names in related_terms; search again with other words when the results miss. Scope tasks searches the episodes instead: title, description and chatter of the tasks I may read (has something like this happened before?), not part of all. Scope sources searches the active cards of the external sources (where the module is installed; also in all): title, public persons, bodies, places, themes, acts, abstract; for a period, a person or a channel use sources_find. mode: lexical (the words), semantic (the meaning, where the hub has vectors: episodes, facts, procedures, lessons, documents, cards; never the rules) or hybrid (both, the default where the vectors are); a hit says which found it (match). A document names the passage that answered (passage: path such as «Art. 43 > comma 2», start) and up to two more to read (passages): read the text from start with document (text, offset), the next passage when the first does not answer, and cite the path. show_expired: the expired notes and lessons too (each says stale expired), for a review. The answer says how the search ran: mode (the one used: lexical when the vectors did not answer), rerank (off, skipped, applied, unavailable), latency_ms.",
         "inputSchema": {"type": "object", "properties": {"query": string, "related_terms": {"type": "array", "items": string},
                                                          "scope": {"type": "string", "enum": list(SCOPES)}, "applies_to": string, "limit": integer,
                                                          "mode": {"type": "string", "enum": list(MODES)}, "show_expired": {"type": "boolean"},
                                                          "as_of": {"type": "string", "description": "YYYY-MM-DD: the facts and procedures that held on that day (started, not yet expired, not yet superseded), superseded ones included"},
                                                          "max_tokens": {"type": "integer", "description": "the results that fit in about this many tokens, an entry too long skipped for the next, never none"}},
                         "required": ["query"]}},
        {"name": "read", "description": "One note (note_id: a rule, a fact with the version to name in note_update, a procedure) or lesson in full; or any concept of the memory by its OKF id (concept: rules/12, facts/3, procedures/8, lessons/5, documents/9, projects/2, tasks/7; with the external sources, sources/12 for a card). With format okf, as an OKF concept: frontmatter (type, status, generated, verified, stale_after, sources) and body.",
         "inputSchema": {"type": "object", "properties": {"note_id": integer, "fact_id": integer, "lesson_id": integer, "concept": string,
                                                          "max_chars": integer, "format": okf}}},
        {"name": "note", "description": "After the person's yes: a note on the record it is about (task_id, project_id, partner_id; none: the organisation itself, the company, or company_id), one per entry, with its section and keywords (synonyms, other names). kind rule (the default): what an agent must always or never do, written only when the person states one, never on a task (what concerns one task goes in a note on the task); severity never (a prohibition), must (an obligation, the default) or prefer; activities: the codes of the work it concerns (none: every activity); state active only for a lead, a member's rule is a draft. kind fact: what the record is (who decides, how a process runs, what was agreed). kind procedure: how an operation is done, step by step; what in it binds is a rule. A fact or a procedure is active at once. A note taken from a document of the memory cites it with document_id: when the original changes, the note is marked source_changed.",
         "inputSchema": {"type": "object", "properties": {
             "name": string, "body": string, "kind": {"type": "string", "enum": list(KINDS)}, "section": section,
             "task_id": integer, "project_id": integer, "partner_id": integer, "company_id": integer,
             "state": {"type": "string", "enum": ["draft", "active"]}, "expires": string, "source_ref": string,
             "valid_from": {"type": "string", "description": "YYYY-MM-DD: the first day a fact or a procedure holds, when it is not the day it is written"},
             "document_id": integer, "severity": {"type": "string", "enum": list(SEVERITIES)}, "activities": strings,
             "keywords": strings, "applies_to": string, "generated_by": generated_by, "confirm": confirm},
             "required": ["name", "body", "confirm"]}},
        {"name": "note_append", "description": "After the person's yes: add a dated, signed paragraph to a fact or a procedure, with new keywords; it becomes verified today.",
         "inputSchema": {"type": "object", "properties": {"note_id": integer, "text": string, "keywords": strings, "confirm": confirm},
                         "required": ["note_id", "text", "confirm"]}},
        {"name": "note_update", "description": "After the person's yes: replace the text of a note (body, with the version returned by read: refused if it changed since), or its title, section, keywords, applies_to, expires; verified true marks it checked today (a rule only by a lead).",
         "inputSchema": {"type": "object", "properties": {
             "note_id": integer, "expected_version": string, "body": string, "name": string, "section": section, "keywords": strings,
             "applies_to": string, "expires": string, "valid_from": string, "verified": {"type": "boolean"}, "confirm": confirm}, "required": ["note_id", "confirm"]}},
        {"name": "fact", "description": "The note tool with kind fact, kept for the clients that call it: what a customer, a project or a task is.",
         "inputSchema": {"type": "object", "properties": {
             "name": string, "body": string, "section": section, "task_id": integer, "project_id": integer, "partner_id": integer,
             "company_id": integer, "keywords": strings, "applies_to": string, "expires": string,
             "document_id": integer, "source_ref": string, "generated_by": generated_by, "confirm": confirm},
             "required": ["name", "body", "confirm"]}},
        {"name": "fact_append", "description": "note_append, kept for the clients that call it.",
         "inputSchema": {"type": "object", "properties": {"fact_id": integer, "text": string, "keywords": strings, "confirm": confirm},
                         "required": ["fact_id", "text", "confirm"]}},
        {"name": "fact_update", "description": "note_update, kept for the clients that call it.",
         "inputSchema": {"type": "object", "properties": {
             "fact_id": integer, "expected_version": string, "body": string, "name": string, "keywords": strings,
             "applies_to": string, "expires": string, "verified": {"type": "boolean"}, "confirm": confirm}, "required": ["fact_id", "confirm"]}},
        {"name": "lesson", "description": "Write a finding after the person's yes: a technical fact learned on a project that will help another one, with no customer, person, amount, record or task number in it (refused otherwise: rewrite it). tags: what it is about (a module, a version, an area), as the projects are tagged: the pack of a task gives the lessons that share a tag with the task or its project; a missing tag is created. activities: the codes of the work it helps; none, every activity. keywords: synonyms, translations and other names, so the search finds it by other words. source_ref (the task) only feeds the leak filter. state active only for a lead.",
         "inputSchema": {"type": "object", "properties": {
             "finding": string, "solution": string, "tags": {"type": "array", "items": string},
             "keywords": {"type": "array", "items": string},
             "activities": {"type": "array", "items": string}, "title": string,
             "applies_to": string, "verified": string, "state": {"type": "string", "enum": ["draft", "active"]},
             "source_ref": string, "generated_by": generated_by, "confirm": confirm}, "required": ["finding", "solution", "confirm"]}},
        {"name": "project", "description": "One project: description, milestones (the roadmap), last update (now: its present) and the warnings on it. With format okf, as an OKF concept (projects/<id>.md).",
         "inputSchema": {"type": "object", "properties": {"project_id": integer, "format": okf}, "required": ["project_id"]}},
        {"name": "log", "description": "The history of a project (its updates, the milestones reached) or of a task (its chatter), newest first, as an OKF log.md.",
         "inputSchema": {"type": "object", "properties": {"project_id": integer, "task_id": integer, "limit": integer}}},
        {"name": "update", "description": "Write a project update after the person's yes, at the end of a session that changed the state of the project: title, status, progress (0-100, default the last one) and a plain-text description with what changed, the decisions taken, the risks and the next steps against the milestones. It becomes the present of the project.",
         "inputSchema": {"type": "object", "properties": {
             "project_id": integer, "name": string, "status": {"type": "string", "enum": list(UPDATE_STATUSES)},
             "progress": integer, "description": string, "confirm": confirm},
             "required": ["project_id", "name", "status", "description", "confirm"]}},
        {"name": "state", "description": "After the person's yes: a lead activates, supersedes or archives a rule or a lesson; the author of a fact or a procedure or a lead supersedes or archives it.",
         "inputSchema": {"type": "object", "properties": {"note_id": integer, "lesson_id": integer, "fact_id": integer, "state": {"type": "string", "enum": list(STATES)},
                                                          "superseded_by_id": integer, "confirm": confirm}, "required": ["state", "confirm"]}},
        {"name": "log_time", "description": "Hours on a task, as the person gives them (never estimated), with the worklog line as description.",
         "inputSchema": {"type": "object", "properties": {"task_id": integer, "hours": {"type": "number"}, "description": string, "date": string, "confirm": confirm},
                         "required": ["task_id", "hours", "description", "confirm"]}},
        {"name": "review", "description": "My review queue, for the consolidation: draft rules to decide, active rules to re-check, projects without a recent update; for a lead also draft lessons and near-duplicate lessons.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "confirm", "description": "After re-checking a note with the person: verified today, with an optional expiry (YYYY-MM-DD). An active rule only by a lead.",
         "inputSchema": {"type": "object", "properties": {"note_id": integer, "expires": string, "confirm": confirm}, "required": ["note_id", "confirm"]}},
        {"name": "documents", "description": "The documents of the memory on a task, project or customer: attachments of that record, files or links to an original elsewhere, with their summary. With no anchor, the documents of the organisation itself (the company, or company_id).",
         "inputSchema": {"type": "object", "properties": {"task_id": integer, "project_id": integer, "partner_id": integer, "company_id": integer}}},
        {"name": "document", "description": "One document of the memory: what and where it is, its summary and, with text true, its text in slices (offset, max_chars). With format okf, as an OKF concept (documents/<id>.md).",
         "inputSchema": {"type": "object", "properties": {"document_id": integer, "text": {"type": "boolean"}, "max_chars": integer, "offset": integer,
                                                          "format": okf}, "required": ["document_id"]}},
        {"name": "document_write", "description": "After the person's yes: bring a document into the memory or read one again. An attachment already on a record: document_id (its id), with summary, keywords, read_on, fingerprint and the converted text. A new one: name and url (a link to an original elsewhere), one anchor (none for a document of the organisation itself, on the company or company_id). A local file is sent with ctx.py document-write --file. keep_text false for a sensitive document.",
         "inputSchema": {"type": "object", "properties": {
             "document_id": integer, "name": string, "url": string, "summary": string, "keywords": {"type": "array", "items": string},
             "task_id": integer, "project_id": integer, "partner_id": integer, "company_id": integer,
             "read_on": string, "fingerprint": string, "keep_text": {"type": "boolean"}, "text": string, "confirm": confirm},
             "required": ["confirm"]}},
        {"name": "document_convert", "description": "After the person's yes: convert the file of an attachment of a record with the conversion service of the hub, where an administrator named one (else convert on your machine with ingest.py): the text is kept next to the original, the document is in the memory, read today. A sensitive document (no text kept) is refused.",
         "inputSchema": {"type": "object", "properties": {"document_id": integer, "confirm": confirm}, "required": ["document_id", "confirm"]}},
        {"name": "document_remove", "description": "Lead only, after the person's yes: take a document out of the memory (what the memory brought in goes; an attachment the people put on the record stays).",
         "inputSchema": {"type": "object", "properties": {"document_id": integer, "confirm": confirm}, "required": ["document_id", "confirm"]}},
        {"name": "document_attachment", "description": "Save the file of an attachment of a record I may read into a local folder (out, else a temporary one), for the local conversion with scripts/ingest.py --attachment; the file itself is never returned here.",
         "inputSchema": {"type": "object", "properties": {"attachment_id": integer, "out": string}, "required": ["attachment_id"]}},
        {"name": "query", "description": "Read-only question on the ERP as myself: search_read of a model with a domain and fields.",
         "inputSchema": {"type": "object", "properties": {"model": string, "domain": {"type": "array"}, "fields": {"type": "array", "items": string}, "limit": integer},
                         "required": ["model"]}},
        {"name": "ask", "description": "Read-only question on the ERP in natural language: grounds into verified model, domain and fields, then executes search_read safely without hallucinations.",
         "inputSchema": {"type": "object", "properties": {"prompt": string, "limit": integer},
                         "required": ["prompt"]}},
        # the external sources, where the hub has texo_sources: the triage of Odoo, in the session
        {"name": "sources_due", "description": "The external source channels overdue (not read for longer than their frequency), with what to look for in each and how it is read. The context pack lists them too.",
         "inputSchema": {"type": "object", "properties": {"project_id": integer}}},
        {"name": "sources_find", "description": "Search the press review and the other external sources already collected (cards and candidates): every word of query, the public persons and themes named, a channel, the period of the event (date_from, date_to as YYYY-MM-DD); newest event first.",
         "inputSchema": {"type": "object", "properties": {"query": string, "persons": strings, "themes": strings, "channel": string, "date_from": string,
                                                          "date_to": string, "states": strings, "limit": integer}}},
        {"name": "sources_inbox", "description": "The candidates waiting for the triage, those holding the watched words first, with the proposals already made; then the cards to write (to_write): kept and not written yet, or sent back by a lead (sent_back), with the notes of their chatter.",
         "inputSchema": {"type": "object", "properties": {"watched_only": {"type": "boolean"}, "limit": integer}}},
        {"name": "sources_collect", "description": "On request: read the channels now (by default the overdue ones); new links become candidates; the pages to check by hand are listed. Nothing is read on a schedule.",
         "inputSchema": {"type": "object", "properties": {"channel_ids": {"type": "array", "items": integer}, "overdue_only": {"type": "boolean"}, "confirm": confirm},
                         "required": ["confirm"]}},
        {"name": "sources_search", "description": "«Search news about X»: what the memory already has on the subject (known), then the channels asked now through their search feeds (found; new links become candidates). since (YYYY-MM-DD): only what was published from that day (a press review: since the last one). Brief entries; read a card in full with read and its concept (sources/12). Then propose a triage to the person: for each candidate the action, the theme, the card in short, the doubts and the questions.",
         "inputSchema": {"type": "object", "properties": {"query": string, "channel_ids": {"type": "array", "items": integer}, "limit": integer, "since": string, "confirm": confirm},
                         "required": ["query", "confirm"]}},
        {"name": "sources_link", "description": "A link the person pasted (from a chat, an email) becomes a candidate, on the channel of its site; a site the organisation does not follow is refused: propose the channel first.",
         "inputSchema": {"type": "object", "properties": {"url": string, "title": string, "confirm": confirm}, "required": ["url", "confirm"]}},
        {"name": "sources_propose", "description": "When the person asked to prepare the triage: keep your proposal on a candidate, so it can be decided in Odoo too. action: keep, discard or check; themes; card: the card in short; doubts, codes of the fixed list: event_date, private_person, homonym, unconfirmed, quote, unreadable, duplicate, partisan, unknown_channel, watch_video; questions: what you need to know.",
         "inputSchema": {"type": "object", "properties": {"item_id": integer, "action": {"type": "string", "enum": ["keep", "discard", "check"]}, "themes": strings,
                                                          "card": string, "doubts": strings, "questions": string, "generated_by": generated_by, "confirm": confirm},
                         "required": ["item_id", "action", "confirm"]}},
        {"name": "sources_triage", "description": "The person's decision on candidates: keep (with themes and a note), keep_as_proposed, or discard.",
         "inputSchema": {"type": "object", "properties": {"item_ids": {"type": "array", "items": integer}, "decision": {"type": "string", "enum": ["keep", "keep_as_proposed", "discard"]},
                                                          "themes": strings, "note": string, "confirm": confirm},
                         "required": ["item_ids", "decision", "confirm"]}},
        {"name": "sources_card", "description": "After the person's yes: write the card of a candidate. abstract in your words (60-120 words: who, what, where, which acts); quotes at most a couple, between «» and attributed: each must be in the page word for word, or the card is refused; public persons, bodies, places, themes as names; event_date (YYYY-MM-DD) when it happened; stance (positive, neutral, negative, none). A card that names persons waits for a lead's approval.",
         "inputSchema": {"type": "object", "properties": {"item_id": integer, "abstract": string, "quotes": string, "persons": strings, "bodies": strings,
                                                          "places": strings, "themes": strings, "acts": string, "event_date": string,
                                                          "stance": {"type": "string", "enum": ["positive", "neutral", "negative", "none"]},
                                                          "relevance": {"type": "integer", "enum": [1, 2, 3]}, "keywords": strings,
                                                          "related_ids": {"type": "array", "items": integer}, "submit": {"type": "boolean"}, "confirm": confirm},
                         "required": ["item_id", "abstract", "confirm"]}},
        {"name": "sources_channel", "description": "Lead only, after the person's yes: a new channel to follow (a site the agent met), with what to look for, how often (every_days) and its feeds [{kind: rss|video|search|search_template|manual, url}] (a search_template has {q} where the subject goes).",
         "inputSchema": {"type": "object", "properties": {"name": string, "website": string,
                                                          "kind": {"type": "string", "enum": ["press", "broadcaster", "video", "public_body", "calls", "legislation", "other"]},
                                                          "look_for": string, "every_days": integer, "project_id": integer, "feeds": {"type": "array"}, "confirm": confirm},
                         "required": ["name", "confirm"]}},
    ]
    return tools


def instructions(hub):
    """The rules of the session, for the instructions of the MCP server: every session starts with them."""
    try:
        data = hub.call("memory/rules")
    except HubError as error:
        return (f"L'Odoo di coordinamento (la memoria) non è raggiungibile: {error}. Dillo alla persona "
                "e non scrivere nulla nella memoria finché non risponde.")
    text = f"{data['rules']}\n\nIl mio ruolo nel hub: {data['role']}."
    if data.get("activities"):
        text += "\n\nAttività dell'organizzazione (l'activity di memory/context): " + "; ".join(
            f"{a['code']} ({a['description'] or a['name']})" for a in data["activities"]) + "."
    if data.get("sections"):
        text += "\n\nSezioni dell'organizzazione (la section di una nota): " + "; ".join(
            f"{s['code']} ({s['description'] or s['name']})" for s in data["sections"]) + "."
    if hub.threads:
        text += "\n\nFili di questa cartella (lo strumento threads dà la guida di ognuno): " + "; ".join(
            f"{t['id']} ({t['type']}, data_class {t['data_class']}, writes {t.get('writes', 'never')})"
            for t in hub.threads) + "."
    return text


def call_tool(hub, name, arguments):
    """Run one tool; writes need confirm true. Returns (text, is_error)."""
    if name not in OPERATIONS:
        return f"unknown tool {name}", True
    arguments = dict(arguments or {})
    if name in WRITE_TOOLS and not arguments.pop("confirm", False):
        return ("Serve una conferma: mostra alla persona che cosa stai per scrivere e richiama con "
                "confirm: true dopo il suo sì. Non è stato scritto nulla."), False
    try:
        data = OPERATIONS[name](hub, arguments)
    except HubError as error:
        return f"error {error.status or ''}: {error}".strip(), True
    if isinstance(data, dict) and data.get("format") == "okf":
        # an OKF bundle is markdown: the agent reads its files as they are, not escaped in JSON
        return render_okf(data), False
    return json.dumps(data, ensure_ascii=False), False


def client_actor(info):
    """The client of the MCP session as an OKF actor, <producer>/<version>: who writes through it."""
    info = info or {}
    name = "-".join(str(info.get("name") or "").split()).lower()
    version = "-".join(str(info.get("version") or "").split())
    return f"{name}/{version or 'unknown'}" if name else None


def handle_message(hub, message):
    """One JSON-RPC message in, one answer out (None for a notification)."""
    method, params, rid = message.get("method"), message.get("params") or {}, message.get("id")
    if method == "initialize":
        hub.generated_by = hub.generated_by or client_actor(params.get("clientInfo"))
        result = {"protocolVersion": params.get("protocolVersion") or "2025-06-18",
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "memoria", "version": __version__},
                  "instructions": instructions(hub)}
    elif method == "notifications/initialized":
        return None
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_schemas()}
    elif method == "tools/call":
        text, is_error = call_tool(hub, params.get("name"), params.get("arguments"))
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        if rid is None:
            return None
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def serve_mcp(hub, stdin=sys.stdin, stdout=sys.stdout):
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        answer = handle_message(hub, message)
        if answer is not None:
            stdout.write(json.dumps(answer, ensure_ascii=False) + "\n")
            stdout.flush()


# -- command line --------------------------------------------------------------------------

def build_parser(extend=None):
    """The commands of the hub; extend(sub) adds the local commands of the CLI."""
    parser = argparse.ArgumentParser(prog="texo", description="Texo: the memory of the hub and the fabric of a customer.")
    parser.add_argument("--root", help="the fabric (a folder with texo.toml); default: the one above the current directory")
    parser.add_argument("--json", action="store_true", help="print the raw answer")
    parser.add_argument("--okf", action="store_true",
                        help="ask in Open Knowledge Format: context, read, task, project, document")
    parser.add_argument("--generated-by", dest="generated_by",
                        help="who writes, as <producer>/<version> (e.g. claude-code/2.1): note, fact, lesson")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("whoami")
    p = sub.add_parser("rules"); p.add_argument("--activity", help="only the rules of the organisation that concern it")
    sub.add_parser("mcp", help="run the MCP server over stdio")
    p = sub.add_parser("my-work"); p.add_argument("--limit", type=int)
    p = sub.add_parser("task"); p.add_argument("task_id", type=int); p.add_argument("--messages", type=int)
    p = sub.add_parser("task-note", help="an internal note in the chatter of a task")
    p.add_argument("task_id", type=int); p.add_argument("body"); p.add_argument("--keywords", nargs="*")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("context", help="the pack of a task or a project; of neither, the pack of the organisation (the company)")
    p.add_argument("--task", dest="task_id", type=int); p.add_argument("--project", dest="project_id", type=int)
    p.add_argument("--company", dest="company_id", type=int, help="another of my companies"); p.add_argument("--messages", type=int)
    p.add_argument("--activity", help="the activity of the session (e.g. code); only the rules that concern it")
    p.add_argument("--max-tokens", dest="max_tokens", type=int, help="cut the pack to about this many tokens (never a rule)")
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--terms", dest="related_terms", nargs="*")
    p.add_argument("--scope", choices=SCOPES); p.add_argument("--applies-to", dest="applies_to"); p.add_argument("--limit", type=int)
    p.add_argument("--mode", choices=MODES, help="the words, the vectors, or both fused (where the hub has texo_vector)")
    p.add_argument("--show-expired", dest="show_expired", action="store_true",
                   help="the expired notes and lessons too, each marked stale: for a review")
    p.add_argument("--as-of", dest="as_of", help="YYYY-MM-DD: the facts and procedures that held on that day")
    p.add_argument("--max-tokens", dest="max_tokens", type=int, help="the results that fit in about this many tokens")
    p = sub.add_parser("read"); p.add_argument("--note", dest="note_id", type=int); p.add_argument("--lesson", dest="lesson_id", type=int)
    p.add_argument("--fact", dest="fact_id", type=int, help="a fact: a note id, as --note")
    p.add_argument("--concept", help="an OKF concept id: rules/12, facts/3, lessons/5, documents/9, projects/2, tasks/7, sources/12")
    p.add_argument("--max-chars", dest="max_chars", type=int)
    p = sub.add_parser("note", help="a rule (default), a fact or a procedure: on a task (not a rule), project, customer or, with none, the organisation")
    p.add_argument("name"); p.add_argument("body"); p.add_argument("--kind", choices=KINDS)
    p.add_argument("--section", help="profile, operations, compliance, sector, offer or another of the organisation's")
    p.add_argument("--task", dest="task_id", type=int)
    p.add_argument("--project", dest="project_id", type=int); p.add_argument("--partner", dest="partner_id", type=int)
    p.add_argument("--state", choices=("draft", "active"))
    p.add_argument("--company", dest="company_id", type=int, help="no anchor: this company instead of the current one")
    p.add_argument("--expires"); p.add_argument("--source-ref", dest="source_ref")
    p.add_argument("--valid-from", dest="valid_from", help="YYYY-MM-DD: the first day a fact or a procedure holds")
    p.add_argument("--document", dest="document_id", type=int, help="the document of the memory the note comes from")
    p.add_argument("--severity", choices=SEVERITIES, help="of a rule: never, must (default) or prefer")
    p.add_argument("--activities", nargs="*", help="the codes of the work it concerns; none: every activity")
    p.add_argument("--keywords", nargs="*"); p.add_argument("--applies-to", dest="applies_to")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("note-append", help="a dated, signed paragraph at the end of a fact or a procedure")
    p.add_argument("note_id", type=int); p.add_argument("text"); p.add_argument("--keywords", nargs="*")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("note-update", help="replace the text of a note (with the version read), or mark it verified")
    p.add_argument("note_id", type=int); p.add_argument("--version", dest="expected_version"); p.add_argument("--body")
    p.add_argument("--name"); p.add_argument("--section"); p.add_argument("--keywords", nargs="*")
    p.add_argument("--applies-to", dest="applies_to"); p.add_argument("--expires"); p.add_argument("--verified", action="store_true")
    p.add_argument("--valid-from", dest="valid_from"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("fact", help="a fact (a note of kind fact) on a task, project or customer; with none, on the organisation")
    p.add_argument("name"); p.add_argument("body"); p.add_argument("--section")
    p.add_argument("--task", dest="task_id", type=int); p.add_argument("--project", dest="project_id", type=int)
    p.add_argument("--partner", dest="partner_id", type=int); p.add_argument("--company", dest="company_id", type=int)
    p.add_argument("--keywords", nargs="*"); p.add_argument("--applies-to", dest="applies_to"); p.add_argument("--expires")
    p.add_argument("--document", dest="document_id", type=int, help="the document of the memory the fact comes from")
    p.add_argument("--source-ref", dest="source_ref")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("fact-append", help="note-append, for a fact")
    p.add_argument("fact_id", type=int); p.add_argument("text"); p.add_argument("--keywords", nargs="*")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("fact-update", help="note-update, for a fact")
    p.add_argument("fact_id", type=int); p.add_argument("--version", dest="expected_version"); p.add_argument("--body")
    p.add_argument("--name"); p.add_argument("--keywords", nargs="*"); p.add_argument("--applies-to", dest="applies_to")
    p.add_argument("--expires"); p.add_argument("--verified", action="store_true"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("lesson", help="a finding without the customer")
    p.add_argument("finding"); p.add_argument("solution"); p.add_argument("--title")
    p.add_argument("--tags", nargs="*", help="what it is about, as the projects are tagged (a module, a version, an area)")
    p.add_argument("--activities", nargs="*", help="the codes of the work it helps; none: every activity")
    p.add_argument("--keywords", nargs="*", help="synonyms, translations and other names: the search finds it by these too")
    p.add_argument("--applies-to", dest="applies_to"); p.add_argument("--verified"); p.add_argument("--state", choices=("draft", "active"))
    p.add_argument("--source-ref", dest="source_ref", help="the task it comes from, for the leak filter only")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("project", help="description, milestones and present of a project"); p.add_argument("project_id", type=int)
    p = sub.add_parser("log", help="the history of a project (updates) or of a task (chatter), as an OKF log.md")
    p.add_argument("--project", dest="project_id", type=int); p.add_argument("--task", dest="task_id", type=int)
    p.add_argument("--limit", type=int)
    p = sub.add_parser("update", help="a project update: the new present of the project")
    p.add_argument("project_id", type=int); p.add_argument("name"); p.add_argument("status", choices=UPDATE_STATUSES)
    p.add_argument("description"); p.add_argument("--progress", type=int); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("state"); p.add_argument("state", choices=STATES); p.add_argument("--note", dest="note_id", type=int)
    p.add_argument("--fact", dest="fact_id", type=int)
    p.add_argument("--lesson", dest="lesson_id", type=int)
    p.add_argument("--superseded-by", dest="superseded_by_id", type=int)
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("log-time"); p.add_argument("task_id", type=int); p.add_argument("hours", type=float)
    p.add_argument("description"); p.add_argument("--date"); p.add_argument("--yes", action="store_true")
    sub.add_parser("review", help="my review queue, for the consolidation")
    p = sub.add_parser("confirm"); p.add_argument("note_id", type=int); p.add_argument("--expires"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("documents", help="the documents of a task, project or customer; of none, those of the organisation")
    p.add_argument("--task", dest="task_id", type=int); p.add_argument("--project", dest="project_id", type=int)
    p.add_argument("--partner", dest="partner_id", type=int); p.add_argument("--company", dest="company_id", type=int)
    p = sub.add_parser("document"); p.add_argument("document_id", type=int); p.add_argument("--text", action="store_true")
    p.add_argument("--max-chars", dest="max_chars", type=int); p.add_argument("--offset", type=int)
    p = sub.add_parser("document-write", help="an attachment of a record into the memory (--id), or a new link (--url) or file (--file)")
    p.add_argument("--id", dest="document_id", type=int, help="an attachment already on a record, or a document to read again")
    p.add_argument("--name"); p.add_argument("--url", help="a link to an original that lives elsewhere")
    p.add_argument("--file", dest="file", help="a local file, put on the record as an attachment")
    p.add_argument("--summary"); p.add_argument("--task", dest="task_id", type=int); p.add_argument("--project", dest="project_id", type=int)
    p.add_argument("--partner", dest="partner_id", type=int); p.add_argument("--company", dest="company_id", type=int)
    p.add_argument("--read-on", dest="read_on"); p.add_argument("--fingerprint")
    p.add_argument("--text-file", dest="text_file", help="file with the converted text to keep next to the original")
    p.add_argument("--keywords", nargs="*", help="synonyms, translations and other names: the search finds it by these too")
    p.add_argument("--no-text", dest="no_text", action="store_true", help="sensitive document: keep no text"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("document-remove", help="lead only: a document out of the memory")
    p.add_argument("document_id", type=int); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("document-convert", help="convert the file of an attachment with the conversion service of the hub, when one is named")
    p.add_argument("document_id", type=int); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("document-attachment", help="save the file of an attachment I may read, for the local conversion")
    p.add_argument("attachment_id", type=int); p.add_argument("--out", help="folder where the file is saved (default: a temporary one)")
    # the external sources (where the hub has texo_sources)
    p = sub.add_parser("sources-due", help="the external source channels overdue")
    p.add_argument("--project", dest="project_id", type=int)
    p = sub.add_parser("sources-find", help="search the press review and the other external sources collected")
    p.add_argument("query", nargs="?"); p.add_argument("--persons", nargs="*"); p.add_argument("--themes", nargs="*")
    p.add_argument("--channel"); p.add_argument("--from", dest="date_from"); p.add_argument("--to", dest="date_to")
    p.add_argument("--states", nargs="*"); p.add_argument("--limit", type=int)
    p = sub.add_parser("sources-inbox", help="the candidates waiting for the triage")
    p.add_argument("--watched", dest="watched_only", action="store_true"); p.add_argument("--limit", type=int)
    p = sub.add_parser("sources-collect", help="read the channels now (default: the overdue ones)")
    p.add_argument("--channels", dest="channel_ids", type=int, nargs="*")
    p.add_argument("--all", dest="overdue_only", action="store_false", default=None); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("sources-search", help="search news about a subject: the memory, then the channels asked now")
    p.add_argument("query"); p.add_argument("--channels", dest="channel_ids", type=int, nargs="*")
    p.add_argument("--limit", type=int); p.add_argument("--since", help="only what was published from this day (YYYY-MM-DD)")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("sources-link", help="a pasted link becomes a candidate")
    p.add_argument("url"); p.add_argument("--title"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("sources-propose", help="keep the agent's proposal on a candidate")
    p.add_argument("item_id", type=int); p.add_argument("action", choices=("keep", "discard", "check"))
    p.add_argument("--themes", nargs="*"); p.add_argument("--card"); p.add_argument("--doubts", nargs="*")
    p.add_argument("--questions"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("sources-triage", help="keep, keep as proposed, or discard candidates")
    p.add_argument("decision", choices=("keep", "keep_as_proposed", "discard")); p.add_argument("item_ids", type=int, nargs="+")
    p.add_argument("--themes", nargs="*"); p.add_argument("--note"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("sources-card", help="write the card of a candidate (quotes checked on the page)")
    p.add_argument("item_id", type=int); p.add_argument("abstract"); p.add_argument("--quotes")
    p.add_argument("--persons", nargs="*"); p.add_argument("--bodies", nargs="*"); p.add_argument("--places", nargs="*")
    p.add_argument("--themes", nargs="*"); p.add_argument("--acts"); p.add_argument("--event-date", dest="event_date")
    p.add_argument("--stance", choices=("positive", "neutral", "negative", "none")); p.add_argument("--relevance", type=int, choices=(1, 2, 3))
    p.add_argument("--keywords", nargs="*"); p.add_argument("--related", dest="related_ids", type=int, nargs="*")
    p.add_argument("--draft", dest="submit", action="store_false", default=None); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("sources-channel", help="lead only: a new channel to follow")
    p.add_argument("name"); p.add_argument("--website"); p.add_argument("--kind", default="press")
    p.add_argument("--look-for", dest="look_for"); p.add_argument("--every-days", dest="every_days", type=int)
    p.add_argument("--project", dest="project_id", type=int)
    p.add_argument("--feeds", help='JSON list: [{"kind": "rss", "url": "..."}]'); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("query"); p.add_argument("model", nargs="?"); p.add_argument("--domain", help="JSON list")
    p.add_argument("--fields", help="comma separated"); p.add_argument("--limit", type=int); p.add_argument("--ask")
    p = sub.add_parser("ask", help="natural language read-only question on the ERP")
    p.add_argument("prompt"); p.add_argument("--limit", type=int)
    if extend:
        extend(sub)
    return parser
