"""Tests without a real Odoo of scripts/eval_varianti.py (python -m unittest discover -s scripts/tests)."""
import contextlib
import io
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import eval_varianti  # noqa: E402


def outcome(rank, words=None, query="q"):
    return {"query": query, "scope": "facts", "class": "paraphrase", "rank": rank, "words": words}


class TestReport(unittest.TestCase):

    def printed(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            eval_varianti.report(*args)
        return out.getvalue()

    def test_hits_mrr_and_misses(self):
        text = self.printed("== set lexical", [outcome(1), outcome(2), outcome(None, query="lost one")])
        self.assertIn("2/3 mrr 0.50", text)
        self.assertIn("facts/paraphrase: 2/3", text)
        self.assertIn("MISS [facts/paraphrase] lost one", text)

    def test_a_lost_hit_of_every_word_is_a_regression_a_partial_one_a_trade_off(self):
        reference = [outcome(1, "all", "a"), outcome(3, "some", "b"), outcome(None, query="c")]
        text = self.printed("== set hybrid", [outcome(None, query="a"), outcome(None, query="b"), outcome(2, query="c")],
                            reference)
        self.assertIn("- REGRESSION (every word) [facts/paraphrase] a", text)
        self.assertIn("- trade-off (some words) [facts/paraphrase] b", text)
        self.assertIn("+ [facts/paraphrase] c", text)


class FakeRecords:
    def __init__(self, ids):
        self.ids = ids


class FakeModel:
    """A model of a fake env: search answers from a table {(field, value): ids}; the search methods of the agent
    answer what the test gave and remember how they were called."""

    def __init__(self, table=None, search=None, find=None):
        self.table, self.searched, self.found, self.calls = table or {}, search or [], find or [], []

    def sudo(self):
        return self

    def with_context(self, **_kw):
        return self

    def with_user(self, _user):
        return self

    def search(self, domain):
        field, _op, value = domain[0]
        return FakeRecords(self.table.get((field, value), []))

    def _agent_search(self, query, **kw):
        self.calls.append(("search", query, kw))
        return self.searched[:kw["limit"]]

    def _agent_find(self, **kw):
        self.calls.append(("find", kw))
        return self.found[:kw["limit"]]


class TestCards(unittest.TestCase):
    CARDS = {"a": {"url": "https://x.example/a", "document": "Doc A"},
             "b": {"url": "https://x.example/b", "document": "Doc B"}}

    def env(self, searched=(), found=()):
        return {"memory.note": FakeModel(search=list(searched)),
                "memory.source.item": FakeModel({("url", "https://x.example/a"): [7], ("url", "https://x.example/b"): [8]},
                                                find=list(found)),
                "ir.attachment": FakeModel({("name", "Doc A"): [7], ("name", "Doc B"): [30]})}

    def test_a_card_is_found_as_its_card_or_as_its_document_never_by_an_id_of_another_model(self):
        units = eval_varianti.expected_units(self.env(), {"expected": [{"card": "a"}]}, self.CARDS)
        self.assertEqual(units, [{(True, 7), (False, 7)}])
        self.assertEqual(eval_varianti.result_key({"id": 7, "source": True}), (True, 7))
        self.assertEqual(eval_varianti.result_key({"id": 7, "document": True}), (False, 7))

    def test_a_list_counts_the_expected_records_in_the_first_k(self):
        env = self.env(searched=[{"id": 30, "document": True}, {"id": 5}])
        question = {"query": "q", "scope": "sources", "class": "temporale", "all": True,
                    "expected": [{"card": "a"}, {"card": "b"}]}
        out, = eval_varianti.run(env, None, [question], "lexical", 5, scope="documents", cards=self.CARDS)
        self.assertEqual((out["rank"], out["recall"], out["scope"]), (1, [1, 2], "documents"))
        self.assertEqual(env["memory.note"].calls[0][2]["scope"], "documents")

    def test_filters_ask_sources_find_and_the_other_questions_the_hybrid(self):
        env = self.env(searched=[{"id": 8, "source": True}], found=[{"id": 9}, {"id": 8}])
        with_filters = {"query": "q", "class": "temporale", "expected": [{"card": "b"}], "k": 10,
                        "filters": {"date_from": "2026-10-27"}}
        without = {"query": "r", "class": "temporale", "expected": [{"card": "b"}]}
        first, second = eval_varianti.run(env, None, [with_filters, without], "filters", 5, cards=self.CARDS)
        self.assertEqual((first["rank"], second["rank"]), (2, 1))
        self.assertEqual(env["memory.source.item"].calls,
                         [("find", {"states": ["active"], "limit": 10, "date_from": "2026-10-27"})])
        self.assertEqual(env["memory.note"].calls[0][2]["mode"], "hybrid")

    def test_the_report_of_the_lists(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            eval_varianti.report("== set filters", [dict(outcome(1, query="full"), recall=[2, 2]),
                                                    dict(outcome(2, query="half"), recall=[1, 2])])
        self.assertIn("lists: 3/4 expected records found, 1/2 lists complete", out.getvalue())
        self.assertIn("PARTIAL 1/2 [facts/paraphrase] half", out.getvalue())


class TestExpand(unittest.TestCase):

    def test_the_other_terms_of_a_group_found_in_the_question(self):
        glossary = [["SAL", "stato di avanzamento lavori", "acconto"], ["APE", "certificato energetico"]]
        self.assertEqual(eval_varianti.expand("Quando arriva il prossimo acconto?", glossary),
                         ["SAL", "stato di avanzamento lavori"])
        self.assertEqual(eval_varianti.expand("serve l'APE?", glossary), ["certificato energetico"])
        self.assertEqual(eval_varianti.expand("la salita del cantiere", glossary), [], "whole words only")
        self.assertEqual(eval_varianti.expand("nulla", None), [])


if __name__ == "__main__":
    unittest.main()


class TestCandidateText(unittest.TestCase):
    """What the reranker of the measure reads of a result: a source card from its own record."""

    def test_a_source_card_is_read_as_a_card_not_as_a_note_with_its_id(self):
        card = mock.Mock(abstract="Il Tar annulla la determina.", acts="Sentenza del 24 marzo")
        cards = mock.Mock(**{"sudo.return_value.browse.return_value.exists.return_value": card})
        notes = mock.Mock(**{"sudo.return_value.browse.return_value.body": "a note with the same id"})
        env = {"memory.source.item": cards, "memory.note": notes}
        text = eval_varianti.candidate_text(env, {"id": 20, "source": True, "title": "Stadio-clinica"})
        self.assertEqual(text, "Stadio-clinica\nIl Tar annulla la determina. Sentenza del 24 marzo")
        self.assertIn("a note", eval_varianti.candidate_text(env, {"id": 20, "fact": True, "title": ""}))


class TestRerank(unittest.TestCase):
    """The order of the reranker, from the answer of Text Embeddings Inference or of llama.cpp."""

    def rerank(self, api, payload):
        answer = mock.Mock(**{"json.return_value": payload})
        results = [{"id": 1}, {"id": 2}, {"id": 3}]
        # a fake requests: rerank imports it when it runs (inside odoo shell), the CI does not install it
        requests = mock.Mock(**{"post.return_value": answer})
        with mock.patch.dict(eval_varianti.__dict__, ARGS={"rerank_api": api, "chars": 800}), \
                mock.patch.object(eval_varianti, "candidate_text", lambda env, entry, size: f"text {entry['id']}"), \
                mock.patch.dict(sys.modules, requests=requests):
            order = eval_varianti.rerank(None, "q", results, "http://host:1", [])
        return [entry["id"] for entry in order], requests.post.call_args

    def test_tei(self):
        order, call = self.rerank("tei", [{"index": 2, "score": 0.9}, {"index": 0, "score": 0.5}, {"index": 1, "score": 0.1}])
        self.assertEqual(order, [3, 1, 2])
        self.assertEqual(call.args[0], "http://host:1/rerank")
        self.assertEqual(call.kwargs["json"]["texts"], ["text 1", "text 2", "text 3"])

    def test_llamacpp(self):
        order, call = self.rerank("llamacpp", {"results": [{"index": 0, "relevance_score": -3.0},
                                                         {"index": 1, "relevance_score": 1.5},
                                                         {"index": 2, "relevance_score": -0.2}]})
        self.assertEqual(order, [2, 3, 1], "the results of llama.cpp come in the order of the texts")
        self.assertEqual(call.args[0], "http://host:1/v1/rerank")
        self.assertEqual(call.kwargs["json"], {"query": "q", "documents": ["text 1", "text 2", "text 3"], "top_n": 3})
