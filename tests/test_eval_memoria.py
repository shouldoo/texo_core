"""Tests without a real Odoo of scripts/eval_memoria.py."""
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import eval_memoria as ev  # noqa: E402


class FakeHub:
    def __init__(self):
        self.payloads = []

    def call(self, route, payload):
        assert route == "memory/search"
        self.payloads.append(payload)
        if payload["scope"] == "tasks":
            return {"results": [{"id": 131, "task": True, "title": "Componente non scaricato"}]}
        if payload["scope"] == "sources":
            return {"results": [{"id": 9, "source": True, "title": "Terni, crisi in Comune", "state": "active"},
                                {"id": 10, "source": True, "title": "Terni, crisi in Comune", "state": "active"}]}
        if "uom" in payload["query"]:
            return {"results": [{"id": 40, "state": "active", "kind": "context"}, {"id": 12, "lesson": True, "state": "active"}]}
        if "procedura" in payload["query"]:
            return {"results": [{"id": 7, "procedure": True, "state": "active"}]}
        return {"results": [{"id": 1, "lesson": True, "state": "active"}]}


QUESTIONS = [
    {"query": "uom field", "expected": [{"lesson": 12}]},
    {"query": "uom field again", "expected": [{"note": 40}]},
    {"query": "nothing known", "expected": [{"note": 99}]},
]


class EvalMemoriaTest(unittest.TestCase):
    def test_ranks_hits_and_reports_misses(self):
        outcome = ev.evaluate(FakeHub(), QUESTIONS, k=5)
        self.assertEqual([rank for _, rank in outcome], [2, 1, None])
        out = io.StringIO()
        hits, mrr = ev.report(outcome, 5, out)
        self.assertEqual(hits, 2)
        self.assertAlmostEqual(mrr, (0.5 + 1) / 3)
        self.assertIn("hit@5: 2/3", out.getvalue())
        self.assertIn("MISS  nothing known", out.getvalue())
        self.assertNotIn("/", out.getvalue().splitlines()[1], "no classes, no lines by scope and class")

    def test_the_mode_of_the_search_reaches_the_hub_only_when_asked(self):
        hub = FakeHub()
        ev.evaluate(hub, QUESTIONS[:1], k=5)
        self.assertNotIn("mode", hub.payloads[-1], "none: the configured mode of the hub")
        ev.evaluate(hub, QUESTIONS[:1], k=5, mode="semantic")
        self.assertEqual(hub.payloads[-1]["mode"], "semantic")

    def test_reports_by_scope_and_class(self):
        questions = [
            {"query": "uom field", "scope": "lessons", "class": "lexical", "expected": [{"lesson": 12}]},
            {"query": "nothing known", "scope": "lessons", "class": "paraphrase", "expected": [{"lesson": 99}]},
            {"query": "procedura di rilascio", "scope": "procedures", "class": "keywords", "expected": [{"procedure": 7}]},
            {"query": "il pezzo resta a stock", "scope": "tasks", "class": "paraphrase", "expected": [{"task": 131}]},
            {"query": "crisi", "scope": "sources", "class": "temporale", "expected": [{"source": 10}, {"note": 9}]},
        ]
        outcome = ev.evaluate(FakeHub(), questions, k=5)
        self.assertEqual([rank for _, rank in outcome], [2, None, 1, 1, 2], "a card is a source, never a note")
        questions.pop()
        outcome.pop()
        out = io.StringIO()
        hits, mrr = ev.report(outcome, 5, out)
        text = out.getvalue()
        self.assertEqual(hits, 3, "the episodes are a scope like the others")
        self.assertAlmostEqual(mrr, (0.5 + 1 + 1) / 4)
        self.assertIn("questions: 4  hit@5: 3/4  mrr: 0.62", text)
        self.assertIn("  lessons/lexical: 1  hit@5: 1/1  mrr: 0.50", text)
        self.assertIn("  lessons/paraphrase: 1  hit@5: 0/1  mrr: 0.00", text)
        self.assertIn("  procedures/keywords: 1  hit@5: 1/1  mrr: 1.00", text)
        self.assertIn("  tasks/paraphrase: 1  hit@5: 1/1  mrr: 1.00", text)
        self.assertIn("MISS  [lessons/paraphrase]  nothing known", text)
        self.assertNotIn("il pezzo resta a stock", text)


class ResolveHub:
    def call(self, route, payload):
        if route == "memory/search":
            if payload["scope"] == "sources":
                return {"results": [{"id": 21, "title": "Terni, crisi in Comune", "source": True}]}
            assert payload["scope"] == "documents"
            return {"results": [{"id": 9, "title": "Annex (sintesi)", "document": True}, {"id": 10, "title": "Altro"}]}
        assert route == "search_read"
        if payload["model"] == "memory.lesson":
            return {"records": [{"id": 12}]}
        if payload["model"] == "memory.note" and ["kind", "=", "rule"] in payload["domain"]:
            return {"records": [{"id": 40}]}
        if payload["model"] == "project.task":
            return {"records": [{"id": 131}]}
        return {"records": []}


