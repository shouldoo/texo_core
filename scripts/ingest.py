#!/usr/bin/env python3
"""ingest.py — bring a document into the memory of a project: convert it locally, show
what it holds, and write it in the coordination Odoo after the person's yes.

    python3 scripts/ingest.py <file> --project <id> --url "<link>"          # convert and show
    python3 scripts/ingest.py <file> --project <id> --url "<link>" --yes    # also write it, as a link
    python3 scripts/ingest.py <file> --task <id> --yes                      # the file itself on the task
    python3 scripts/ingest.py <file> ... --no-text --yes       # sensitive: keep no converted text
    python3 scripts/ingest.py <folder> --project <id> --url "<link of the folder>"  # a batch
    python3 scripts/ingest.py --attachment <id>                # an attachment of a record in Odoo
    python3 scripts/ingest.py <file> --url "<link>"            # no anchor: a document of the organisation
                                                               # itself, on the company (--company <id>)

A document of the memory is an attachment of the record it belongs to. With --url the
original stays where the person keeps it (a shared drive, a web page) and the record gets a
link to it; without, the file itself becomes the attachment; with --attachment the attachment
already on a record becomes the document. Its fingerprint, the summary the person confirms
and, unless --no-text, its converted text go with it. The conversion runs on this machine:
Docling when `setup/install-docling.sh` installed it, otherwise the light converters
(pdftotext, python-docx, plain text and Markdown). Nothing is printed beyond the outline and
the size of the text: the agent reads the text from the memory (texo document --text) or
from the file this script leaves in the folder given by --out.

A folder is a batch: one document per file, its link the folder's plus the file name, one
summary, one --yes for the lot. A fingerprint the record already knows is skipped
(idempotent); a file no converter handles is skipped and said. An attachment of a record in
Odoo (--attachment) is downloaded through the hub into a temporary folder and converted; the
download is removed at the end.
"""
import argparse
import base64
import datetime
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from texo import hub as ctx  # noqa: E402
from texo.config import ConfigError, hub_settings  # noqa: E402

DOCLING_VENV = os.path.expanduser("~/.local/share/texo/docling")
DOCLING_SCRIPT = """
import sys
from docling.document_converter import DocumentConverter
doc = DocumentConverter().convert(sys.argv[1]).document
sys.stdout.write(doc.export_to_markdown())
"""
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".rst"}
MAX_OUTLINE = 40


