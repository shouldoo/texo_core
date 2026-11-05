"""Tests of scripts/check_agents.py: a Texo repository independent from any one assistant."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_agents as ca  # noqa: E402

SKILL = "---\nname: demo\ndescription: A demo skill.\n---\n# Demo\n"
CORE = Path(__file__).resolve().parent.parent


class CheckAgentsTest(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "demo").mkdir(parents=True)
        (self.root / "skills" / "demo" / "SKILL.md").write_text(SKILL, encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# Rules\n\nOpen only the section you need.\n", encoding="utf-8")
        for name in ca.POINTERS:
            (self.root / name).write_text("# Pointer\n@AGENTS.md\n", encoding="utf-8")

    def test_a_clean_repository_passes(self):
        self.assertEqual(ca.check(self.root), [])

    def test_the_core_itself_passes(self):
        self.assertEqual(ca.check(CORE), [])

    def test_pointer_without_import_fails(self):
        (self.root / "CLAUDE.md").write_text("# Pointer\nRead the rules.\n", encoding="utf-8")
        self.assertIn("CLAUDE.md: does not import AGENTS.md", ca.check(self.root))

    def test_a_customer_pointer_may_import_the_rules_of_the_core(self):
        (self.root / "GEMINI.md").write_text("@core/AGENTS.md\n@AGENTS.md\n", encoding="utf-8")
        self.assertEqual(ca.check(self.root), [])

    def test_a_pointer_with_rules_fails(self):
        (self.root / "GEMINI.md").write_text("@AGENTS.md\n" + "rule\n" * 10, encoding="utf-8")
        self.assertTrue(any("keep this file a pointer" in e for e in ca.check(self.root)))

    def test_non_portable_frontmatter_fails(self):
        (self.root / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\ndescription: d\nallowed-tools: Bash\n---\n", encoding="utf-8")
        self.assertIn("skills/demo/SKILL.md: non-portable frontmatter keys ['allowed-tools']", ca.check(self.root))

    def test_assistant_specific_text_fails(self):
        (self.root / "AGENTS.md").write_text("Open it with `Read`.\nRun ${CLAUDE_PLUGIN_ROOT}/x.\n", encoding="utf-8")
        errors = ca.check(self.root)
        self.assertIn("AGENTS.md:1: tool name of one assistant '`Read`'", errors)
        self.assertIn("AGENTS.md:2: Claude Code variable '${CLAUDE_PLUGIN_ROOT'", errors)

    def test_lowercase_words_are_not_tool_names(self):
        (self.root / "AGENTS.md").write_text("Override `write` and `create`.\n", encoding="utf-8")
        self.assertEqual(ca.check(self.root), [])


if __name__ == "__main__":
    unittest.main()
