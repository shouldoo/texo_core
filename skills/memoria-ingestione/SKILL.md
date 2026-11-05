---
name: memoria-ingestione
description: >-
  Bring the documents of a project into the memory of the coordination Odoo, as
  attachments of the record they belong to: a PDF, a scan, an Office file, an e-mail or a page the person
  received or found, as a local file, a whole folder (local, or a cloud folder reached
  through the connector of the session) or an attachment of a record in Odoo. Convert
  locally (`scripts/ingest.py`, Docling or the light converters), read the converted
  text, propose the document (where the original is, what it contains, when read)
  and what it gives (the rules it states, citing the document; the changes to the
  description of the project, which the person makes; a project update when it changes
  the state of the work; lessons without the customer), write only after the person's
  yes, with the state their role allows. The procedures of the organisation in a folder
  become documents of the organisation, and the rules they state become its rules:
  the rules bind, the sources do not. A sensitive document is kept without its text.
  Triggers: "ingerisci questo documento", "leggi questo PDF e metti in memoria", "mappa
  la documentazione del progetto", "cosa dice la spec allegata", "nel task c'è un
  allegato: cosa dice?", "le procedure sono in questa cartella: portale in memoria",
  "ingest this document", "add this file to the memory", "quali documenti abbiamo su
  <progetto>".
---

# memoria-ingestione

## Overview

