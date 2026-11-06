"""Tests of scripts/load_demo.py without an Odoo: the helpers and the refusal of a real database."""
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import load_demo  # noqa: E402


class LoadDemoTest(unittest.TestCase):

    def test_a_database_the_data_does_not_name_is_refused(self):
        env = SimpleNamespace(cr=SimpleNamespace(dbname="production"))
        with unittest.mock.patch.object(load_demo, "data", SimpleNamespace(DATABASES=("demo-test",))):
            with self.assertRaisesRegex(SystemExit, "refusing to seed 'production'"):
                load_demo.seed(env)

    def test_text_becomes_html_and_a_message_plain_text(self):
        self.assertEqual(load_demo.html_of("One <b>.\nTwo\n\nThree"), "<p>One &lt;b&gt;.<br>Two</p><p>Three</p>")
        self.assertEqual(load_demo.plain_of("<p>One&nbsp;&amp;   two</p>"), "One & two")

    def test_a_generated_pdf_is_deterministic(self):
        pdf = load_demo.pdf_bytes("Title (draft)", ["line one", "line two"])
        self.assertTrue(pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF"))
        self.assertEqual(pdf, load_demo.pdf_bytes("Title (draft)", ["line one", "line two"]))

    def test_anchors_and_the_lessons_of_a_pack(self):
        customer, project, task = SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)
        projects, tasks = {"Shop": project}, {("Shop", "Cart"): task}
        self.assertEqual(load_demo.anchor_of("organisation", customer, projects, tasks), {})
        self.assertEqual(load_demo.anchor_of("customer", customer, projects, tasks), {"partner_id": 1})
        self.assertEqual(load_demo.anchor_of("project:Shop", customer, projects, tasks), {"project_id": 2})
        self.assertEqual(load_demo.anchor_of("task:Shop/Cart", customer, projects, tasks), {"task_id": 3})
        lessons = [({"state": "active", "tags": ["a", "b"]}, 10), ({"state": "active", "tags": ["a"]}, 11),
                   ({"state": "draft", "tags": ["a", "b"]}, 12), ({"state": "active", "tags": ["c"]}, 13)]
        self.assertEqual(load_demo.pack_lessons(lessons, ["a", "b"]), [10, 11], "more shared tags first, no draft")

    def test_the_cards_of_the_external_sources(self):
        made = []

        def labels(names, kind):
            made.extend((kind, name) for name in names or [])
            return [hash((kind, name)) % 1000 for name in names or []]

        card = {"key": "a", "channel": "UmbriaON", "url": "https://umbriaon.example/a", "title": "Titolo",
                "published_on": "2026-10-31", "event_date": None, "abstract": "Che cosa dice.", "quotes": None,
                "persons": ["Mario Rossi"], "bodies": [], "places": ["Terni"], "themes": ["Crisi in Comune"],
                "acts": None, "keywords": "sfiducia, mozione", "stance": "none", "relevance": 3, "related": ["b", "a", "zz"]}
        vals = load_demo.card_values(card, 7, labels)
        self.assertEqual((vals["channel_id"], vals["kind"], vals["relevance"]), (7, "article", "3"))
        self.assertEqual(vals["published_on"], "2026-10-31 12:00:00")
        self.assertEqual((vals["event_date"], vals["quotes"], vals["acts"], vals["triage_note"]), (False, False, False, False))
        self.assertEqual(vals["person_ids"], [(6, 0, [hash(("person", "Mario Rossi")) % 1000])])
        self.assertEqual(vals["body_ids"], [(6, 0, [])])
        self.assertEqual(made, [("person", "Mario Rossi"), ("place", "Terni"), ("theme", "Crisi in Comune")])
        self.assertEqual(load_demo.card_values({"key": "v", "channel": "c", "url": "u", "title": "t", "abstract": "a"}, 1,
                                               labels)["relevance"], "2", "medium by default")
        self.assertFalse(load_demo.published_at(None))
        self.assertEqual(load_demo.related_cards([card, {"key": "b", "related": ["a"]}]), {"a": ["b"], "b": ["a"]},
                         "an unknown key and the card itself are left out")

    def test_the_load_waits_for_the_embedding_service(self):
        class Answer:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        calls, sleeps = [], []

        def starting(url, timeout=None):
            calls.append(url)
            if len(calls) < 3:
                raise load_demo.urllib.error.URLError("connection refused")
            return Answer()

        self.assertTrue(load_demo.service_ready("http://tei:80", wait=30, step=5, opener=starting, sleep=sleeps.append))
        self.assertEqual(calls, ["http://tei:80/health"] * 3)
        self.assertEqual(sleeps, [5, 5])

        def down(url, timeout=None):
            raise OSError("no route to host")

        sleeps.clear()
        self.assertFalse(load_demo.service_ready("http://tei:80", wait=10, step=5, opener=down, sleep=sleeps.append))
        self.assertEqual(len(sleeps), 2, "it gives up after the wait")


if __name__ == "__main__":
    unittest.main()
