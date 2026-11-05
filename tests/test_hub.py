"""Tests without a real Odoo of the client of the hub (python3 -m unittest discover -s tests)."""
import base64
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from texo import __version__, cli  # noqa: E402
from texo import hub as ctx  # noqa: E402

CWD = os.getcwd()


def setUpModule():
    # outside any fabric: the CLI takes the hub from TEXO_HUB_URL and TEXO_HUB_TOKEN
    os.chdir(tempfile.mkdtemp())


def tearDownModule():
    os.chdir(CWD)


PROJECT = {"id": 2, "name": "Alfa", "customer": "Rossi", "description": "Migrate to 20.0.\nNever on Fridays.",
           "milestones": [{"id": 3, "name": "Go live", "deadline": "2026-10-20", "reached": False, "overdue": True,
                           "open_tasks": 2, "closed_tasks": 1},
                          {"id": 4, "name": "Assessment", "deadline": None, "reached": True, "reached_date": "2026-09-01",
                           "open_tasks": 0, "closed_tasks": 3}],
           "now": {"id": 8, "title": "Week 43", "date": "2026-10-21", "author": "Jane Doe", "status": "at_risk",
                   "progress": 40, "description": "Stage late."}}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


SOURCE = {"id": 21, "title": "The council meets", "url": "https://news.example.com/a", "channel": "Local news",
          "kind": "article", "state": "active", "published_on": "2026-10-28 10:00:00", "event_date": "2026-10-27",
          "watched": True}


class FakeOdoo:
    """Answers the routes like the coordination Odoo, as a urlopen replacement."""

    def __init__(self):
        self.calls = []

    def __call__(self, request, timeout=None):
        route = request.full_url.split("/texo/v1/")[1]
        payload = json.loads(request.data.decode())
        self.calls.append((route, payload))
        if request.headers.get("Authorization") != "Bearer good":
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))
        if route == "memory/read" and payload.get("note_id") == 999:
            body = json.dumps({"name": "odoo.exceptions.MissingError", "message": "Note 999 does not exist"}).encode()
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(body))
        answers = {
            "whoami": {"uid": 7, "login": "jdoe", "name": "Jane Doe", "role": "lead"},
            "memory/rules": {"role": "lead", "rules": "Working memory", "company_rules": [{"id": 2, "title": "Language"}],
                             "activities": [{"code": "code", "name": "Code", "description": "Writing code."},
                                            {"code": "deploy", "name": "Deploy", "description": ""}]},
            "project/my_work": {"tasks": [{"id": 1, "name": "Returns", "project": "Alfa", "customer": "Rossi", "stage": "New"}]},
            "memory/search": {"results": [{"id": 3, "title": "UoM", "state": "active", "lesson": True, "snippet": "the field"}]},
            "memory/note": {"id": 12, "kind": "rule", "state": payload.get("state")},
            "memory/lesson": {"id": 13, "kind": "finding", "state": payload.get("state")},
            "memory/context": {"role": "lead",
                               "task": {"id": 1, "name": "Returns", "milestone": {"id": 3, "name": "Go live", "reached": False}},
                               "project": PROJECT,
                               "levels": [{"model": "project.task", "id": 1, "name": "Returns", "rules": []},
                                          {"model": "project.project", "id": 2, "name": "Alfa",
                                           "rules": [{"id": 2, "title": "Version", "body": "20.0"},
                                                     {"id": 6, "title": "Stage", "body": "Never prod.", "severity": "never",
                                                      "activities": ["deploy"]}]},
                                          {"model": "res.partner", "id": 5, "name": None, "skipped": "not readable"}],
                               "pending": [{"id": 9, "title": "Idea", "author": "Bob"}],
                               "pending_lessons": [{"id": 4, "title": "Draft lesson"}],
                               "warnings": [{"project_id": 2, "warning": "now_stale"}], "lessons": []},
            "project/project": dict(PROJECT, warnings=["now_stale"]),
            "project/update": {"id": 8, "title": payload.get("name"), "date": "2026-10-28", "author": "Jane Doe",
                               "status": payload.get("status"), "progress": payload.get("progress", 40), "description": "Done."},
            "project/log_time": {"timesheet_id": 1},
            "memory/review": {"role": "lead", "drafts": [{"id": 9, "kind": "rule", "title": "Idea", "body": "x",
                                                         "anchor": {"model": "project.project", "id": 2}}],
                              "stale": [], "draft_lessons": [],
                              "projects_without_now": [{"project_id": 2, "name": "Alfa", "warning": "now_missing", "last_update": None}],
                              "duplicates": [{"lesson_id": 3, "other_id": 4, "ratio": 71, "title": "A", "other_title": "B"}]},
            "memory/confirm": {"id": payload.get("note_id"), "confirmed": "2026-10-25"},
            "sources/search": {"known": [SOURCE], "new": 1, "errors": [], "without_search": ["Radio"],
                               "found": [dict(SOURCE, id=22, state="candidate", proposal={
                                   "action": "keep", "themes": ["Council"], "card": "x", "doubts": ["event_date"],
                                   "questions": None, "by": "claude-code/2.1"})]},
            "sources/triage": [dict(SOURCE, state="todo")],
        }
        return FakeResponse(json.dumps(answers.get(route, {})).encode())