class ResolveTest(unittest.TestCase):
    def test_titles_become_ids_in_place(self):
        questions = [{"query": "x", "expected": [{"lesson": "Odoo 18: una lezione"}, {"note": "Segreti"}, {"note": 41}]},
                     {"query": "y", "scope": "documents", "expected": [{"document": "Annex (sintesi)"}]},
                     {"query": "z", "scope": "tasks", "expected": [{"task": "Un ticket"}]}]
        ev.resolve(ResolveHub(), questions)
        self.assertEqual(questions[0]["expected"], [{"lesson": 12}, {"note": 40}, {"note": 41}])
        self.assertEqual(questions[1]["expected"], [{"document": 9}])
        self.assertEqual(questions[2]["expected"], [{"task": 131}])
        cards = [{"query": "v", "scope": "sources", "expected": [{"source": "Terni, crisi in Comune"}]}]
        ev.resolve(ResolveHub(), cards)
        self.assertEqual(cards[0]["expected"], [{"source": 21}], "a card of the external sources, by its title")
        with self.assertRaises(ValueError):
            ev.resolve(ResolveHub(), [{"query": "w", "expected": [{"fact": "Nessun fatto"}]}])

    def test_a_set_may_be_an_object_with_questions(self):
        import json
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"_comment": "x", "questions": [{"query": "q", "expected": []}]}, handle)
        self.assertEqual(ev.load_questions(handle.name), [{"query": "q", "expected": []}])


class FakePackHub:
    def call(self, route, payload):
        assert route == "memory/context"
        return {7: {"project": {"now": {"id": 81}}, "task": {"milestone": {"id": 5}},
                    "levels": [{"rules": []}, {"rules": [{"id": 40}, {"id": 42}]}, {"skipped": "not readable"}],
                    "lessons": [{"id": 12}, {"id": 13}]},
                8: {"project": {"now": None}, "task": {"milestone": None}, "levels": [{"rules": [{"id": 41}]}]}}[payload["task_id"]]


class EvalPacksTest(unittest.TestCase):
    def test_now_milestone_and_rules(self):
        questions = [{"query": "x", "expected": []},
                     {"task_id": 7, "now": 81, "milestone": 5, "rules": [40], "lessons": [12]},
                     {"task_id": 8, "now": 90, "rules": [41, 50]}]
        outcome = ev.evaluate_packs(FakePackHub(), questions)
        self.assertTrue(all(got.pop("size") > 0 for _, got in outcome))
        self.assertEqual([got for _, got in outcome], [{"now": 81, "milestone": 5, "rules": [40, 42], "lessons": [12, 13]},
                                                       {"now": None, "milestone": None, "rules": [41], "lessons": []}])
        out = io.StringIO()
        now, precision, recall = ev.report_packs(outcome, out)
        self.assertEqual(now, 1)
        self.assertAlmostEqual(precision, 2 / 3)
        self.assertAlmostEqual(recall, 2 / 3)
        self.assertIn("packs: 2  now: 1/2  milestone: 1/1", out.getvalue())
        self.assertIn("lessons in the packs: 2.0 per pack  precision: 0.50  recall: 1.00", out.getvalue())
        self.assertIn("MISS  task 7: now 81 (expected 81), rules extra [42], missing []; lessons extra [13], missing []",
                      out.getvalue())
        self.assertIn("MISS  task 8: now None (expected 90), rules extra [], missing [50]; lessons extra [], missing []",
                      out.getvalue())

    def test_an_okf_pack_says_the_same_and_has_a_size(self):
        index = ("---\nokf_version: \"0.2\"\n---\n\n# Work\n\n* [T](/tasks/7.md) - Task\n\n"
                 "# Project: Alfa\n\n* [R](/rules/40.md) - Rule, must: x\n* [F](/facts/2.md) - Fact: y\n\n"
                 "# Lessons\n\n* [L](/lessons/12.md) - Finding: orm\n\n"
                 "# Pending review\n\n* [D](/rules/99.md) - draft rule by Bob\n")
        answer = {"format": "okf", "files": [
            {"path": "index.md", "text": index},
            {"path": "tasks/7.md", "text": '---\ntype: "Task"\nmilestone: {"id": 5, "name": "Go live"}\n---\n'},
            {"path": "projects/2.md", "text": '---\ntype: "Project"\nnow: {"id": 81, "date": "2026-10-21"}\n---\n\n# Now\n'}]}

        class OkfHub:
            def call(self, route, payload):
                assert payload["format"] == "okf"
                return answer

        [(_, got)] = ev.evaluate_packs(OkfHub(), [{"task_id": 7, "now": 81, "rules": [40]}], "okf")
        self.assertEqual((got["now"], got["milestone"], got["rules"], got["lessons"]), (81, 5, [40], [12]),
                         "a draft waiting for review does not bind")
        out = io.StringIO()
        means = ev.report_sizes({"json": [(None, {"size": 100})], "okf": [(None, {"size": 150})]}, out)
        self.assertEqual(means, {"json": 100, "okf": 150})
        self.assertIn("okf / json: 1.50", out.getvalue())

    def test_search_questions_skip_the_packs(self):
        self.assertEqual(ev.evaluate(FakeHub(), [{"task_id": 7, "rules": []}]), [])


if __name__ == "__main__":
    unittest.main()