def fingerprint(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def docling_python():
    for candidate in (os.path.join(DOCLING_VENV, "bin", "python"), os.path.join(DOCLING_VENV, "Scripts", "python.exe")):
        if os.path.exists(candidate):
            return candidate
    return None


def convert(path, converter=None):
    """(markdown text, converter used). Docling first, then the light converters."""
    path = Path(path)
    python = docling_python()
    if converter in (None, "docling") and python:
        result = subprocess.run([python, "-c", DOCLING_SCRIPT, str(path)], capture_output=True, text=True, timeout=3600)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout, "docling"
        if converter == "docling":
            raise RuntimeError(f"docling failed: {result.stderr.strip()[-500:]}")
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace"), "text"
    if suffix == ".pdf" and shutil.which("pdftotext"):
        result = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return result.stdout, "pdftotext"
    if suffix == ".docx":
        try:
            import docx  # python-docx, optional
        except ImportError:
            docx = None
        if docx:
            document = docx.Document(str(path))
            return "\n\n".join(p.text for p in document.paragraphs if p.text.strip()), "python-docx"
    raise RuntimeError(f"no converter for {path.name}: install Docling (setup/install-docling.sh), "
                       "pdftotext (poppler) or python-docx")


def outline(text, limit=MAX_OUTLINE):
    """The headings of the converted text, or its first lines when it has none."""
    headings = [line.strip() for line in text.splitlines() if line.startswith("#")]
    if headings:
        return headings[:limit]
    return [line.strip() for line in text.splitlines() if line.strip()][:min(limit, 10)]


def known_documents(hub, anchor):
    """{fingerprint: (id, title)} of the documents the memory already holds on the anchor."""
    documents = ctx.op_documents(hub, anchor)["documents"]
    return {d["fingerprint"]: (d["id"], d["title"]) for d in documents if d.get("fingerprint")}


def connect():
    try:
        return ctx.Hub(*hub_settings())
    except ConfigError as error:
        raise ctx.HubError(0, str(error)) from None


def main(argv=None, out=sys.stdout, err=sys.stderr):
    parser = argparse.ArgumentParser(description="Convert a document locally and bring it into the memory of a project.")
    parser.add_argument("file", nargs="?", help="a file, or a folder for a batch")
    parser.add_argument("--attachment", dest="attachment_id", type=int, help="an attachment of a record in Odoo, by id")
    parser.add_argument("--task", dest="task_id", type=int)
    parser.add_argument("--project", dest="project_id", type=int)
    parser.add_argument("--partner", dest="partner_id", type=int)
    parser.add_argument("--company", dest="company_id", type=int,
                        help="no anchor: this company instead of the current one")
    parser.add_argument("--url", help="the link to the original, which stays where it lives; for a folder, the link of the "
                                      "folder (without: the file itself is put on the record)")
    parser.add_argument("--name", help="title of the document (default: the file name)")
    parser.add_argument("--summary", help="what it contains, confirmed by the person")
    parser.add_argument("--no-text", dest="no_text", action="store_true", help="sensitive document: keep no converted text")
    parser.add_argument("--converter", choices=("docling", "light"), help="force one converter")
    parser.add_argument("--out", help="folder where the converted text is left (default: a temporary folder, removed)")
    parser.add_argument("--yes", action="store_true", help="write the document; without it only the outline is shown")
    args = parser.parse_args(argv)
    # no anchor: a document of the organisation itself, on the company
    anchor = {key: getattr(args, key) for key in ("task_id", "project_id", "partner_id", "company_id") if getattr(args, key)}
    if len([key for key in anchor if key != "company_id"]) > 1:
        err.write("give at most one of --task, --project, --partner (none: the organisation, the company)\n")
        return 2
    if bool(args.file) == bool(args.attachment_id):
        err.write("give a file or a folder, or --attachment <id>\n")
        return 2
    hub = None
    download = None
    try:
        if args.attachment_id:
            # the original stays in Odoo: the download is temporary and removed at the end
            if anchor:
                err.write("an attachment belongs to its record already: no --task, --project, --partner\n")
                return 2
            hub = connect()
            download = Path(tempfile.mkdtemp(prefix="ingest-attachment-"))
            fetched = ctx.op_document_attachment(hub, {"attachment_id": args.attachment_id, "out": str(download)})
            items = [(Path(fetched["path"]), None, args.attachment_id)]
        else:
            path = Path(args.file)
            if path.is_dir():
                files = sorted(p for p in path.iterdir() if p.is_file() and not p.name.startswith("."))
                items = [(p, args.url.rstrip("/") + "/" + p.name if args.url else None, None) for p in files]
                if not items:
                    err.write(f"no files in {path}\n")
                    return 2
            elif path.is_file():
                items = [(path, args.url, None)]
            else:
                err.write(f"not a file nor a folder: {path}\n")
                return 2
        return run(args, items, anchor, hub, out, err)
    except ctx.HubError as error:
        err.write(f"error{' ' + str(error.status) if error.status else ''}: {error}\n")
        return 1
    finally:
        if download:
            shutil.rmtree(download, ignore_errors=True)


def run(args, items, anchor, hub, out, err):
    """Convert every item, show the outline, skip the known ones, map the rest with --yes."""
    out_dir = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="ingest-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    known = {}
    if (args.yes or len(items) > 1) and not args.attachment_id:
        hub = hub or connect()
        known = known_documents(hub, anchor)
    converted, skipped = [], []
    for path, url, attachment_id in items:
        try:
            text, used = convert(path, args.converter)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            skipped.append(path.name)
            out.write(f"{path.name}: skipped, {error}\n")
            continue
        digest = fingerprint(path)
        target = out_dir / (path.stem + ".md")
        target.write_text(text, encoding="utf-8")
        out.write(f"{path.name}: {len(text)} chars with {used}, sha256 {digest[:12]}..., text in {target}\n")
        for line in outline(text):
            out.write(f"  {line}\n")
        if digest in known:
            document_id, title = known[digest]
            out.write(f"  already in the memory as document {document_id} {title}: nothing to write\n")
            continue
        payload = {"summary": args.summary, "fingerprint": digest, "read_on": datetime.date.today().isoformat(),
                   "keep_text": not args.no_text, "text": None if args.no_text else text}
        name = args.name if len(items) == 1 and args.name else None
        if attachment_id:
            payload.update(document_id=attachment_id, name=name)
        elif url:
            payload.update(anchor, name=name or path.name, url=url)
        else:
            payload.update(anchor, name=name or path.name, data=base64.b64encode(path.read_bytes()).decode())
        converted.append(payload)
    if not converted:
        if not args.out:
            shutil.rmtree(out_dir, ignore_errors=True)
        return 1 if skipped and len(skipped) == len(items) else 0
    if not args.yes:
        out.write(f"add --yes, after the person agreed, to write {'it' if len(converted) == 1 else f'these {len(converted)}'} in the memory\n")
        return 0
    for payload in converted:
        result = ctx.op_document_write(hub, payload)
        out.write(f"document {result['id']} {result['title']} ({result['type']})"
                  f"{' with text' if result.get('has_text') else ' without text'}\n")
    if not args.out:
        shutil.rmtree(out_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
