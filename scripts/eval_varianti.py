#!/usr/bin/env python3
"""eval_varianti.py — measure the search of a database of the local coordination stack in its modes, on one
or more question sets, from inside odoo shell (no token, no HTTP: the ORM as the person).

    python3 scripts/eval_varianti.py <database> <questions.json> [<questions.json> ...]
        --user <login> [--k 5] [--modes lexical,hybrid] [--out result.json]
        [--expand glossary.json] [--scope documents|sources] [--cards cards.json]
        [--rerank <url> [--rerank-api tei|llamacpp] [--rerank-task description|chatter] [--pool 10] [--chars 800]]

A question set is the format of scripts/eval_memoria.py with the expected records named by title (or id):
{"query", "scope", "class", "expected": [{"task": "<title>"}, {"fact": "<title>"}, ...], "related_terms"?}.
For every set and mode it prints hit@k and mrr overall and per scope/class, the questions that missed, and
for the modes after the first the hits won and lost against the first (a lost hit of every word is a
regression, a lost partial hit a trade-off: playbooks/valutazione-memoria.md). --out writes the ranks per
question, so two runs (for example a raw and a curated layer of the same documents) can be compared.

--expand takes a glossary, a JSON list of groups of equivalent terms ([["SAL", "stato di avanzamento lavori",
"acconto"], ...]): when a term of a group is in the question, the other terms of the group are passed as
related_terms, as an agent that reads the glossary of the organisation before searching would do.

A question may name the passage that answers ("passage": a substring of its path, e.g. "Art. 41 > comma 4"):
the report then also counts the questions whose document was found with that passage.

The cards of the external sources (texo_sources): an expected {"source": "<title>"} names a card; an expected
{"card": "<key>"} names a clipping by its key in a cards file (--cards, a JSON {"cards": [{"key", "url",
"document"}]}) and is found either as its card (by link) or as the document it came from, so the same set
measures the documents (--scope documents) and the cards (--scope sources). Mode `filters` is the agent that
filters: a question with "filters" ({"query", "persons", "themes", "channel", "date_from", "date_to"}) is asked
to sources_find (the active cards, newest event first), the others to the hybrid search. A question with
"all": true asks for a list: the report adds how many of its expected records are in the first k (recall); "k"
on a question overrides --k for it.

The script pipes itself into `odoo shell` of the coordination stack ($TEXO_STACK, default
~/.local/share/texo/coordinamento: setup/coordinamento-up.sh); inside, it runs on `env`. It reads, it never
writes: the database is the one the person named, never a production one.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

KINDS = {"task": ("project.task", None), "fact": ("memory.note", "fact"), "procedure": ("memory.note", "procedure"),
         "note": ("memory.note", "rule"), "lesson": ("memory.lesson", None), "document": ("ir.attachment", None)}


def expected_units(env, question, cards=None):
    """One set of result keys per expected record: (True, id) for a card of the external sources, (False, id) for
    any other record (as before the cards, ids of different models are not told apart)."""
    units = []
    for item in question["expected"]:
        (kind, value), = item.items()
        if isinstance(value, int):
            units.append({(False, value)})
            continue
        if kind == "card":
            card = (cards or {}).get(value)
            if not card:
                raise SystemExit(f"card {value!r} is not in the cards file (--cards)")
            unit = set()
            if "memory.source.item" in env:
                unit |= {(True, i) for i in env["memory.source.item"].sudo().with_context(active_test=False).search(
                    [("url", "=", card["url"])]).ids}
            unit |= {(False, i) for i in env["ir.attachment"].sudo().search(
                [("name", "=", card["document"]), ("texo_document", "=", True)]).ids}
            if not unit:
                print(f"   [warn] expected card not on the database: {value!r}")
            units.append(unit)
            continue
        if kind == "source":
            found = env["memory.source.item"].sudo().with_context(active_test=False).search([("title", "=", value)])
            if not found:
                print(f"   [warn] expected source not on the database: {value!r}")
            units.append({(True, i) for i in found.ids})
            continue
        model, note_kind = KINDS[kind]
        domain = [("name", "=", value)] + ([("kind", "=", note_kind)] if note_kind else [])
        if model == "ir.attachment":
            domain.append(("texo_document", "=", True))
        found = env[model].sudo().with_context(active_test=False).search(domain)
        if not found:
            print(f"   [warn] expected {kind} not on the database: {value!r}")
        units.append({(False, i) for i in found.ids})
    return units


def result_key(entry):
    return bool(entry.get("source")), entry["id"]


def expand(query, glossary):
    """The other terms of every group of the glossary that has a term in the query (whole words, any case)."""
    import re
    text = " " + re.sub(r"[^\w]+", " ", query.lower()) + " "
    extra = []
    for group in glossary or []:
        if any(" " + re.sub(r"[^\w]+", " ", term.lower()).strip() + " " in text for term in group):
            extra += [term for term in group if " " + re.sub(r"[^\w]+", " ", term.lower()).strip() + " " not in text]
    return list(dict.fromkeys(extra))


def candidate_text(env, entry, size=2000):
    """What the reranker reads of a result: the title and the text of its record (a document: the passage that
    answered, else its summary)."""
    if entry.get("lesson"):
        record = env["memory.lesson"].sudo().browse(entry["id"])
        text = f"{record.finding}\n{record.solution}"
    elif entry.get("task"):
        from odoo.tools import html2plaintext
        text = html2plaintext(env["project.task"].sudo().browse(entry["id"]).description or "")
        if (globals().get("ARGS") or {}).get("rerank_task") == "chatter":
            # the human messages of the chatter too, newest first: the description of a task is often a
            # line, and what it answers is in the chatter (the episode the vectors index, one per message)
            messages = env["mail.message"].sudo().search_fetch(
                [("model", "=", "project.task"), ("res_id", "=", entry["id"]),
                 ("message_type", "in", ("comment", "email", "email_outgoing"))], ["body"], order="id desc")
            text = "\n".join([text, *(html2plaintext(message.body or "") for message in messages)])
    elif entry.get("document"):
        passage = entry.get("passage") or {}
        found = env["memory.document.passage"].sudo().search(
            [("attachment_id", "=", entry["id"]), ("start", "=", passage.get("start"))], limit=1) if passage else None
        text = f"{passage.get('path') or ''}\n{found.text}" if found else (entry.get("summary") or entry.get("snippet") or "")
    elif entry.get("source"):
        # a card of the external sources: its id is a card's, never a note's (as the hub's _rerank_text)
        card = env["memory.source.item"].sudo().browse(entry["id"]).exists()
        text = "\n".join(filter(None, [card.abstract, card.acts])) if card else (entry.get("snippet") or "")
    elif entry.get("fact") or entry.get("procedure") or entry.get("kind") in ("fact", "procedure", "rule"):
        text = env["memory.note"].sudo().browse(entry["id"]).body or ""
    else:
        text = entry.get("snippet") or entry.get("summary") or ""
    return f"{entry.get('title') or ''}\n{' '.join(text.split())}"[:size]


def rerank(env, query, results, url, timings):
    """The results in the order of a cross-encoder reading question and text: Text Embeddings Inference (POST
    /rerank) or llama.cpp server started with --reranking (POST /v1/rerank), as rerank_api of the hub."""
    import time

    import requests
    if not results:
        return results
    args = globals().get("ARGS") or {}
    size = args.get("chars") or 2000
    texts = [candidate_text(env, entry, size) for entry in results]
    started = time.monotonic()
    if args.get("rerank_api") == "llamacpp":
        answer = requests.post(f"{url}/v1/rerank", json={"query": query, "documents": texts, "top_n": len(texts)},
                               timeout=60)
        answer.raise_for_status()
        scores = [(item["index"], item["relevance_score"]) for item in answer.json()["results"]]
    else:
        answer = requests.post(f"{url}/rerank", json={"query": query, "texts": texts, "truncate": True}, timeout=60)
        answer.raise_for_status()
        scores = [(item["index"], item["score"]) for item in answer.json()]
    timings.append(time.monotonic() - started)
    return [results[index] for index, _score in sorted(scores, key=lambda item: -item[1])]


def run(env, user, questions, mode, k, glossary=None, rerank_url=None, pool=20, timings=None, scope=None,
        cards=None):
    Note = env["memory.note"].with_user(user)
    out = []
    for question in questions:
        if "task_id" in question:
            continue  # a context pack question: scripts/eval_memoria.py
        related = list(question.get("related_terms") or []) + expand(question["query"], glossary)
        where = scope or question.get("scope") or "all"
        size = question.get("k") or k
        if rerank_url:
            # the first pool of the hybrid, reordered by the reranker, then cut to k
            results = Note._agent_search(question["query"], related_terms=related or None,
                                         scope=where, limit=pool, mode="hybrid")
            results = rerank(env, question["query"], results, rerank_url, timings)[:size]
        elif mode == "filters" and question.get("filters"):
            # the agent that reads the dates, the persons and the channel of the question: sources_find
            found = env["memory.source.item"].with_user(user)._agent_find(states=["active"], limit=size,
                                                                          **question["filters"])
            results = [dict(entry, source=True) for entry in found]
        else:
            results = Note._agent_search(question["query"], related_terms=related or None,
                                         scope=where, limit=size, mode="hybrid" if mode == "filters" else mode)
        units = expected_units(env, question, cards)
        keys = [result_key(r) for r in results]
        rank = next((i + 1 for i, key in enumerate(keys) if any(key in unit for unit in units)), None)
        words = next((r.get("words") for r, key in zip(results, keys) if any(key in unit for unit in units)), None)
        entry = {"query": question["query"], "scope": where,
                 "class": question.get("class", "seed"), "rank": rank, "words": words}
        if question.get("all"):
            entry["recall"] = [sum(1 for unit in units if unit & set(keys)), len(units)]
        if question.get("passage"):
            # the document found, and with it the passage that answers (a substring of its path)
            hit = next((r for r, key in zip(results, keys) if any(key in unit for unit in units)), {})
            path = (hit.get("passage") or {}).get("path") or ""
            paths = [p.get("path") or "" for p in hit.get("passages") or []]
            entry.update(passage=bool(rank) and question["passage"] in path, path=path,
                         passage3=bool(rank) and any(question["passage"] in p for p in paths))
        out.append(entry)
    return out


def report(label, outcome, reference=None):
    hits = sum(1 for o in outcome if o["rank"])
    mrr = sum(1 / o["rank"] for o in outcome if o["rank"]) / max(len(outcome), 1)
    print(f"{label}: {hits}/{len(outcome)} mrr {mrr:.2f}")
    with_passage = [o for o in outcome if "passage" in o]
    if with_passage:
        print(f"   passage: {sum(1 for o in with_passage if o['passage'])}/{len(with_passage)} first, "
              f"{sum(1 for o in with_passage if o.get('passage3'))}/{len(with_passage)} among those named "
              "(the document in the first k, and the passage that answers named with it)")
    groups = {}
    for o in outcome:
        groups.setdefault((o["scope"], o["class"]), []).append(o["rank"])
    for (scope, cls), ranks in sorted(groups.items()):
        found = sum(1 for r in ranks if r)
        print(f"   {scope}/{cls}: {found}/{len(ranks)} ({sum(1 / r for r in ranks if r) / len(ranks):.2f})")
    lists = [o for o in outcome if "recall" in o]
    if lists:
        found, wanted = sum(o["recall"][0] for o in lists), sum(o["recall"][1] for o in lists)
        complete = sum(1 for o in lists if o["recall"][0] == o["recall"][1])
        print(f"   lists: {found}/{wanted} expected records found, {complete}/{len(lists)} lists complete")
        for o in lists:
            if o["recall"][0] < o["recall"][1]:
                print(f"   PARTIAL {o['recall'][0]}/{o['recall'][1]} [{o['scope']}/{o['class']}] {o['query']}")
    for o in outcome:
        if not o["rank"]:
            print(f"   MISS [{o['scope']}/{o['class']}] {o['query']}")
    if reference:
        for o, r in zip(outcome, reference, strict=True):
            if o["rank"] and not r["rank"]:
                print(f"   + [{o['scope']}/{o['class']}] {o['query']}")
            elif r["rank"] and not o["rank"]:
                kind = "REGRESSION (every word)" if r["words"] == "all" else "trade-off (some words)"
                print(f"   - {kind} [{o['scope']}/{o['class']}] {o['query']}")


def shell_main(env, args):
    user = env["res.users"].search([("login", "=", args["user"])], limit=1)
    if not user:
        raise SystemExit(f"no user {args['user']!r} on {env.cr.dbname}")
    params = env["ir.config_parameter"].sudo()
    if params.get_str("texo_vector.rerank_endpoint"):
        # the hub reorders its hybrid search itself when a reranker is configured: the modes measure the search
        # without it, --rerank measures it with one (the change is rolled back with the rest of the measure)
        params.set_str("texo_vector.rerank_endpoint", "")
        print("   the reranker of the database is off for this measure")
    result = {}
    for name, questions in args["sets"].items():
        first = None
        for mode in args["modes"]:
            outcome = run(env, user, questions, mode, args["k"], args.get("glossary"), scope=args.get("scope"),
                          cards=args.get("cards"))
            report(f"== {name} {mode}", outcome, first)
            first = first or outcome
            result[f"{name}:{mode}"] = outcome
        if args.get("rerank"):
            timings = []
            outcome = run(env, user, questions, "rerank", args["k"], args.get("glossary"), args["rerank"],
                          args.get("pool", 20), timings, scope=args.get("scope"), cards=args.get("cards"))
            report(f"== {name} hybrid+rerank (pool {args.get('pool', 20)}, {args.get('chars', 2000)} chars)", outcome, first)
            if timings:
                timings.sort()
                print(f"   rerank time: median {timings[len(timings) // 2]:.2f}s, max {timings[-1]:.2f}s")
            result[f"{name}:rerank"] = outcome
    print("@@RESULT " + json.dumps(result))
    env.cr.rollback()  # the measure writes nothing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("database")
    parser.add_argument("questions", nargs="+")
    parser.add_argument("--user", required=True, help="the login of the person the questions are asked as")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--modes", default="lexical,hybrid", help="lexical, hybrid, filters (comma-separated)")
    parser.add_argument("--scope", help="ask every question in this scope (e.g. documents, sources)")
    parser.add_argument("--cards", help="the cards file that resolves the expected {\"card\": key}")
    parser.add_argument("--out")
    parser.add_argument("--expand", help="a glossary: JSON list of groups of equivalent terms")
    parser.add_argument("--rerank", help="URL of a reranker seen from the web container, e.g. http://tei-rerank:80 "
                                         "or http://192.168.1.53:8012: also measures the hybrid reordered by it")
    parser.add_argument("--rerank-api", choices=("tei", "llamacpp"), default="tei",
                        help="the API of the reranker, as rerank_api of the hub: tei (POST /rerank) or llamacpp "
                             "(llama.cpp server with --reranking, POST /v1/rerank)")
    parser.add_argument("--rerank-task", choices=("description", "chatter"), default="description",
                        help="what the reranker reads of a task: its description (as the hub does today) or the "
                             "description and the human messages of its chatter, newest first")
    parser.add_argument("--pool", type=int, default=20, help="how many results of the hybrid the reranker reorders")
    parser.add_argument("--chars", type=int, default=2000, help="characters of each result the reranker reads")
    options = parser.parse_args(argv)
    sets = {}
    for path in options.questions:
        loaded = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        sets[pathlib.Path(path).stem] = loaded["questions"] if isinstance(loaded, dict) else loaded
    args = {"user": options.user, "k": options.k, "modes": options.modes.split(","), "sets": sets,
            "rerank": options.rerank, "rerank_api": options.rerank_api, "rerank_task": options.rerank_task, "pool": options.pool, "chars": options.chars, "scope": options.scope,
            "cards": {card["key"]: {"url": card["url"], "document": card["document"]} for card in json.loads(
                pathlib.Path(options.cards).read_text(encoding="utf-8"))["cards"]} if options.cards else None,
            "glossary": json.loads(pathlib.Path(options.expand).read_text(encoding="utf-8")) if options.expand else None}
    stack = pathlib.Path(os.environ.get("TEXO_STACK", "~/.local/share/texo/coordinamento")).expanduser() / "docker-compose.yml"
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    program = f"ARGS = {args!r}\n{source}\n"
    command = ["docker", "compose", "-f", str(stack), "exec", "-T", "web", "odoo", "shell", "-c", "/etc/odoo/odoo.conf",
               "-d", options.database, "--no-http", "--log-level=warn"]
    done = subprocess.run(command, input=program, capture_output=True, text=True, check=False)
    result = None
    for line in done.stdout.splitlines():
        if line.startswith("@@RESULT "):
            result = json.loads(line[len("@@RESULT "):])
        elif line.strip():
            print(line)
    if result is None:
        sys.stderr.write(done.stderr[-3000:])
        return 1
    if options.out:
        pathlib.Path(options.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if "env" in globals() and "ARGS" in globals():  # inside odoo shell
    shell_main(env, ARGS)  # noqa: F821
elif __name__ == "__main__":
    sys.exit(main())