class CtxTest(unittest.TestCase):
    def setUp(self):
        self.odoo = FakeOdoo()
        self.hub = ctx.Hub("http://odoo.test/", "good", opener=self.odoo)

    def test_the_external_sources_in_the_session(self):
        env = {"TEXO_HUB_URL": "http://odoo.test", "TEXO_HUB_TOKEN": "good"}
        with unittest.mock.patch.dict(ctx.os.environ, env), unittest.mock.patch.object(ctx, "Hub", lambda u, t: self.hub):
            self.assertEqual(cli.main(["sources-search", "mozione"], out=io.StringIO(), err=io.StringIO()), 2,
                             "a search creates candidates: a write, after the person's yes")
            out = io.StringIO()
            self.assertEqual(cli.main(["sources-search", "mozione", "--yes"], out=out, err=io.StringIO()), 0)
            self.assertEqual(self.odoo.calls[-1], ("sources/search", {"query": "mozione"}))
            self.assertEqual(cli.main(["sources-search", "mozione", "--since", "2026-10-27", "--yes"], out=io.StringIO(),
                                      err=io.StringIO()), 0)
            self.assertEqual(self.odoo.calls[-1], ("sources/search", {"query": "mozione", "since": "2026-10-27"}))
            text = out.getvalue()
            self.assertIn("1 new candidates; no search feed: Radio", text)
            self.assertIn("21  [active, known]  2026-10-27  Local news  *", text)
            self.assertIn("proposal: keep, themes Council, doubts event_date", text)
            self.assertEqual(cli.main(["sources-triage", "keep_as_proposed", "22", "23", "--note", "ok", "--yes"],
                                      out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.odoo.calls[-1], ("sources/triage", {"item_ids": [22, 23], "decision": "keep_as_proposed",
                                                                      "note": "ok"}))
            self.assertEqual(cli.main(["sources-card", "22", "The council meets.", "--persons", "The mayor",
                                       "--event-date", "2026-10-27", "--quotes", "«x», the mayor", "--yes"],
                                      out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.odoo.calls[-1], ("sources/card", {
                "item_id": 22, "abstract": "The council meets.", "quotes": "«x», the mayor", "persons": ["The mayor"],
                "event_date": "2026-10-27"}))
            self.assertEqual(cli.main(["sources-channel", "Radio", "--feeds", '[{"kind": "rss", "url": "https://r.example/f"}]',
                                       "--yes"], out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.odoo.calls[-1][1]["feeds"], [{"kind": "rss", "url": "https://r.example/f"}])
        inbox = ctx.render("sources_inbox", {"total": 1, "watched": 0, "candidates": [
            {"id": 3, "state": "candidate", "channel": "UmbriaON", "title": "Nuovo", "url": "https://u.example/3"}],
            "to_write_total": 1, "to_write": [
            {"id": 7, "state": "todo", "channel": "UmbriaON", "title": "Rimandata", "url": "https://u.example/7",
             "sent_back": True, "notes": ["La data è il 27."]}]})
        self.assertIn("1 cards to write", inbox)
        self.assertIn("7  [todo]", inbox)
        self.assertIn("sent back\n    note: La data è il 27.", inbox)
        self.assertNotIn("cards to write", ctx.render("sources_inbox", {"total": 0, "watched": 0, "candidates": []}),
                         "a hub before the cards to write: only the candidates")
        names = {t["name"]: t for t in ctx.tool_schemas()}
        self.assertIn("confirm", names["sources_card"]["inputSchema"]["required"])
        self.assertNotIn("confirm", names["sources_find"]["inputSchema"].get("required", []), "reading needs no yes")
        refused = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "sources_propose", "arguments": {"item_id": 22, "action": "keep"}}})
        self.assertIn("Needs confirmation", refused["result"]["content"][0]["text"])

    def test_call_strips_slash_and_sends_bearer(self):
        self.assertEqual(ctx.op_whoami(self.hub, {})["login"], "jdoe")
        self.assertEqual(self.odoo.calls[0], ("whoami", {}))

    def test_search_sends_the_mode_only_when_asked_and_shows_who_found_a_hit(self):
        ctx.op_search(self.hub, {"query": "uom"})
        self.assertNotIn("mode", self.odoo.calls[-1][1], "none: the configured mode of the hub, or lexical without vectors")
        ctx.op_search(self.hub, {"query": "uom", "mode": "hybrid"})
        self.assertEqual(self.odoo.calls[-1][1]["mode"], "hybrid")
        self.assertEqual(set(ctx.MODES), {"lexical", "semantic", "hybrid"})
        shown = ctx.render("search", {"results": [
            {"id": 3, "title": "UoM", "state": "active", "lesson": True, "snippet": "the field"},
            {"id": 9, "title": "Resi", "state": "active", "kind": "fact", "fact": True, "snippet": "I resi",
             "match": "semantic", "similarity": 0.83, "score": 0.1818},
            {"id": 131, "title": "Snapshot", "state": "In Progress", "task": True, "concept": "tasks/131", "snippet": "",
             "match": "both", "similarity": 0.61, "score": 0.27}]})
        self.assertEqual(shown, "3  [lesson/active]  UoM\n    the field\n9  [fact/active]  Resi  (semantic, 0.83)\n    I resi"
                                "\n131  [task/In Progress]  Snapshot  (both, 0.61)\n    ")
        # a document names the passage that answered and the others to read
        shown = ctx.render("search", {"results": [
            {"id": 7, "title": "D.Lgs. 36/2023", "document": True, "snippet": "1. Il RUP...",
             "passage": {"path": "Articolo 15 > commi 2-3", "start": 1200, "snippet": "1. Il RUP..."},
             "passages": [{"path": "Articolo 15 > commi 2-3", "start": 1200}, {"path": "Articolo 15 > comma 1", "start": 800}]}]})
        self.assertEqual(shown, "7  [document]  D.Lgs. 36/2023\n    Articolo 15 > commi 2-3  (offset 1200)"
                                "\n      also: Articolo 15 > comma 1  (offset 800)\n    1. Il RUP...")
        # a card of the external sources says its channel, the date of the event and the link
        shown = ctx.render("search", {"results": [
            {"id": 4, "title": "Il Comune paga in ritardo", "source": True, "state": "active", "channel": "Local news",
             "event_date": "2026-10-26", "url": "https://news.example.com/a", "snippet": "Le fatture..."}]})
        self.assertEqual(shown, "4  [card/active]  Il Comune paga in ritardo\n    Local news · 2026-10-26 · "
                                "https://news.example.com/a\n    Le fatture...")
        self.assertIn("sources", ctx.SCOPES)
        env = {"TEXO_HUB_URL": "http://odoo.test", "TEXO_HUB_TOKEN": "good"}
        with unittest.mock.patch.dict(ctx.os.environ, env), unittest.mock.patch.object(ctx, "Hub", lambda u, t: self.hub):
            self.assertEqual(cli.main(["search", "uom", "--mode", "semantic"], out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.odoo.calls[-1][1]["mode"], "semantic")

    def test_errors_carry_odoo_message_and_status(self):
        with self.assertRaises(ctx.HubError) as caught:
            ctx.op_read(self.hub, {"note_id": 999})
        self.assertEqual(caught.exception.status, 404)
        self.assertIn("Note 999", str(caught.exception))
        bad = ctx.Hub("http://odoo.test", "bad", opener=self.odoo)
        with self.assertRaises(ctx.HubError) as caught:
            ctx.op_whoami(bad, {})
        self.assertEqual(caught.exception.status, 401)
        self.assertIn("token", str(caught.exception))

    def test_render_context_and_my_work(self):
        text = ctx.render("context", ctx.op_context(self.hub, {"task_id": 1}))
        self.assertIn("role: lead", text)
        self.assertIn("task 1: Returns  (milestone Go live)", text)
        self.assertIn("project 2: Alfa  [Rossi]\n  Migrate to 20.0.\n  Never on Fridays.", text)
        self.assertIn("  - Go live (OVERDUE 2026-10-20; tasks 2 open, 1 closed)", text)
        self.assertIn("  - Assessment (reached 2026-09-01; tasks 0 open, 3 closed)", text)
        self.assertIn("now: update 8 2026-10-21 Week 43 [at_risk, 40%] by Jane Doe\n  Stage late.", text)
        self.assertIn("  - rule 2 Version: 20.0", text)
        self.assertIn("  - rule 6 [never] Stage: Never prod.  (activities: deploy)", text)
        self.assertIn("(not readable)", text)
        self.assertIn("draft rules: 9 Idea (Bob)", text)
        self.assertIn("warnings: project 2 now_stale", text)
        self.assertIn("draft lessons to review: 4 Draft lesson", text)
        self.assertIn("1  Returns  [Alfa / Rossi]", ctx.render("my_work", ctx.op_my_work(self.hub, {})))

    def test_context_of_the_organisation_needs_no_anchor(self):
        ctx.op_context(self.hub, {})
        self.assertEqual(self.odoo.calls[-1], ("memory/context", {"messages": 5}), "the hub picks the home of the company")
        ctx.op_context(self.hub, {"company_id": 2})
        self.assertEqual(self.odoo.calls[-1][1]["company_id"], 2)
        ctx.op_note(self.hub, {"name": "x", "body": "y", "company_id": 2})
        self.assertEqual(self.odoo.calls[-1][1]["company_id"], 2)
        self.assertNotIn("project_id", self.odoo.calls[-1][1])
        ctx.op_documents(self.hub, {"company_id": 2})
        self.assertEqual(self.odoo.calls[-1][1], {"company_id": 2})

    def test_the_activity_of_the_session_and_the_typed_rule(self):
        ctx.op_context(self.hub, {"task_id": 1, "activity": "code"})
        self.assertEqual(self.odoo.calls[-1], ("memory/context", {"messages": 5, "task_id": 1, "activity": "code"}))
        ctx.op_rules(self.hub, {"activity": "deploy"})
        self.assertEqual(self.odoo.calls[-1], ("memory/rules", {"activity": "deploy"}))
        ctx.op_rules(self.hub, {})
        self.assertEqual(self.odoo.calls[-1], ("memory/rules", {}))
        ctx.op_note(self.hub, {"name": "x", "body": "y", "severity": "never", "activities": ["code", "deploy"]})
        self.assertEqual(self.odoo.calls[-1][1], {"name": "x", "body": "y", "severity": "never",
                                                  "activities": ["code", "deploy"], "state": "draft"})
        self.assertIn("Activities of the organisation (the activity of memory/context): code (Writing code.); "
                      "deploy (Deploy).", ctx.instructions(self.hub))
        note = next(t for t in ctx.tool_schemas() if t["name"] == "note")["inputSchema"]["properties"]
        self.assertEqual(note["severity"]["enum"], ["never", "must", "prefer"])
        self.assertEqual(ctx.render("context", {"role": "lead", "activities": ["code"], "levels": [], "pending": [],
                                                "warnings": [], "lessons": []}), "role: lead  (rules of: code)")
        text = ctx.render("context", {"role": "member", "levels": [{"model": "res.company", "id": 1, "name": "Shouldoo srl",
                                                                   "rules": []}],
                                      "pending": [], "warnings": [], "lessons": [],
                                      "sections": [{"code": "profile"}, {"code": "compliance"}]})
        self.assertIn("res.company 1: Shouldoo srl  (the organisation)", text)
        self.assertIn("sections: profile, compliance", text)

    def test_review_renders_and_confirm_needs_yes(self):
        text = ctx.render("review", ctx.op_review(self.hub, {}))
        self.assertIn("draft rules to decide:", text)
        self.assertIn("9 Idea (project.project 2)", text)
        self.assertIn("projects without a recent update:\n  - 2 Alfa (now_missing, last never)", text)
        self.assertIn("3 A ~ 4 B (71%)", text)
        refused = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                                "params": {"name": "confirm", "arguments": {"note_id": 9}}})
        self.assertIn("Needs confirmation", refused["result"]["content"][0]["text"])
        done = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                                             "params": {"name": "confirm", "arguments": {"note_id": 9, "expires": "2027-01-01", "confirm": True}}})
        self.assertFalse(done["result"]["isError"])
        self.assertEqual(self.odoo.calls[-1], ("memory/confirm", {"note_id": 9, "expires": "2027-01-01"}))

    def test_mcp_dispatch_and_confirmation(self):
        init = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "memoria")
        self.assertEqual(init["result"]["serverInfo"]["version"], __version__, "the version of the core")
        # the rules of the session are the instructions of the server: no call needed to read them
        self.assertTrue(init["result"]["instructions"].startswith("Working memory\n\nMy role in the hub: lead.\n\n"))
        self.assertIsNone(ctx.handle_message(self.hub, {"jsonrpc": "2.0", "method": "notifications/initialized"}))
        tools = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        names = [t["name"] for t in tools]
        self.assertTrue({"note", "lesson", "project", "update"} <= set(names))
        self.assertNotIn("procedure", names, "the procedures are documents: no tool of their own")
        refused = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                                "params": {"name": "note", "arguments": {"name": "x", "body": "y"}}})
        self.assertIn("Needs confirmation", refused["result"]["content"][0]["text"])
        self.assertFalse(any(route == "memory/note" for route, _ in self.odoo.calls))
        written = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                                "params": {"name": "note", "arguments": {"name": "x", "body": "y", "project_id": 2, "confirm": True}}})
        self.assertFalse(written["result"]["isError"])
        self.assertEqual(self.odoo.calls[-1][1]["state"], "draft")
        error = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                              "params": {"name": "read", "arguments": {"note_id": 999}}})
        self.assertTrue(error["result"]["isError"])
        unknown = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 6, "method": "nope"})
        self.assertEqual(unknown["error"]["code"], -32601)

    def test_instructions_without_the_hub_say_write_nothing(self):
        bad = ctx.Hub("http://odoo.test", "bad", opener=self.odoo)
        text = ctx.handle_message(bad, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})["result"]["instructions"]
        self.assertIn("not reachable", text)
        self.assertIn("write nothing", text)
        self.assertEqual(ctx.render("rules", {"role": "member", "rules": "R", "company_rules": [{}]}),
                         "role: member (1 rules of the organisation)\nR")

    def test_lesson_project_and_update(self):
        ctx.op_lesson(self.hub, {"finding": "f", "solution": "s", "tags": ["tests"], "source_ref": "T-1"})
        self.assertEqual(self.odoo.calls[-1], ("memory/lesson", {"finding": "f", "solution": "s", "tags": ["tests"],
                                                                 "source_ref": "T-1", "state": "draft"}))
        text = ctx.render("project", ctx.op_project(self.hub, {"project_id": 2}))
        self.assertEqual(self.odoo.calls[-1], ("project/project", {"project_id": 2}))
        self.assertIn("warnings: now_stale", text)
        refused = ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "update", "arguments": {"project_id": 2, "name": "Week 44", "status": "on_track", "description": "Done."}}})
        self.assertIn("Needs confirmation", refused["result"]["content"][0]["text"])
        env = {"TEXO_HUB_URL": "http://odoo.test", "TEXO_HUB_TOKEN": "good"}
        with unittest.mock.patch.dict(ctx.os.environ, env), unittest.mock.patch.object(ctx, "Hub", lambda u, t: self.hub):
            self.assertEqual(cli.main(["update", "2", "Week 44", "on_track", "Done."], out=io.StringIO(), err=io.StringIO()), 2)
            out = io.StringIO()
            self.assertEqual(cli.main(["update", "2", "Week 44", "on_track", "Done.", "--progress", "50", "--yes"],
                                      out=out, err=io.StringIO()), 0)
            self.assertEqual(self.odoo.calls[-1], ("project/update", {"project_id": 2, "name": "Week 44", "status": "on_track",
                                                                      "description": "Done.", "progress": 50}))
            self.assertIn("now: update 8 2026-10-28 Week 44 [on_track, 50%] by Jane Doe", out.getvalue())
            self.assertEqual(cli.main(["lesson", "f", "s", "--tags", "tests", "--yes"], out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(cli.main(["task-note", "1", "Scope agreed."], out=io.StringIO(), err=io.StringIO()), 2)
            self.assertEqual(cli.main(["task-note", "1", "Scope agreed.", "--yes"], out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.odoo.calls[-1], ("project/task_note", {"task_id": 1, "body": "Scope agreed."}))
            self.assertEqual(cli.main(["task-note", "1", "Returns fixed.", "--keywords", "reso", "RMA", "--yes"],
                                      out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.odoo.calls[-1], ("project/task_note",
                                                   {"task_id": 1, "body": "Returns fixed.", "keywords": ["reso", "RMA"]}))
            out = io.StringIO()
            self.assertEqual(cli.main(["rules"], out=out, err=io.StringIO()), 0)
            self.assertIn("role: lead (1 rules of the organisation)", out.getvalue())

    def test_serve_mcp_reads_lines(self):
        stdin = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n\nnot json\n')
        stdout = io.StringIO()
        ctx.serve_mcp(self.hub, stdin=stdin, stdout=stdout)
        self.assertEqual(json.loads(stdout.getvalue())["result"], {})

    def test_cli_refuses_a_write_without_yes(self):
        err = io.StringIO()
        env = {"TEXO_HUB_URL": "http://odoo.test", "TEXO_HUB_TOKEN": "good"}
        with unittest.mock.patch.dict(ctx.os.environ, env), unittest.mock.patch.object(ctx, "Hub", lambda u, t: self.hub):
            code = cli.main(["note", "x", "y", "--project", "2"], out=io.StringIO(), err=err)
            self.assertEqual(code, 2)
            self.assertIn("--yes", err.getvalue())
            out = io.StringIO()
            self.assertEqual(cli.main(["--json", "note", "x", "y", "--project", "2", "--yes"], out=out, err=err), 0)
            self.assertEqual(json.loads(out.getvalue())["id"], 12)
            out = io.StringIO()
            self.assertEqual(cli.main(["whoami"], out=out, err=err), 0)
            self.assertEqual(out.getvalue().strip(), "Jane Doe (jdoe), role lead")


OKF_ANSWER = {"format": "okf", "okf_version": "0.2",
              "files": [{"path": "index.md", "text": "---\nokf_version: \"0.2\"\n---\n\n# Work\n"},
                        {"path": "log.md", "text": "# Alfa: log\n"}]}


class OkfTest(unittest.TestCase):
    """The memory in Open Knowledge Format: asked with format okf, read as markdown; a write says who wrote it."""

    def setUp(self):
        self.calls = []

        def opener(request, timeout=None):
            route = request.full_url.split("/texo/v1/")[1]
            payload = json.loads(request.data.decode())
            self.calls.append((route, payload))
            if route == "memory/rules":
                return FakeResponse(json.dumps({"role": "lead", "rules": "R"}).encode())
            if payload.get("format") == "okf" or route == "project/log":
                return FakeResponse(json.dumps(OKF_ANSWER).encode())
            return FakeResponse(json.dumps({"id": 12}).encode())

        self.hub = ctx.Hub("http://odoo.test", "good", opener=opener)

    def test_okf_answers_are_markdown_and_writes_carry_the_client(self):
        ctx.handle_message(self.hub, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                      "params": {"clientInfo": {"name": "Claude Code", "version": "2.1.0"}}})
        self.assertEqual(self.hub.generated_by, "claude-code/2.1.0")
        text, error = ctx.call_tool(self.hub, "context", {"task_id": 1, "format": "okf"})
        self.assertFalse(error)
        self.assertEqual(self.calls[-1], ("memory/context", {"messages": 5, "task_id": 1, "format": "okf"}))
        self.assertTrue(text.startswith("<!-- okf: index.md -->\n---\nokf_version"))
        self.assertIn("<!-- okf: log.md -->\n# Alfa: log", text)
        ctx.call_tool(self.hub, "read", {"concept": "facts/3", "format": "okf"})
        self.assertEqual(self.calls[-1], ("memory/read", {"max_chars": 6000, "format": "okf", "concept": "facts/3"}))
        ctx.call_tool(self.hub, "log", {"project_id": 2})
        self.assertEqual(self.calls[-1], ("project/log", {"project_id": 2}))
        ctx.call_tool(self.hub, "fact", {"name": "W", "body": "B", "project_id": 2, "document_id": 9, "confirm": True})
        self.assertEqual(self.calls[-1][1]["generated_by"], "claude-code/2.1.0")
        self.assertEqual(self.calls[-1][1]["document_id"], 9)
        ctx.call_tool(self.hub, "lesson", {"finding": "f", "solution": "s", "generated_by": "codex/1.0", "confirm": True})
        self.assertEqual(self.calls[-1][1]["generated_by"], "codex/1.0", "the call names itself")
        names = [t["name"] for t in ctx.tool_schemas()]
        self.assertIn("log", names)

    def test_cli_okf_and_generated_by(self):
        env = {"TEXO_HUB_URL": "http://odoo.test", "TEXO_HUB_TOKEN": "good"}
        with unittest.mock.patch.dict(ctx.os.environ, env), unittest.mock.patch.object(ctx, "Hub", lambda u, t: self.hub):
            out = io.StringIO()
            self.assertEqual(cli.main(["--okf", "context", "--project", "2"], out=out, err=io.StringIO()), 0)
            self.assertEqual(self.calls[-1][1]["format"], "okf")
            self.assertIn("<!-- okf: index.md -->", out.getvalue())
            self.assertEqual(cli.main(["--okf", "read", "--concept", "rules/12"], out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.calls[-1][1]["concept"], "rules/12")
            self.assertEqual(cli.main(["log", "--task", "1"], out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.calls[-1], ("project/log", {"task_id": 1}))
            self.assertEqual(cli.main(["--generated-by", "gemini-cli/0.9", "note", "x", "y", "--yes"],
                                      out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.calls[-1][1]["generated_by"], "gemini-cli/0.9")


class DocumentTest(unittest.TestCase):
    """The documents of the memory, attachments of their records: the file saved for the
    conversion, the sources cited, a local file sent, the renders."""

    DOCUMENTS = {"documents": [
        {"id": 4, "title": "Returns spec", "type": "url", "url": "https://d/x", "record": {"model": "project.project", "id": 2},
         "has_text": True, "fingerprint": "a" * 64, "changed_on": "2026-10-27 10:00:00"},
        {"id": 12, "title": "scan.pdf", "type": "binary", "mimetype": "application/pdf",
         "record": {"model": "project.task", "id": 3}, "has_text": False, "fingerprint": None}]}

    def setUp(self):
        self.calls = []

        def opener(request, timeout=None):
            route = request.full_url.split("/texo/v1/")[1]
            self.calls.append((route, json.loads(request.data.decode())))
            answers = {
                "document/attachment": {"id": 12, "name": "spec.md", "mimetype": "text/markdown", "size": 5, "sha256": "b" * 64,
                                        "record": {"model": "project.task", "id": 3}, "data": "aGVsbG8="},
                "document/list": self.DOCUMENTS,
                "document/read": dict(self.DOCUMENTS["documents"][1], summary="A scan.", read_on="2026-10-28"),
                "document/remove": {"id": 4, "title": "Returns spec", "removed": True},
                "memory/note": {"id": 20, "title": "Fact", "kind": "rule", "state": "active", "document_id": 4},
                "memory/context": {"role": "member", "levels": [{"model": "project.project", "id": 2, "name": "Alfa",
                                                                "rules": [{"id": 30, "title": "OCA first", "severity": "prefer",
                                                                           "body_omitted": True}],
                                                                "documents": self.DOCUMENTS["documents"]}],
                                   "pending": [], "lessons": [{"id": 7, "title": "Quants", "tags": ["stock", "20.0"]}],
                                   "warnings": [{"id": 20, "title": "Fact", "stale": "source_changed"}]},
                "memory/search": {"results": [dict(self.DOCUMENTS["documents"][0], document=True, score=0.3, snippet="Returns.")]},
                "document/write": dict(self.DOCUMENTS["documents"][1]),
            }
            return FakeResponse(json.dumps(answers[route]).encode())

        self.hub = ctx.Hub("http://odoo.test", "good", opener=opener)

    def test_attachment_is_saved_never_printed(self):
        with tempfile.TemporaryDirectory() as folder:
            result = ctx.op_document_attachment(self.hub, {"attachment_id": 12, "out": folder})
            self.assertEqual(self.calls[-1], ("document/attachment", {"attachment_id": 12}))
            with open(result["path"], "rb") as handle:
                self.assertEqual(handle.read(), b"hello")
            self.assertNotIn("data", result)
            text = ctx.render("document_attachment", result)
            self.assertIn(f"saved {result['path']}  (spec.md, text/markdown, 5 bytes, sha256 {'b' * 64}, record project.task 3)", text)
            self.assertNotIn("hello", text)
        tools = {t["name"]: t for t in ctx.tool_schemas()}
        self.assertIn("document_attachment", tools)
        self.assertNotIn("document_attachment", ctx.WRITE_TOOLS)
        self.assertIn("document_id", tools["note"]["inputSchema"]["properties"])
        self.assertIn("url", tools["document_write"]["inputSchema"]["properties"])
        self.assertIn("document_remove", ctx.WRITE_TOOLS)

    def test_note_cites_the_document_and_an_attachment_becomes_one(self):
        ctx.op_note(self.hub, {"name": "Fact", "body": "Returns are separate.", "project_id": 2, "document_id": 4})
        self.assertEqual(self.calls[-1][1]["document_id"], 4)
        ctx.op_document_write(self.hub, {"document_id": 12, "summary": "A scan.", "text": "# Scan"})
        self.assertEqual(self.calls[-1], ("document/write", {"document_id": 12, "summary": "A scan.", "text": "# Scan",
                                                             "keep_text": True}))
        ctx.op_document_remove(self.hub, {"document_id": 4})
        self.assertEqual(self.calls[-1], ("document/remove", {"document_id": 4}))

    def test_renders_show_what_and_where(self):
        documents = ctx.render("documents", ctx.op_documents(self.hub, {"project_id": 2}))
        self.assertIn("4  Returns spec  (url: https://d/x; on project.project 2)  text  changed 2026-10-27 10:00:00", documents)
        self.assertIn("12  scan.pdf  (binary: application/pdf; on project.task 3)", documents)
        document = ctx.render("document", ctx.op_document(self.hub, {"document_id": 12}))
        self.assertIn("read_on: 2026-10-28", document)
        self.assertIn("summary: A scan.", document)
        context = ctx.render("context", ctx.op_context(self.hub, {"project_id": 2}))
        self.assertIn("  documents: 4 Returns spec (changed), 12 scan.pdf", context)
        self.assertIn("20 Fact (source_changed)", context)
        self.assertIn("  - 7 Quants  [stock, 20.0]", context)
        self.assertIn("  - rule 30 [prefer] OCA first  (text: read --note)", context)
        self.assertIn("documents", ctx.SCOPES)
        found = ctx.render("search", ctx.op_search(self.hub, {"query": "returns"}))
        self.assertIn("4  [document]  Returns spec\n    Returns.", found)
        self.assertEqual(ctx.render("document_remove", ctx.op_document_remove(self.hub, {"document_id": 4})),
                         "4 Returns spec: out of the memory")

    def test_cli_document_attachment_a_local_file_and_note_document(self):
        with unittest.mock.patch.dict(ctx.os.environ, {"TEXO_HUB_URL": "http://odoo.test", "TEXO_HUB_TOKEN": "good"}), \
                unittest.mock.patch.object(ctx, "Hub", lambda url, token: self.hub), tempfile.TemporaryDirectory() as folder:
            out = io.StringIO()
            self.assertEqual(cli.main(["document-attachment", "12", "--out", folder], out=out, err=io.StringIO()), 0)
            self.assertIn("saved " + folder, out.getvalue())
            self.assertEqual(cli.main(["note", "Fact", "Body.", "--project", "2", "--document", "4", "--yes"], out=out, err=io.StringIO()), 0)
            self.assertEqual(self.calls[-1][1]["document_id"], 4)
            local = os.path.join(folder, "procedura.md")
            with open(local, "w", encoding="utf-8") as handle:
                handle.write("# Procedura")
            self.assertEqual(cli.main(["document-write", "--file", local, "--task", "3", "--yes"], out=out, err=io.StringIO()), 0)
            sent = self.calls[-1][1]
            self.assertEqual((sent["name"], base64.b64decode(sent["data"]), sent["task_id"]), ("procedura.md", b"# Procedura", 3))


class FactTest(unittest.TestCase):
    """The notes that describe (facts, procedures): written, appended, replaced with the version read, shown by title
    in the pack; the fact commands are the note commands with kind fact."""

    FACT = {"id": 9, "kind": "fact", "title": "Warehouse", "body": "Two locations.", "version": "abc123",
            "verified": "2026-10-29"}

    def setUp(self):
        self.calls = []

        def opener(request, timeout=None):
            route = request.full_url.split("/texo/v1/")[1]
            self.calls.append((route, json.loads(request.data.decode())))
            answers = {"memory/note": self.FACT, "memory/note_append": self.FACT, "memory/note_update": self.FACT,
                       "memory/read": self.FACT,
                       "memory/context": {"role": "member", "levels": [{"model": "project.project", "id": 2, "name": "Alfa",
                                                                       "rules": [], "facts": [{"id": 9, "title": "Warehouse"},
                                                                                              {"id": 10, "title": "Old", "stale": "unverified"}],
                                                                       "procedures": [{"id": 11, "title": "Returns", "section": "operations"}]}],
                                          "pending": [], "lessons": [], "warnings": []}}
            return FakeResponse(json.dumps(answers[route]).encode())

        self.hub = ctx.Hub("http://odoo.test", "good", opener=opener)

    def test_write_append_update_and_render(self):
        ctx.op_fact(self.hub, {"name": "Warehouse", "body": "Two locations.", "project_id": 2, "keywords": ["magazzino"]})
        self.assertEqual(self.calls[-1], ("memory/note", {"name": "Warehouse", "body": "Two locations.", "project_id": 2,
                                                          "keywords": ["magazzino"], "kind": "fact"}))
        ctx.op_fact_append(self.hub, {"fact_id": 9, "text": "A third one."})
        self.assertEqual(self.calls[-1], ("memory/note_append", {"note_id": 9, "text": "A third one."}))
        ctx.op_fact_update(self.hub, {"fact_id": 9, "expected_version": "abc123", "body": "One.", "verified": False})
        self.assertEqual(self.calls[-1], ("memory/note_update", {"note_id": 9, "expected_version": "abc123", "body": "One."}))
        self.assertEqual(ctx.render("read", ctx.op_read(self.hub, {"fact_id": 9})),
                         "fact 9: Warehouse  verified 2026-10-29  version abc123\nTwo locations.")
        self.assertEqual(self.calls[-1][1]["note_id"], 9, "a fact is a note")
        ctx.op_note(self.hub, {"name": "Returns", "body": "1. Check.", "kind": "procedure", "section": "operations",
                               "task_id": 4})
        self.assertEqual(self.calls[-1][1], {"name": "Returns", "body": "1. Check.", "kind": "procedure",
                                             "section": "operations", "task_id": 4}, "no state: active at once")
        context = ctx.render("context", ctx.op_context(self.hub, {"project_id": 2}))
        self.assertIn("  facts: 9 Warehouse, 10 Old (unverified)", context)
        self.assertIn("  procedures: 11 Returns [operations]", context)
        self.assertTrue({"fact", "note_append", "note_update"} <= set(ctx.WRITE_TOOLS))
        self.assertTrue({"facts", "procedures"} <= set(ctx.SCOPES))
        env = {"TEXO_HUB_URL": "http://odoo.test", "TEXO_HUB_TOKEN": "good"}
        with unittest.mock.patch.dict(ctx.os.environ, env), unittest.mock.patch.object(ctx, "Hub", lambda u, t: self.hub):
            self.assertEqual(cli.main(["note", "Close", "1. Bank.", "--kind", "procedure", "--section", "operations",
                                       "--yes"], out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.calls[-1][1]["kind"], "procedure")
            self.assertEqual(cli.main(["note-append", "9", "More.", "--yes"], out=io.StringIO(), err=io.StringIO()), 0)
            self.assertEqual(self.calls[-1], ("memory/note_append", {"note_id": 9, "text": "More."}))


if __name__ == "__main__":
    unittest.main()
