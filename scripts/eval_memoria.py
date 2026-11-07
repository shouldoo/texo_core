#!/usr/bin/env python3
"""eval_memoria.py — measure the retrieval of the memory on a question set.

    python3 scripts/eval_memoria.py <questions.json> [--k 5]

The question set is a JSON list (or an object with a "questions" list), written by the
person who knows the project; for a real project it is kept out of git (it names notes
of real projects), for a demo customer it is the eval/ folder of its repository:

    [{"query": "when are supplier invoices registered",
      "related_terms": ["invoice", "fattura", "supplier"],
      "scope": "lessons",                 # all | notes (the rules) | facts | procedures | lessons | documents (default all);
                                          # tasks searches the episodes (title, description and chatter of the tasks)
      "class": "paraphrase",              # lexical (words of the record) | keywords (words only in its keywords)
                                          # | paraphrase (other words for the symptom); missing: the seed's own
      "applies_to": "2026",               # optional
      "expected": [{"lesson": 12}, {"note": "Segreti"}]},   # what a good answer returns: lesson, note (a rule), fact,
                                          # procedure, document, task or source (a card of the external sources,
                                          # scope sources), by id or by title (resolved on the database)
     {"task_id": 7,                      # a context pack question
      "now": 81,                          # the update that is the present of its project
      "milestone": 5,                     # the milestone of the task (optional)
      "rules": [40, 41],                  # the active rules of the chain that must bind the task
      "lessons": [12]},                   # the lessons the pack must carry (optional; [] = none)
     ...]

For every question the script calls the search of the coordination Odoo as the
person and reports hit@k (one expected id among the first k results), the mean
reciprocal rank and the questions that missed, overall and by scope and class, so a
change in the search (lexical today, semantic only if these numbers call for it) is
measured, not guessed: the paraphrase class is what better keywords cannot close. For the
pack questions it reads the context pack of the task as the person and reports
whether it carries the present of the project and the milestone of the task, and
the precision and the recall of the rules of the chain and, when the question names
them, of the lessons of the pack, with how many lessons a pack carries on average.

--format okf reads the packs as Open Knowledge Format bundles (the index, the project and
the task concepts) instead of JSON; --format both reads them both ways, reports each and
the size of a pack in the two (characters, and tokens at about four characters each), as
an agent receives them from MCP.

After the search questions a line says how the searches ran: the mean and the 95th percentile of the
latency the hub measured, and what the reranker did. The titles of the expected documents and cards are
resolved with the words only, whatever the search under measure; the rate limit of the hub waits and
retries, since a set asks more than a person does in a minute.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from texo import hub as ctx  # noqa: E402
from texo.config import ConfigError, hub_settings  # noqa: E402

KINDS = ("lesson", "note", "fact", "procedure", "document", "task", "source")
# how a title is resolved on the database: the model and the domain of search_read; a document and a card of the
# external sources by their search (the scope of each)
RESOLVE = {"lesson": ("memory.lesson", []), "note": ("memory.note", [["kind", "=", "rule"]]),
           "fact": ("memory.note", [["kind", "=", "fact"]]), "procedure": ("memory.note", [["kind", "=", "procedure"]]),
           "task": ("project.task", [])}


class Patient:
    """The hub for a measure: the rate limit of the hub (429, texo.rate_limit_per_minute) waits and retries,
    since a set of a few hundred questions asks more than a person does in a minute; any other error, or a
    limit that does not lift after the tries, stops the measure as before."""

    def __init__(self, hub, wait=10, tries=30, sleep=time.sleep):
        self.hub, self.wait, self.tries, self.sleep = hub, wait, tries, sleep

    def call(self, route, payload=None):
        for attempt in range(self.tries):
            try:
                return self.hub.call(route, payload)
            except ctx.HubError as error:
                if error.status != 429 or attempt == self.tries - 1:
                    raise
                self.sleep(self.wait)
        return None


def load_questions(path):
    with open(path, encoding="utf-8") as handle:
        loaded = json.load(handle)
    return loaded["questions"] if isinstance(loaded, dict) else loaded


def resolve(hub, questions):
    """The expected records named by title get their id on this database, in place; an unknown title raises."""
    for question in questions:
        for item in question.get("expected", []):
            for kind, value in list(item.items()):
                if kind in KINDS and isinstance(value, str):
                    item[kind] = _resolve_title(hub, kind, value)
    return questions


def _resolve_title(hub, kind, title):
    if kind in ("document", "source"):
        # by the words only: the search under measure (vectors, reranker) must not decide what is expected
        found = [r for r in hub.call("memory/search", {"query": title, "scope": kind + "s", "limit": 5,
                                                       "mode": "lexical"})["results"]
                 if r.get("title") == title]
    else:
        model, domain = RESOLVE[kind]
        found = hub.call("search_read", {"model": model, "domain": domain + [["name", "=", title]],
                                         "fields": ["id"], "limit": 2})["records"]
    if len(found) != 1:
        raise ValueError(f"{kind} {title!r}: {'not found' if not found else 'more than one'} on this database")
    return found[0]["id"]
# The sections of an OKF index that are levels of the chain: their rules bind the task.
LEVELS = ("Task:", "Project:", "Customer:", "Organisation:")


def key_of(result):
    # a note carries no flag: lessons, facts and documents do
    return (next((kind for kind in KINDS if kind != "note" and result.get(kind)), "note"), result["id"])


def expected_keys(question):
    keys = set()
    for item in question.get("expected", []):
        for kind in KINDS:
            if kind in item:
                keys.add((kind, int(item[kind])))
    return keys


def evaluate(hub, questions, k=5, mode=None, runs=None):
    """[(question, rank or None)] where rank is 1-based of the first expected hit; mode (lexical,
    semantic, hybrid) asks the hub for one mode of the search, None for the configured one. runs, a list,
    gets for each search how it ran: (latency in ms, what the reranker did), as the hub says it."""
    outcome = []
    for question in questions:
        if "task_id" in question:
            continue
        answer = ctx.op_search(hub, {"query": question["query"], "related_terms": question.get("related_terms"),
                                     "scope": question.get("scope") or "all", "applies_to": question.get("applies_to"),
                                     "limit": k, "mode": mode})
        results = answer["results"]
        if runs is not None:
            runs.append((answer.get("latency_ms"), answer.get("rerank")))
        wanted = expected_keys(question)
        rank = next((i + 1 for i, r in enumerate(results) if key_of(r) in wanted), None)
        outcome.append((question, rank))
    return outcome


def _frontmatter(text):
    """The frontmatter of an OKF concept written by the hub: one key per line, its value JSON."""
    meta = {}
    lines = text.split("\n")
    for line in lines[1:lines.index("---", 1)] if text.startswith("---") else []:
        key, _sep, value = line.partition(": ")
        meta[key] = json.loads(value)
    return meta


def okf_pack(answer):
    """What an OKF pack says: now, milestone, the rules of the levels and the lessons, from its index and concepts."""
    files = {f["path"]: f["text"] for f in answer["files"]}
    rules, lessons, section = [], [], None
    for line in files["index.md"].split("\n"):
        if line.startswith("# "):
            section = line[2:]
        elif section and section.startswith(LEVELS):
            rules += [int(i) for i in re.findall(r"\(/rules/(\d+)\.md\)", line)]
        elif section == "Lessons":
            lessons += [int(i) for i in re.findall(r"\(/lessons/(\d+)\.md\)", line)]
    project = next((_frontmatter(t) for p, t in files.items() if re.fullmatch(r"projects/\d+\.md", p)), {})
    task = next((_frontmatter(t) for p, t in files.items() if re.fullmatch(r"tasks/\d+\.md", p)), {})
    return {"now": (project.get("now") or {}).get("id"), "milestone": (task.get("milestone") or {}).get("id"),
            "rules": rules, "lessons": lessons}


def size(answer):
    """The characters of an answer as the MCP server gives it: an OKF bundle as markdown, else JSON."""
    if isinstance(answer, dict) and answer.get("format") == "okf":
        return len(ctx.render_okf(answer))
    return len(json.dumps(answer, ensure_ascii=False))


def evaluate_packs(hub, questions, fmt="json"):
    """[(question, what the pack says)] for the pack questions: now, milestone and rules; with the size of the pack."""
    outcome = []
    for question in questions:
        if "task_id" not in question:
            continue
        if fmt == "okf":
            answer = ctx.op_context(hub, {"task_id": question["task_id"], "format": "okf"})
            outcome.append((question, dict(okf_pack(answer), size=size(answer))))
            continue
        pack = ctx.op_context(hub, {"task_id": question["task_id"]})
        now = (pack.get("project") or {}).get("now") or {}
        milestone = (pack.get("task") or {}).get("milestone") or {}
        rules = [rule["id"] for level in pack.get("levels", []) for rule in level.get("rules", [])]
        lessons = [lesson["id"] for lesson in pack.get("lessons", [])]
        outcome.append((question, {"now": now.get("id"), "milestone": milestone.get("id"), "rules": rules,
                                   "lessons": lessons, "size": size(pack)}))
    return outcome


def report_sizes(by_format, out=sys.stdout):
    """The mean size of a pack in each format, and how the second compares with the first."""
    means = {}
    for fmt, outcome in by_format.items():
        means[fmt] = sum(got["size"] for _, got in outcome) / len(outcome) if outcome else 0
        out.write(f"pack size {fmt}: {means[fmt]:.0f} chars (~{means[fmt] / 4:.0f} tokens)\n")
    if len(means) == 2 and all(means.values()):
        first, second = means.values()
        out.write(f"okf / json: {second / first:.2f}\n")
    return means


def _precision_recall(pairs):
    """Precision and recall of the ids chosen over the ids wanted, summed over the packs."""
    chosen = sum(len(got) for got, _ in pairs)
    wanted = sum(len(want) for _, want in pairs)
    right = sum(len(set(got) & set(want)) for got, want in pairs)
    return (right / chosen if chosen else 1.0), (right / wanted if wanted else 1.0)


def report_packs(outcome, out=sys.stdout):
    """The present and the milestone found, precision and recall of the rules over all the packs, and of the
    lessons over the packs whose question names them."""
    now = sum(1 for q, got in outcome if got["now"] == q.get("now"))
    asked = [(q, got) for q, got in outcome if "milestone" in q]
    milestone = sum(1 for q, got in asked if got["milestone"] == q["milestone"])
    precision, recall = _precision_recall([(got["rules"], q.get("rules", [])) for q, got in outcome])
    out.write(f"packs: {len(outcome)}  now: {now}/{len(outcome)}  milestone: {milestone}/{len(asked)}"
              f"  rules precision: {precision:.2f}  recall: {recall:.2f}\n")
    with_lessons = [(q, got) for q, got in outcome if "lessons" in q]
    if with_lessons:
        l_precision, l_recall = _precision_recall([(got["lessons"], q["lessons"]) for q, got in with_lessons])
        mean = sum(len(got["lessons"]) for _, got in with_lessons) / len(with_lessons)
        out.write(f"lessons in the packs: {mean:.1f} per pack  precision: {l_precision:.2f}  recall: {l_recall:.2f}\n")
    for question, got in outcome:
        extra = sorted(set(got["rules"]) - set(question.get("rules", [])))
        missing = sorted(set(question.get("rules", [])) - set(got["rules"]))
        lessons_extra = sorted(set(got["lessons"]) - set(question.get("lessons", got["lessons"])))
        lessons_missing = sorted(set(question.get("lessons", [])) - set(got["lessons"]))
        if extra or missing or lessons_extra or lessons_missing or got["now"] != question.get("now"):
            out.write(f"MISS  task {question['task_id']}: now {got['now']} (expected {question.get('now')}), "
                      f"rules extra {extra}, missing {missing}; lessons extra {lessons_extra}, missing {lessons_missing}\n")
    return now, precision, recall


def _measure(outcome):
    total = len(outcome)
    hits = sum(1 for _, rank in outcome if rank is not None)
    mrr = sum(1 / rank for _, rank in outcome if rank is not None) / total if total else 0
    return total, hits, mrr


def report_runs(runs, out=sys.stdout):
    """How the searches ran: the mean and the 95th percentile of the latency the hub measured, and how many
    times the reranker was applied, skipped, off or unavailable (a hub before 20.0.1.3.0 says neither)."""
    latencies = sorted(ms for ms, _ in runs if ms is not None)
    states = {}
    for _, state in runs:
        if state:
            states[state] = states.get(state, 0) + 1
    if not latencies and not states:
        return None
    parts = []
    if latencies:
        p95 = latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))]
        parts.append(f"latency: mean {sum(latencies) / len(latencies):.0f} ms  p95 {p95} ms")
    if states:
        parts.append("rerank: " + ", ".join(f"{state} {count}" for state, count in sorted(states.items())))
    out.write("  ".join(parts) + "\n")
    return latencies, states


def report(outcome, k, out=sys.stdout):
    """The overall numbers, then one line per scope and class when the set has classes, then the misses with
    their scope and class."""
    total, hits, mrr = _measure(outcome)
    out.write(f"questions: {total}  hit@{k}: {hits}/{total}  mrr: {mrr:.2f}\n")
    if any(q.get("class") for q, _ in outcome):
        groups = {}
        for question, rank in outcome:
            groups.setdefault(((question.get("scope") or "all"), question.get("class") or "seed"), []).append((question, rank))
        for (scope, cls), group in sorted(groups.items()):
            g_total, g_hits, g_mrr = _measure(group)
            out.write(f"  {scope}/{cls}: {g_total}  hit@{k}: {g_hits}/{g_total}  mrr: {g_mrr:.2f}\n")
    for question, rank in outcome:
        if rank is None:
            label = f"[{question.get('scope') or 'all'}/{question.get('class') or 'seed'}]  " if question.get("class") else ""
            out.write(f"MISS  {label}{question['query']}\n")
    return hits, mrr


def main(argv=None, out=sys.stdout, err=sys.stderr):
    parser = argparse.ArgumentParser(description="Evaluate the retrieval of the memory on a question set.")
    parser.add_argument("questions", help="JSON file with the questions and the expected ids or titles")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--format", choices=("json", "okf", "both"), default="json",
                        help="how the packs are read: JSON, OKF bundles, or both with their sizes")
    parser.add_argument("--mode", choices=ctx.MODES,
                        help="one mode of the search (where the hub has texo_vector); none, the configured one")
    args = parser.parse_args(argv)
    try:
        questions = load_questions(args.questions)
        hub = Patient(ctx.Hub(*hub_settings()))
        resolve(hub, questions)
        if any("task_id" not in q for q in questions):
            if args.mode:
                out.write(f"-- search mode {args.mode}\n")
            runs = []
            report(evaluate(hub, questions, args.k, args.mode, runs), args.k, out)
            report_runs(runs, out)
        if any("task_id" in q for q in questions):
            formats = ("json", "okf") if args.format == "both" else (args.format,)
            by_format = {}
            for fmt in formats:
                out.write(f"-- packs as {fmt}\n")
                by_format[fmt] = evaluate_packs(hub, questions, fmt)
                report_packs(by_format[fmt], out)
            report_sizes(by_format, out)
    except (OSError, ValueError, ConfigError, ctx.HubError) as error:
        err.write(f"error: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
