"""Tests without a real Odoo nor Docling of scripts/ingest.py."""
import base64
import hashlib
import io
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ingest  # noqa: E402

TEXT = "# Returns\n\nReturns go through a dedicated route.\n\n## Exceptions\n\nDamaged goods are scrapped.\n"
OTHER = "# Shipping\n\nShipments leave before noon.\n"


class FakeHub:
    """Answers document/list with the documents it knows, document/attachment with one file, records every write."""

    def __init__(self, known=(), attachment=None):
        self.calls = []
        self.known = list(known)
        self.attachment = attachment

    def call(self, route, payload):
        self.calls.append((route, payload))
        if route == "document/list":
            return {"documents": self.known}
        if route == "document/attachment":
            raw = self.attachment["raw"]
            return {"id": payload["attachment_id"], "name": self.attachment["name"], "mimetype": "text/markdown",
                    "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "record": {"model": "project.task", "id": 3},
                    "data": base64.b64encode(raw).decode()}
        return {"id": payload.get("document_id") or 5 + len(self.known), "title": payload.get("name") or "spec.md",
                "type": "url" if payload.get("url") else "binary", "has_text": bool(payload.get("text"))}


def connected(hub):
    """ingest.py talks to the fake hub whatever the configuration of the machine."""
    return unittest.mock.patch.object(ingest, "connect", lambda: hub)


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "cloud"
        self.folder.mkdir()
        self.doc = self.folder / "returns.md"
        self.doc.write_text(TEXT, encoding="utf-8")
        self.hub = FakeHub()
        self._python = ingest.docling_python
        ingest.docling_python = lambda: None  # no Docling in the tests

    def tearDown(self):
        ingest.docling_python = self._python
        self.tmp.cleanup()

    def writes(self, hub):
        return [payload for route, payload in hub.calls if route == "document/write"]

    def test_light_conversion_and_outline(self):
        text, used = ingest.convert(self.doc)
        self.assertEqual(used, "text")
        self.assertEqual(ingest.outline(text), ["# Returns", "## Exceptions"])
        self.assertEqual(len(ingest.fingerprint(self.doc)), 64)
        nothing = Path(self.tmp.name) / "nothing.xyz"
        nothing.write_text("x")
        with self.assertRaises(RuntimeError):
            ingest.convert(nothing)

    def test_dry_run_shows_only_the_outline(self):
        out, err = io.StringIO(), io.StringIO()
        code = ingest.main([str(self.doc), "--project", "7", "--url", "https://drive.example.com/x", "--out", self.tmp.name], out=out, err=err)
        self.assertEqual(code, 0)
        self.assertIn("returns.md:", out.getvalue())
        self.assertIn("  # Returns", out.getvalue())
        self.assertIn("add --yes", out.getvalue())
        self.assertNotIn("dedicated route", out.getvalue(), "the body never reaches the output")
        self.assertEqual(ingest.main([str(self.doc), "--project", "7", "--task", "3"], out=out, err=err), 2, "one anchor at most")
        self.assertEqual(ingest.main([str(self.doc), "--out", self.tmp.name], out=out, err=err), 0,
                         "no anchor: the home of the company")
        self.assertEqual(ingest.main(["--project", "7"], out=out, err=err), 2, "a file or an attachment")
        self.assertEqual(ingest.main(["--attachment", "12", "--task", "3"], out=out, err=err), 2,
                         "an attachment belongs to its record already")

    def test_yes_writes_a_link_or_the_file_with_fingerprint_and_text(self):
        with connected(self.hub):
            out = io.StringIO()
            code = ingest.main([str(self.doc), "--task", "3", "--url", "https://drive.example.com/returns.md",
                                "--summary", "Rules for returns.", "--yes"], out=out, err=io.StringIO())
            self.assertEqual(code, 0)
            [payload] = self.writes(self.hub)
            self.assertEqual((payload["task_id"], payload["url"], payload["name"]), (3, "https://drive.example.com/returns.md", "returns.md"))
            self.assertEqual(payload["fingerprint"], ingest.fingerprint(self.doc))
            self.assertEqual(payload["text"], TEXT)
            self.assertTrue(payload["keep_text"])
            self.assertNotIn("data", payload)
            self.assertIn("document 5 returns.md (url) with text", out.getvalue())
            # without a link the file itself goes on the record
            code = ingest.main([str(self.doc), "--task", "3", "--no-text", "--yes"], out=out, err=io.StringIO())
            self.assertEqual(code, 0)
            payload = self.writes(self.hub)[-1]
            self.assertEqual(base64.b64decode(payload["data"]), TEXT.encode())
            self.assertIsNone(payload.get("text"))
            self.assertFalse(payload["keep_text"])

    def test_a_known_fingerprint_is_not_written_twice(self):
        hub = FakeHub(known=[{"id": 9, "title": "Returns spec", "fingerprint": ingest.fingerprint(self.doc)}])
        with connected(hub):
            out = io.StringIO()
            code = ingest.main([str(self.doc), "--task", "3", "--url", "https://d/x", "--yes"], out=out, err=io.StringIO())
        self.assertEqual(code, 0)
        self.assertIn("already in the memory as document 9 Returns spec", out.getvalue())
        self.assertEqual(self.writes(hub), [])
        self.assertEqual(hub.calls[0], ("document/list", {"task_id": 3}))

    def test_a_folder_is_a_batch_with_one_yes(self):
        (self.folder / "shipping.md").write_text(OTHER, encoding="utf-8")
        (self.folder / "scan.xyz").write_bytes(b"no converter for this")
        (self.folder / ".hidden.md").write_text("ignored", encoding="utf-8")
        hub = FakeHub(known=[{"id": 9, "title": "Returns spec", "fingerprint": ingest.fingerprint(self.doc)}])
        with connected(hub):
            out = io.StringIO()
            code = ingest.main([str(self.folder), "--project", "7", "--url", "https://drive.example.com/procedures/",
                                "--summary", "Procedures of the folder."], out=out, err=io.StringIO())
            self.assertEqual(code, 0)
            self.assertIn("scan.xyz: skipped, no converter", out.getvalue())
            self.assertIn("already in the memory as document 9", out.getvalue())
            self.assertIn("  # Shipping", out.getvalue())
            self.assertIn("add --yes, after the person agreed, to write it", out.getvalue())
            self.assertEqual(self.writes(hub), [])
            code = ingest.main([str(self.folder), "--project", "7", "--url", "https://drive.example.com/procedures",
                                "--summary", "Procedures of the folder.", "--yes"], out=out, err=io.StringIO())
            self.assertEqual(code, 0)
            [payload] = self.writes(hub)
            self.assertEqual((payload["name"], payload["url"], payload["project_id"], payload["summary"]),
                             ("shipping.md", "https://drive.example.com/procedures/shipping.md", 7, "Procedures of the folder."))
            self.assertEqual(payload["text"], OTHER)
            self.assertIn("document 6 shipping.md (url) with text", out.getvalue())
        # nothing convertible: an error
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        (empty / "scan.xyz").write_bytes(b"x")
        with connected(FakeHub()):
            self.assertEqual(ingest.main([str(empty), "--project", "7", "--url", "https://d/"], out=io.StringIO(), err=io.StringIO()), 1)

    def test_an_attachment_of_odoo_is_downloaded_converted_and_brought_in(self):
        hub = FakeHub(attachment={"name": "spec.md", "raw": TEXT.encode()})
        with connected(hub):
            out = io.StringIO()
            code = ingest.main(["--attachment", "12", "--summary", "The returns spec."], out=out, err=io.StringIO())
            self.assertEqual(code, 0)
            self.assertIn("spec.md: ", out.getvalue())
            self.assertIn("  # Returns", out.getvalue())
            self.assertEqual(self.writes(hub), [])
            code = ingest.main(["--attachment", "12", "--summary", "The returns spec.", "--yes"], out=out, err=io.StringIO())
            self.assertEqual(code, 0)
            [payload] = self.writes(hub)
            self.assertEqual((payload["document_id"], payload["summary"]), (12, "The returns spec."))
            self.assertNotIn("name", {k for k, v in payload.items() if v is not None})
            self.assertEqual(payload["fingerprint"], hashlib.sha256(TEXT.encode()).hexdigest())
            self.assertEqual(payload["text"], TEXT)
        # the download is gone
        saved = [c for c in hub.calls if c[0] == "document/attachment"]
        self.assertEqual(len(saved), 2)


if __name__ == "__main__":
    unittest.main()
