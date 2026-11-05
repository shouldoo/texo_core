"""Tests of the home-path pattern of scripts/check_isolation.py (python -m unittest discover -s scripts/tests)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import check_isolation  # noqa: E402

HOME, USERS = "/" + "home/", "/" + "Users/"  # built here: the check reads this file too


class TestHomePath(unittest.TestCase):

    def test_a_home_folder_is_found(self):
        for text in (f"{HOME}mario/x", f"see {USERS}mario/y", f'cd "{HOME}mario/w"', f"({HOME}anna/a)",
                     f"[file]({HOME}anna/notes.md)"):
            self.assertTrue(check_isolation.HOME_PATH.search(text), text)

    def test_a_web_address_and_the_placeholders_are_not(self):
        for text in ("https://www.garanteprivacy.it/home/docweb/-/docweb-display/9105201",
                     "/home/<user>/", "/home/odoo/data"):
            self.assertIsNone(check_isolation.HOME_PATH.search(text), text)


if __name__ == "__main__":
    unittest.main()
