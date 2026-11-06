"""Tests of scripts/check_okf.py: a knowledge bundle as an Open Knowledge Format bundle."""
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_okf  # noqa: E402


class CheckOkfTest(unittest.TestCase):
    def bundle(self, files):
        root = Path(tempfile.mkdtemp())
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root

    def test_a_bundle_at_its_root(self):
        root = self.bundle({
            "INDEX.md": '---\ntype: "Index"\ntitle: "I"\ndescription: "d"\n---\n# I\n',
            "reference/v20/models.md": '---\ntype: "Reference"\ntitle: "M"\ndescription: "m"\n---\n',
            "playbooks/x.md": "# X\n",
            "README.md": "# not part of the bundle\n",
        })
        errors = check_okf.check(root)
        self.assertIn("INDEX.md: the root index carries okf_version '0.2'", errors)
        self.assertIn("playbooks/x.md: no frontmatter (python3 scripts/check_okf.py --write)", errors)
        self.assertEqual(len(errors), 2)

    def test_a_repository_without_knowledge_passes(self):
        self.assertEqual(check_okf.main(["--root", tempfile.mkdtemp()]), 0)

    def test_write_derives_the_frontmatter_and_check_accepts_it(self):
        root = self.bundle({
            "knowledge/INDEX.md": "# Index\n\n> Questo indice è sempre caricato.\n",
            "knowledge/reference/v19/views.md": "# Views — Delta Odoo 19\n\n> Da leggere INSIEME a `reference/views.md`. Altro.\n",
            "knowledge/playbooks/adozione.md": "# Adozione\n\n> Regime: **disegno**. Le fasi dell'adozione, es. la prima.\n",
        })
        self.assertEqual(check_okf.write(root, out=io.StringIO()), 3)
        self.assertEqual(check_okf.check(root), [])
        views = check_okf.parse((root / "knowledge/reference/v19/views.md").read_text(encoding="utf-8"))
        self.assertEqual(views, {"type": "Reference", "title": "Views — Delta Odoo 19",
                                 "description": "Views — Delta Odoo 19: da leggere INSIEME a `reference/views.md`.",
                                 "tags": ["views", "v19"]})
        playbook = check_okf.parse((root / "knowledge/playbooks/adozione.md").read_text(encoding="utf-8"))
        self.assertEqual((playbook["type"], playbook["description"]),
                         ("Playbook", "Le fasi dell'adozione, es. la prima."), "no regime line, no cut at «es.»")
        index = check_okf.parse((root / "knowledge/INDEX.md").read_text(encoding="utf-8"))
        self.assertEqual((index["type"], index["okf_version"]), ("Index", "0.2"))
        self.assertEqual(check_okf.write(root, out=io.StringIO()), 0, "a file with a frontmatter is left alone")

    def test_check_reports_what_is_missing(self):
        root = self.bundle({
            "knowledge/INDEX.md": '---\ntype: "Index"\ntitle: "I"\ndescription: "d"\n---\n# I\n',
            "knowledge/a.md": "# A\n",
            "knowledge/b.md": "---\ntype: Reference\ntitle: B\n---\n# B\n",
            "knowledge/c.md": "---\nnot a key\n---\n",
            "knowledge/x/index.md": '---\ntype: "Reference"\ntitle: "X"\ndescription: "x"\n---\n',
        })
        errors = "\n".join(check_okf.check(root))
        self.assertIn("knowledge/INDEX.md: the root index carries okf_version", errors)
        self.assertIn("knowledge/a.md: no frontmatter", errors)
        self.assertIn("knowledge/b.md: no description", errors, "a plain scalar is a value too")
        self.assertNotIn("knowledge/b.md: no type", errors)
        self.assertIn("knowledge/c.md: frontmatter: not a key: value line", errors)
        self.assertIn("index.md is reserved by OKF", errors)


if __name__ == "__main__":
    unittest.main()
