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


if __name__ == "__main__":
    unittest.main()