A document of the memory is an **attachment of the record it belongs to** (a task, a
project, a customer; the organisation's own on the company): the
file itself, or a **link** to an original that stays where the person keeps it (a
shared drive, a web page). Its title is the name, its summary the description; the
memory adds the reading date, the fingerprint and, by default, the converted text as
a second attachment `<name>.md` next to it (searchable: a word present only in the text
finds the document; a Markdown or text file is its own text). The people see both on
the record, with its permissions. A rule taken from a document **cites** it
(`--document <id>` on the rule): when a later reading finds the original changed, the
rule is marked `source_changed` in the context pack and in the review queue until a
lead confirms or supersedes it.

```bash
CTX="core/bin/texo"                     # from the root of the customer repository
INGEST="python3 core/scripts/ingest.py"
$CTX documents --project <id>                 # the documents already there (fingerprints included)
$INGEST <file> --project <id> --url "<link>"  # one file whose original lives elsewhere: convert, outline only
$INGEST <file> --task <id>                    # one file the person gives: it goes on the record itself
$INGEST <folder> --project <id> --url "<link of the folder>"   # a batch, one yes
$INGEST --attachment <id>                     # an attachment already on a record in Odoo
$INGEST <file> --url "<link>"                 # no anchor: a document of the organisation itself (the company)
$CTX document <id> --text --max-chars 6000    # read a document in slices
```

| Where the original is | How it reaches `ingest.py` | What the record gets |
|---|---|---|
| attached to a task or project in Odoo | `--attachment <id>` (downloaded through the hub into a temporary folder, removed at the end) | nothing new: that attachment becomes the document |
| a shared drive, a cloud folder, a web page | the files downloaded into a temporary folder (a connector thread of the fabric, `.texo/THREADS.md`, lists and downloads them), then the file or the folder, with `--url` | a link to the original (for a batch the link of the folder plus the file name) |
| a local file of the person, an e-mail saved as `.eml` | the file, without `--url` | the file itself, as an attachment |

## Workflow & Steps

### 1. Before converting
- Check the documents of the record (`$CTX documents`): `ingest.py` skips a fingerprint
  the record already knows and says which document it is (idempotent); a changed
  original gets a new reading (`$CTX document-write --id <id>` with the new fingerprint
  and text), never a second document.
- Ask the person where the original lives if they did not say it (a link, or the file
  goes on the record), the anchor
  (task, project or customer; **none** for a document of the organisation itself, of no
  customer: it goes on the company, `--company <id>` for another
  company), and whether the document is sensitive (contracts, data of people,
  commercial terms): then `--no-text`, and the summary says what it is, not what it
  says; a sensitive original that must not enter Odoo is brought in as a link
  (`--url`), never as a file. For a customer that serves vulnerable people: no text, no
  local copy beyond the conversion, nothing of the content in the chat.
- The file reaches this machine the way the person chooses: an attachment comes
  through `--attachment`; a cloud folder is listed and downloaded with a connector
  thread of the fabric into a temporary folder; an e-mail is saved as `.eml`. Never ask the
  person to paste a document in the chat.

### 2. Convert and read
- `$INGEST <file|folder> ...` without `--yes`: for every file it prints the size, the
  fingerprint, the outline and where the converted text is (a temporary folder, or
  `--out <dir>`), says which files are already in the memory and which no converter handles,
  and writes nothing.
- Read the converted text from that file. Say in one line what each document is.
  Docling handles PDF, scans (OCR), Office, HTML, images and e-mails; without it the
  light converters handle Markdown, text, PDF (`pdftotext`) and DOCX (`python-docx`)
  when those tools are installed.

### 3. Propose the documents and the facts
In chat, for the person's yes, one message for the whole lot:
- each document: title, where the original is (link or file on the record), a summary
  of a few lines (`--summary` applies to every file of a batch: for different
  summaries, bring the files in one by one), the anchor, text kept or not;
- what the document gives, each item for its own place:
  - a **rule** it states (what an agent must always or never do), citing the document
    (`--document <id>`, after the document exists), on the project, the customer or, for
    a document of the organisation, with no anchor;
  - what it says about the organisation, the customer, the project or a task (who
    decides, how a process runs, what was agreed): a **fact** on that record, one per
    entry, in its section, with keywords, citing the document
    (`$CTX note "<title>" "<text>" --kind fact --section <code> --project <id> --keywords <word>... --document <id> --yes`);
  - how an operation is done there, step by step: a **procedure**, likewise
    (`--kind procedure`);
  - a constraint, a scope or a stable decision for the **description** of the project:
    propose the text, the person edits the description in Odoo;
  - a change in the state of the work (a delay, a new risk, a milestone moved): a
    **project update**;
  - something that helps other projects: a **lesson** without the customer.
  No personal data, no commercial terms in any of them.

### 4. Write after the yes
```bash
$INGEST <file|folder> --project <id> --url "<link>" --summary "<text>" --yes   # the documents
$INGEST --attachment <id> --summary "<text>" --yes
$CTX note "<title>" "<rule>" --project <id> --document <document id> --yes                  # each rule
$CTX note "<title>" "<text>" --kind fact|procedure --section <code> --document <document id> --yes   # each fact, procedure
$CTX update <project id> "<title>" <status> "<what the document changes>" --yes              # when it changes the state
$CTX lesson "<finding>" "<solution>" --tags <tag>... --yes                                    # each lesson
```
A document has no state: once written it is in the memory, for a member as for a
lead; the rules a member writes are drafts that wait for the lead. Then
`$CTX documents --project <id>` shows the documents; delete the temporary folder of a
download if `--out` was used. Only a lead takes a document out of the memory
(`$CTX document-remove <id>`): what the memory brought in goes, an attachment the people
put on the record stays theirs.

### 5. The procedures of the organisation («the procedures are in this folder»)
The sources are never the memory: the notes that cite them are.
1. Bring the files of the folder in as documents of the organisation (no anchor: the
   company), as above, after the yes. They stay sources, searchable.
2. For each file, propose what it gives, one note per entry, each citing its document
   and in its section (`operations`, `compliance`, ...): the **procedures** it describes
   (how an operation is done, step by step: `--kind procedure`), the **facts** it states
   (`--kind fact`), the **rules** it states for the agents (short, one obligation or
   prohibition each). A procedure of the agent itself becomes a skill of the customer
   or of the industry instead (a separate change, with no customer in it). After the yes,
   `$CTX note ... --document <id> --yes` for each.
3. Say that a draft rule binds only once a lead activates it, and that a changed source
   marks every note that cites it `source_changed`, to re-check.

### 6. An attachment of a record («nel task c'è un allegato: cosa dice?»)
`$CTX task <id>` shows the record; `$INGEST --attachment <id>` converts it and shows
the outline; answer from the converted text, quoting only the lines that support the
answer; propose to bring the attachment into the memory (it stays where it is, with
its summary and converted text) and what it gives, write after the yes.

## Safety & Invariants

- Never write without the person's yes; never paste the original or long extracts in
  the chat: quote the lines that support a fact, nothing more.
- A sensitive document keeps no text (`--no-text`) and its summary names the kind of
  document, not its content.
- The converted text, the downloads and the temporary files stay out of every git
  repository (customer, industry, core, code); a download of an
  attachment is removed by the script at the end.
- A link never holds content: it points to the original, nothing more.
- A cloud folder used as a source is never one with real data of a customer in a test.
- Deterministic checks: `$CTX documents` before and after; the fingerprint printed by
  `ingest.py` equals `sha256sum <file>`; a second run of the same batch writes nothing.
