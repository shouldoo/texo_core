# Copyright 2026 Daniele Lucarelli
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Load a demo customer into a test database of the coordination Odoo: a fictional organisation, its people,
customers, projects, tasks, chatter, hours, rules, facts, procedures, documents and lessons.

Everything is invented. The data live in the demo customer repository (demo/data.py); this file is the logic,
the same for every demo. It exists to test and measure the memory (the texo CLI, the MCP server, the skills) on a
database that holds nothing real: it refuses any database the data file does not name in DATABASES.

Run it through the wrapper, from the root of the demo customer repository, which keeps the tokens out of the
terminal:

    bash core/setup/load-demo.sh <database> [--create]

The wrapper pipes into `odoo shell` of the coordination stack: SEEDS (the hub/seed.toml of the industries of the
fabric, applied first as the administrator, so the activities and sections the data use exist), TEXTS (the
converted texts of demo/texts/*.md, for the documents that name a text_file), the data file and this file. It
reads the lines that start with `@@`: `@@TOKEN <role> <key>` goes to ~/.config/texo/<customer>.env (mode 600),
`@@EVAL <json>` to .texo/eval-<database>.json, the question set of scripts/eval_memoria.py with the ids of this
database. Idempotent: records are found by login, reference, name or text; the demo tokens are revoked and
generated again at every run; nothing is deleted.

The data file: DATABASES, TOKEN_NAME, TOKEN_DAYS, COMPANY, USERS, WORK_GROUPS, TEAM, DELIVERY_STAGES,
TICKET_STAGES, HOME_STAGES, TICKET_TAG, ASSISTANCE, SOURCES_FOLDER, ATTACHMENTS, ORGANISATION, CUSTOMERS,
LESSONS, EVAL. ORGANISATION may carry projects of its own (an organisation without customers), a customer may
have no tickets, a document may take its text from TEXTS (text_file) or be a generated PDF (pdf).

Imported by the tests, the module only exposes the helpers and seed(): nothing runs without `env`.
"""
import hashlib
import html
import json
import re
from datetime import datetime, timedelta

try:
    import demo_data as data
except ModuleNotFoundError:
    # piped into odoo shell behind demo/data.py (setup/load-demo.sh): its names are already here
    import types
    data = types.SimpleNamespace(**globals())


def pdf_bytes(title, lines):
    """A minimal, deterministic PDF with one page of Helvetica text, standard library only."""
    def esc(text):
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = ["BT", "/F1 18 Tf", "72 760 Td", f"({esc(title)}) Tj", "/F1 11 Tf", "0 -30 Td"]
    for line in lines:
        content += [f"({esc(line)}) Tj", "0 -16 Td"]
    content.append("ET")
    stream = "\n".join(content).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def html_of(text):
    """Plain text as HTML: a paragraph per blank line, a line break per newline."""
    paragraphs = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    return "".join("<p>%s</p>" % html.escape(p).replace("\n", "<br>") for p in paragraphs)


def plain_of(body):
    """The text of a chatter message: tags stripped, entities decoded, spaces collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body or ""))).strip()


def anchor_of(where, customer, projects, tasks):
    """The anchor of a rule, a fact, a procedure or a document: the partner of a customer, a project, a task;
    none (the organisation itself, the company) when where is missing or "organisation"."""
    if not where or where == "organisation":
        return {}
    if where == "customer":
        return {"partner_id": customer.id}
    kind, _, name = where.partition(":")
    if kind == "project":
        return {"project_id": projects[name].id}
    project_name, _, task_name = name.partition("/")
    return {"task_id": tasks[(project_name, task_name)].id}


def pack_lessons(lessons, tags, limit=5):
    """What the context pack of a task carries: the active lessons that share a tag with the task or its project,
    those that share more first, then the newest (memory.lesson._agent_pack)."""
    tags = set(tags)
    shared = [(len(tags & set(lesson["tags"])), lesson_id) for lesson, lesson_id in lessons if lesson["state"] == "active"]
    return [lesson_id for overlap, lesson_id in sorted((s for s in shared if s[0]), key=lambda s: (-s[0], -s[1]))[:limit]]


def _xid(env, xmlid):
    return env.ref(xmlid).id


class Seeder:
    """The seed of one run: the environment, the day, the people, and what was written, by name."""

    def __init__(self, env):
        self.env = env
        self.today = datetime.now().date()
        self.now = datetime.now()
        self.users = {}
        self.rules = {}      # (anchor key, name) -> (id, state)
        self.notes = {}      # (kind, name) -> id
        self.documents = {}  # key -> id
        self.lessons = []    # [(data, id)]
        self.summary = {"projects": [], "rules": 0, "tasks": 0, "tickets": 0, "lessons": 0, "documents": 0}

    # -- helpers ---------------------------------------------------------------------------------------------
    def day(self, days_ago):
        return self.today - timedelta(days=days_ago)

    def tags(self, names):
        return self.env["memory.lesson"]._tags_from_names(names or [])

    def stage(self, project, name, sequence, fold=False):
        Stage = self.env["project.task.type"].with_context(active_test=False)
        stage = Stage.search([("name", "=", name), ("project_ids", "in", project.id)], limit=1)
        if not stage:
            stage = Stage.create({"name": name, "sequence": sequence, "fold": fold, "project_ids": [(4, project.id)]})
        else:
            stage.write({"sequence": sequence, "fold": fold})
        return stage

    def stages(self, project, names):
        stages = {name: self.stage(project, name, (i + 1) * 10, fold=i == len(names) - 1) for i, name in enumerate(names)}
        project.write({"type_ids": [(6, 0, [s.id for s in stages.values()])]})
        return stages

    def project(self, name, partner, tags, description, stage_names):
        Project = self.env["project.project"].with_context(active_test=False)
        team = self.env["res.users"].browse([self.users[r].id for r in data.TEAM])
        project = Project.search([("name", "=", name)], limit=1) or Project.create({
            "name": name, "partner_id": partner.id if partner else False, "privacy_visibility": "followers",
            "user_id": self.users["lead"].id, "allowed_internal_user_ids": [(4, u.id) for u in team],
            "type_ids": [(5, 0, 0)],  # no default stages: the seed gives each project its own
        })
        project.write({"description": description, "allow_milestones": True,
                       "tag_ids": [(6, 0, self.tags(tags).ids)], "allowed_internal_user_ids": [(4, u.id) for u in team]})
        project.message_subscribe(partner_ids=team.partner_id.ids)
        return project, self.stages(project, stage_names)

    def milestones(self, project, items):
        Milestone = self.env["project.milestone"]
        milestones = {}
        for name, deadline, reached in items:
            milestone = Milestone.search([("project_id", "=", project.id), ("name", "=", name)], limit=1) \
                or Milestone.create({"name": name, "project_id": project.id})
            milestone.write({"deadline": self.today + timedelta(days=deadline), "is_reached": reached is not None})
            if reached is not None:
                milestone.reached_date = self.day(reached)  # reached in the past, not on the seed day
            milestones[name] = milestone
        return milestones

    def task(self, project, item, stages, milestones=None, parents=None, ticket=False):
        Task = self.env["project.task"].with_context(active_test=False)
        task = Task.search([("project_id", "=", project.id), ("name", "=", item["name"])], limit=1)
        tags = list(item.get("tags") or []) + ([data.TICKET_TAG] if ticket else [])
        vals = {"name": item["name"], "project_id": project.id, "allocated_hours": item.get("hours") or 0,
                "stage_id": stages[item["stage"]].id, "tag_ids": [(6, 0, self.tags(tags).ids)],
                "user_ids": [(6, 0, [self.users[item["who"]].id])], "priority": item.get("priority") or "0",
                "description": html_of(item.get("description")),
                "date_deadline": datetime.combine(self.day(-item["deadline"]), datetime.min.time())
                if item.get("deadline") is not None else False,
                "milestone_id": milestones[item["milestone"]].id if item.get("milestone") else False,
                "parent_id": parents[item["parent"]].id if item.get("parent") else False}
        if task:
            task.write(vals)
        else:
            task = Task.create(vals)
        if ticket and item.get("days") is not None:
            # a ticket opened in the past: the day it arrived is its creation day
            task.sudo().write({"create_date": datetime.combine(self.day(item["days"]), self.now.time())})
        for who, days_ago, text in item.get("notes") or []:
            self.note(task, who, days_ago, text)
        for who, days_ago, hours, text in item.get("worklog") or []:
            self.time(task, who, days_ago, hours, text)
        if item.get("attachment"):
            self.attachment(task, item["attachment"])
        self.summary["tickets" if ticket else "tasks"] += 1
        return task

    def note(self, task, who, days_ago, text):
        """An internal note in the chatter of the task, as the person, dated in the past; found by its text."""
        wanted = plain_of(text)
        if any(plain_of(m.body) == wanted for m in task.message_ids):
            return
        result = task.with_user(self.users[who])._texo_post_note(text)
        self.env["mail.message"].browse(result["message_id"]).sudo().write(
            {"date": datetime.combine(self.day(days_ago), self.now.time())})

    def time(self, task, who, days_ago, hours, text):
        """A timesheet line of the person on the task; found by text and hours."""
        if self.env["account.analytic.line"].search([("task_id", "=", task.id), ("name", "=", text),
                                                     ("unit_amount", "=", hours)], limit=1):
            return
        task.with_user(self.users[who])._texo_log_time(hours, text, date=self.day(days_ago).isoformat())

    def attachment(self, task, key):
        """A PDF attached to a task, for the Odoo way of bringing a document in."""
        name, title, lines = data.ATTACHMENTS[key]
        Attachment = self.env["ir.attachment"]
        if not Attachment.search([("res_model", "=", "project.task"), ("res_id", "=", task.id), ("name", "=", name)], limit=1):
            Attachment.create({"name": name, "res_model": "project.task", "res_id": task.id,
                               "raw": pdf_bytes(title, lines), "mimetype": "application/pdf"})

    def updates(self, project, items):
        Update = self.env["project.update"]
        update = None
        for title, status, progress, days_ago, text in items:
            update = Update.search([("project_id", "=", project.id), ("name", "=", title)], limit=1) or \
                Update.with_user(self.users["lead"]).create({"project_id": project.id, "name": title, "status": status,
                                                             "progress": progress, "description": html_of(text)})
            update.date = self.day(days_ago)
        # the present is the last update of the seed, whatever the order of a re-run
        project.sudo().last_update_id = update
        return update

    def realign_keywords(self, record, keywords, field="keywords"):
        """The keywords of a record written before follow the data: the weekly review adds the synonyms the
        measure asked for, and the seed brings them to a database seeded earlier (sudo: the data is fictional,
        the writer of the record is the seed itself)."""
        wanted = keywords or False
        if record[field] != wanted:
            record.sudo().write({field: wanted})
            self.summary["realigned"] = self.summary.get("realigned", 0) + 1

    def rule(self, item, anchor, key):
        Note = self.env["memory.note"]
        domain = [("kind", "=", "rule"), ("name", "=", item["name"])] + \
            ([(k, "=", v) for k, v in anchor.items()] or [("company_id", "!=", False)])
        existing = Note.search(domain, limit=1)
        if existing:
            self.realign_keywords(existing, item.get("keywords"))
            self.rules[(key, item["name"])] = (existing.id, existing.state)
            return existing.id
        who = item.get("who") or "lead"
        state = item.get("state") or ("active" if who == "lead" else "draft")
        result = Note.with_user(self.users[who])._agent_note(
            item["name"], item["body"], kind="rule", state=state, severity=item["severity"],
            activities=item.get("activities"), section=item.get("section"), keywords=item.get("keywords"),
            document_id=self.documents.get(item["document"]) if item.get("document") else None, **anchor)
        self.rules[(key, item["name"])] = (result["id"], state)
        self.summary["rules"] += 1
        return result["id"]

    def memory_note(self, item, anchor):
        """A fact or a procedure, as the person, on its anchor; found by kind, title and anchor."""
        Note = self.env["memory.note"]
        domain = [("kind", "=", item["kind"]), ("name", "=", item["name"])] + \
            ([(k, "=", v) for k, v in anchor.items()] or [("company_id", "!=", False)])
        note = Note.search(domain, limit=1)
        if note:
            self.realign_keywords(note, item.get("keywords"))
        else:
            who = item.get("who") or "lead"
            expires = self.day(-item["expires"]).isoformat() if item.get("expires") else None
            note = Note.browse(Note.with_user(self.users[who])._agent_note(
                item["name"], item["body"], kind=item["kind"], section=item.get("section"),
                keywords=item.get("keywords"), applies_to=item.get("applies_to"), expires=expires,
                document_id=self.documents.get(item["document"]) if item.get("document") else None, **anchor)["id"])
        self.notes[(item["kind"], item["name"])] = note.id
        return note.id

    def document(self, item, anchor):
        """A document of the memory on its anchor: a link to an original elsewhere, or the PDF of the cloud
        folder read with its text; a sensitive one keeps no text. Found by its link."""
        Attachment = self.env["ir.attachment"]
        lead = self.users["lead"]
        if item.get("pdf"):
            name, title, lines = item["pdf"]
            raw = pdf_bytes(title, lines)
            url = f"{data.SOURCES_FOLDER}/{name}"
            fingerprint = hashlib.sha256(raw).hexdigest()
            text = "## " + title + "\n\n" + "\n".join(lines) + "\n"
        else:
            url, fingerprint = item["url"], None
            text = data.TEXTS[item["text_file"]] if item.get("text_file") else item.get("text")
        res_model = {"task_id": "project.task", "project_id": "project.project", "partner_id": "res.partner"}.get(
            next(iter(anchor), None), "res.company")
        document = Attachment.search([("url", "=", url), ("res_model", "=", res_model), ("texo_document", "=", True)],
                                     limit=1)
        if document:
            self.realign_keywords(document, item.get("keywords"), "texo_keywords")
        else:
            result = Attachment.with_user(lead)._texo_write(
                name=item["name"], url=url, summary=item["summary"], keywords=item.get("keywords"),
                fingerprint=fingerprint, read_on=self.today.isoformat(), keep_text=item.get("keep_text", True),
                text=text, **anchor)
            document = Attachment.browse(result["id"])
            self.summary["documents"] += 1
        self.documents[item["key"]] = document.id
        return document.id

    # -- the parts -------------------------------------------------------------------------------------------
    def people(self):
        env = self.env
        env.company.write(data.COMPANY)
        env.company.partner_id.write({"name": data.COMPANY["name"]})
        Users = env["res.users"].with_context(no_reset_password=True, active_test=False)
        for role, (name, login, group) in data.USERS.items():
            user = env.ref("base.user_admin") if role == "admin" else Users.search([("login", "=", login)], limit=1)
            groups = [_xid(env, g) for g in data.WORK_GROUPS] + ([_xid(env, group)] if group else [])
            vals = {"name": name, "group_ids": [(4, g) for g in groups]}
            if user:
                user.write(vals)
            else:
                user = Users.create(dict(vals, login=login, email=login))
            if not env["hr.employee"].search([("user_id", "=", user.id)], limit=1):
                env["hr.employee"].create({"name": name, "user_id": user.id})
            self.users[role] = user
        self.summary["users"] = {role: user.id for role, user in self.users.items()}

    def industries(self):
        """The seed of the industries of the fabric, as its administrator: the activities, sections, rules and
        templates of the sector, before the data that use them."""
        for payload in globals().get("SEEDS") or []:
            result = self.env["memory.seed"].with_user(self.users["admin"])._agent_seed(**dict(payload, apply=True))
            self.summary.setdefault("industries", {})[payload["industry"]] = result["counts"]

    def organisation(self):
        """The memory of the organisation itself (the company): documents, rules, facts and procedures; its
        internal work on its home project."""
        for item in data.ORGANISATION["documents"]:
            self.document(item, {})
        for item in data.ORGANISATION["rules"]:
            self.rule(dict(item, who="lead", state="active"), {}, "home")
        for item in data.ORGANISATION["notes"]:
            self.memory_note(dict(item, who="lead"), {})
        home = self.env.company._texo_home_project()
        home.write({"name": data.COMPANY["name"]})
        stages = self.stages(home, data.HOME_STAGES)
        for item in data.ORGANISATION["home_tasks"]:
            self.task(home, item, stages)
        self.summary["home"] = home.id
        # an organisation without customers (an association, a civic list) works on projects of its own:
        # no partner, the chain goes from the project to the company
        own = data.ORGANISATION.get("projects") or []
        if own:
            projects, tasks = self.projects(own, self.env["res.partner"])
            for item in data.ORGANISATION.get("project_rules") or []:
                self.rule(dict(item, state=item.get("state", "active")), anchor_of(item["where"], None, projects, tasks),
                          "own:" + item["where"])
            for item in data.ORGANISATION.get("project_documents") or []:
                self.document(item, anchor_of(item["where"], None, projects, tasks))
            for item in data.ORGANISATION.get("project_notes") or []:
                self.memory_note(item, anchor_of(item["where"], None, projects, tasks))

    def projects(self, specs, partner):
        """The projects of a customer, or of the organisation itself (partner empty): milestones, tasks,
        updates. Returns ({name: project}, {(project name, task name): task})."""
        projects, tasks = {}, {}
        for spec in specs:
            project, stages = self.project(spec["name"], partner, spec["tags"], spec["description"],
                                           spec.get("stages") or data.DELIVERY_STAGES)
            milestones = self.milestones(project, spec["milestones"])
            parents = {}
            for task_item in spec["tasks"]:
                task = self.task(project, task_item, stages, milestones, parents)
                parents[task_item["name"]] = task
                tasks[(spec["name"], task_item["name"])] = task
            self.updates(project, spec["updates"])
            projects[spec["name"]] = project
            self.summary["projects"].append({"project": project.id, "tasks": len(spec["tasks"])})
        return projects, tasks

    def customer(self, item, eval_set):
        env = self.env
        Partner = env["res.partner"].with_context(active_test=False)
        partner = Partner.search([("ref", "=", item["ref"])], limit=1) or Partner.create(
            {"ref": item["ref"], "name": item["name"], "is_company": True, "city": item["city"]})
        projects, tasks, firsts = {}, {}, None
        for spec in item["projects"]:
            project, stages = self.project(spec["name"], partner, spec["tags"], spec["description"], data.DELIVERY_STAGES)
            milestones = self.milestones(project, spec["milestones"])
            parents = {}
            for task_item in spec["tasks"]:
                task = self.task(project, task_item, stages, milestones, parents)
                parents[task_item["name"]] = task
                tasks[(spec["name"], task_item["name"])] = task
            update = self.updates(project, spec["updates"])
            projects[spec["name"]] = project
            self.summary["projects"].append({"project": project.id, "tasks": len(spec["tasks"])})
            if firsts is None:
                first = spec["tasks"][0]
                firsts = {"task_id": tasks[(spec["name"], first["name"])].id, "now": update.id,
                          "milestone": milestones[first["milestone"]].id if first.get("milestone") else None,
                          "project": spec["name"], "tags": set(spec["tags"]) | set(first.get("tags") or [])}
        if item.get("tickets"):
            assistance, stages = self.project(data.ASSISTANCE.format(name=item["name"]), partner, [],
                                              "<p>I ticket di %s: la memoria episodica dell'assistenza.</p>" % html.escape(item["name"]),
                                              data.TICKET_STAGES)
            for ticket in item["tickets"]:
                self.task(assistance, ticket, stages, ticket=True)
            self.summary["projects"].append({"project": assistance.id, "tickets": len(item["tickets"])})
        for rule in item["rules"]:
            self.rule(rule, anchor_of(rule["where"], partner, projects, tasks), item["ref"] + ":" + rule["where"])
        for document in item["documents"]:
            self.document(document, anchor_of(document["where"], partner, projects, tasks))
        for note in item["notes"]:
            self.memory_note(note, anchor_of(note["where"], partner, projects, tasks))
        # the pack question of the customer: the first task of its first project, with the rules of its chain
        # (the active ones of the customer and of that project) and the lessons by tag
        chain = {"customer", "project:" + firsts["project"]}
        firsts["rules"] = [rule_id for (key, _), (rule_id, state) in self.rules.items()
                           if state == "active" and key.startswith(item["ref"] + ":") and key.split(":", 1)[1] in chain]
        eval_set.append({"task_id": firsts["task_id"], "now": firsts["now"], "milestone": firsts["milestone"],
                         "rules": firsts["rules"], "tags": sorted(firsts["tags"])})

    def findings(self):
        Lesson = self.env["memory.lesson"].with_context(active_test=False)
        for item in data.LESSONS:
            lesson = Lesson.search([("name", "=", item["title"])], limit=1)
            if lesson:
                self.realign_keywords(lesson, item.get("keywords"))
            else:
                # a lead activates; a member's finding is a draft for the review
                who = "lead" if item["state"] == "active" else item["who"]
                lesson = Lesson.browse(Lesson.with_user(self.users[who])._agent_lesson(
                    item["finding"], item["solution"], tags=item["tags"], title=item["title"],
                    applies_to=item.get("applies_to"), verified=item.get("verified"), state=item["state"],
                    activities=item.get("activities"), keywords=item.get("keywords"))["id"])
                self.summary["lessons"] += 1
            self.lessons.append((item, lesson.id))

    def questions(self, eval_set):
        """The question set with the ids of this database: the pack questions get their lessons, the search
        questions their expected ids."""
        for question in eval_set:
            question["lessons"] = pack_lessons(self.lessons, question.pop("tags"))
        by_key = {item["key"]: lesson_id for item, lesson_id in self.lessons}
        rules_by_name = {name: rule_id for (_, name), (rule_id, _) in self.rules.items()}
        for item in data.EVAL:
            expected = []
            for want in item["expected"]:
                (kind, ref), = want.items()
                if kind == "lesson":
                    expected.append({"lesson": by_key[ref]})
                elif kind == "note":
                    expected.append({"note": rules_by_name[ref]})
                elif kind in ("fact", "procedure"):
                    expected.append({kind: self.notes[(kind, ref)]})
                else:
                    expected.append({"document": self.documents[ref]})
            question = {"query": item["query"], "scope": item["scope"], "expected": expected}
            if item.get("related_terms"):
                question["related_terms"] = item["related_terms"]
            eval_set.append(question)
        return eval_set

    def vectors(self):
        """Where the hub has texo_vector: the embedding service of the stack (http://tei:80) when
        none is set, then the vectors of what was seeded, so the measure can run at once. The texts stay
        on the machine: the service is the tei container of the compose network."""
        if not self.env["ir.module.module"].sudo().search_count([("name", "=", "texo_vector"),
                                                                 ("state", "=", "installed")]):
            return
        Params = self.env["ir.config_parameter"].sudo()
        if not Params.get_str("texo_vector.endpoint"):
            Params.set_str("texo_vector.endpoint", "http://tei:80")
        self.summary["vectors"] = self.env["memory.embedding"]._cron_embed()

    def tokens(self):
        Keys = self.env["res.users.apikeys"]
        Keys.sudo().search([("name", "=", data.TOKEN_NAME)]).unlink()
        expiry = self.now + timedelta(days=data.TOKEN_DAYS)
        member_group = _xid(self.env, "texo.group_texo_member")
        tokens = {}
        for role, user in self.users.items():
            if role == "norole":
                # only a hub user creates a hub token: lend the member role for the key, then take it back,
                # so the route sees a valid token of a user without role (403)
                user.write({"group_ids": [(4, member_group)]})
            tokens[role] = Keys.with_user(user)._generate("texo", data.TOKEN_NAME, expiry)
            if role == "norole":
                user.write({"group_ids": [(3, member_group)]})
        return tokens


def seed(env):
    """Create or realign the fictional data. Returns (summary, tokens, eval set); commits nothing."""
    if env.cr.dbname not in data.DATABASES:
        raise SystemExit(f"refusing to seed {env.cr.dbname!r}: only {', '.join(data.DATABASES)} hold fictional data")
    seeder = Seeder(env)
    seeder.people()
    seeder.industries()
    seeder.organisation()
    eval_set = []
    for customer in data.CUSTOMERS:
        seeder.customer(customer, eval_set)
    seeder.findings()
    eval_set = seeder.questions(eval_set)
    seeder.vectors()
    tokens = seeder.tokens()
    return seeder.summary, tokens, eval_set


if "env" in globals():  # inside odoo shell only
    summary, tokens, eval_set = seed(env)  # noqa: F821
    print("demo «%s»: %s" % (data.COMPANY["name"], json.dumps(summary)))
    for role, key in tokens.items():
        print(f"@@TOKEN {role} {key}")
    print("@@EVAL " + json.dumps(eval_set))
    env.cr.commit()  # noqa: F821  # fictional data, on a database the data file names
