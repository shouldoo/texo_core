# texo_core

Texo — workspace and memory for AI agents at work. This repository is the core: the rules every agent follows
in a Texo working folder, the `texo` CLI that connects it to the memory, installs the skill packs of its sector and
mounts its threads, the skills of the memory, the model of the memory and the tools to measure it. It knows how an
agent reaches the memory and how a pack or a thread is mounted; it knows nothing of a sector (that is a pack of the
marketplace) or of an organisation (that is its hub).

| Part | Repository | What |
|---|---|---|
| core | `texo_core` (this one) | agnostic rules, `texo` CLI, thread drivers, pack installer, memory skills, docs, checks |
| hub | [`texo_hub`](https://github.com/shouldoo/texo_hub) | the Odoo modules that keep the memory and the configuration of the organisation (its packs and threads) |
| marketplace | [`texo_marketplace`](https://github.com/shouldoo/texo_marketplace) | the skill packs of the sectors: skills, the seed of the hub, suggested threads |

An organisation may also keep a private repository of its own, for the adapters written for it (`threads/<id>/`)
and its evaluation sets (`eval/`): it can be the working folder itself. Nothing else lives in git.

## Install

Once per machine; git and Python 3.11 or later:

```bash
curl -fsSL https://raw.githubusercontent.com/shouldoo/texo_core/main/setup/install.sh | bash
TEXO_VERSION=v2.0.0 bash setup/install.sh        # a given release (default: the latest tag)
```

The core is checked out at a release tag in `~/.local/share/texo/core` and the command `texo` is linked in
`~/.local/bin`. `texo where` prints the folder of the core.

## A working folder

Any folder becomes a working folder of the organisation:

```bash
texo init https://memoria.example.org acme   # texo.toml, assistant trust, then texo mount
# put the hub token in ~/.config/texo/acme.env (mode 600): TEXO_HUB_TOKEN=...
texo doctor                                  # the hub, every pack, thread and credential
```

`texo.toml` holds only the hub and the name of the organisation:

```toml
[texo]
organisation = "acme"                        # credentials in ~/.config/texo/acme.env, mode 600
hub_url = "https://memoria.example.org"
hub_token = "env:TEXO_HUB_TOKEN"             # never the value
# marketplace = "github.com/<owner>/<repo>"  # optional: another marketplace (or TEXO_MARKETPLACE)
```

The packs (with their versions) and the threads come from the hub: administrators edit them in Odoo (*Settings >
Users > Texo Skill Packs*, *Texo Threads*) or through the route `admin/config`. `texo mount` reads them (route
`config`, kept in `.texo/config.json`; `--offline` uses that copy) and adds the `[[pack]]` and `[[thread]]` of
`texo.toml`, which replace the hub's entry with the same name or id.

What `texo mount` leaves in the folder, outside git:

```text
texo.toml                                   the hub and the organisation
AGENTS.md, CLAUDE.md, GEMINI.md             the rules of the core and the index of the threads (written only
                                            when absent or written by mount)
.texo/                                      config.json, THREADS.md, threads.json
.mcp.json, .gemini/settings.json            the MCP servers: memoria and the MCP threads
.agents/skills/, .claude/skills/            links to the skills of core, threads, packs and the folder's own skills/
<work_dirs of the packs>/                   e.g. progetti/ for the Odoo partners
```

## Skill packs

The marketplace is one repository; `packs/<name>/` is a pack and the tag `<name>-<version>` its release.
`texo mount` checks out only that folder at that tag, once per machine, in
`$TEXO_SHARED_DIR/mirrors/pack-<name>-<version>` (default `~/.local/share/texo`).

```text
packs/<name>/
├── pack.toml        [pack] name, version, core it needs, work_dirs; [[suggested_thread]]
├── skills/          the skills of the sector, each with its references
├── seed.toml        activities, sections, rules and project templates of the sector, for texo seed
└── demo/            optional: a fictional organisation for tests (setup/load-demo.sh)
```

A pack carries method only. The rules of a sector reach the hub through its seed; thresholds, amounts, deadlines
and tables of a law are facts of the organisation in its hub, with the article read, the date of the verification
and an expiry.

## The CLI

| Command | What |
|---|---|
| `init <hub url> <organisation>` | writes `texo.toml`, trusts the folder for Claude Code (and an Antigravity profile when `agy` is installed), then mounts |
| `mount [--yes] [--offline]` | reads the configuration of the hub; installs the packs; checks their versions, the core they need and every thread; clones the git-mirror sources (only their `paths` when declared); installs pinned CLIs (with `--yes`); writes the MCP configuration of Claude Code, Gemini CLI and the Antigravity profile; links the skills of core, threads, packs and folder; creates the working folders of the packs; writes `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.texo/THREADS.md` |
| `doctor` | checks the hub, every pack, thread and credential, without showing a credential |
| `threads` | the threads of the folder (also the tool `threads` of the MCP server `memoria`) |
| `thread <id> ls\|read\|search` | reads a git-remote source at its pinned ref, without cloning it |
| `seed [--apply --yes]` | the `seed.toml` of every pack into the hub (route `admin/seed`, administrators): a dry run, then the writes |
| `where [--pack <name>]` | the folder of the core, or of an installed pack |
| `mcp` | the MCP server `memoria` over stdio: the rules of the session as instructions, the memory as tools |
| `run-thread <id>` | started by the assistants: an MCP thread with its credentials, so no token is written in a configuration file |
| `whoami`, `rules`, `context`, `search`, `read`, `note`, `lesson`, `task`, `task-note`, `log-time`, `update`, `review`, `documents`, `document-write`, `sources-*`, … | the memory, as the person: every write needs `--yes` after the person agreed |

Outside a working folder the CLI takes the hub from `TEXO_HUB_URL` and `TEXO_HUB_TOKEN`.

## Contents

| Path | What |
|---|---|
| `AGENTS.md` | the rules of every agent in a working folder (`texo mount` writes them into the folder) |
| `texo/` | the CLI: `hub.py` (the memory client and the MCP server), `config.py` (`texo.toml`, the configuration of the hub, credentials), `packs.py`, `threads.py` (drivers), `mount.py`, `seed.py`, `bridge.py`, `setup_assistants.py` |
| `docs/` | `memoria.md` (the model of the memory), `fili.md` (threads and packs), `ARCHITECTURE.md`, `blueprint.md` |
| `skills/` | `texo-sessione`, `memoria-consolidamento`, `memoria-ingestione`, `memoria-fonti` |
| `playbooks/` | a new memory system, its profile, the evaluation of the memory, the local coordination Odoo, the review of the knowledge |
| `scripts/` | `ingest.py` (documents into the memory, Docling or light converters), `eval_memoria.py` and `eval_varianti.py` (the measure of the search), `load_demo.py`, the checks every Texo repository runs (`check_isolation.py`, `check_agents.py`, `check_skills.py`, `check_okf.py`, `check_attribution.py`) |
| `setup/` | `install.sh`, `install-git-hooks.sh`, `coordinamento-up.sh` (a local coordination Odoo with texo_hub at a release), `load-demo.sh` (the demo of a pack into a test database), `install-docling.sh` |

## Checks

The workflow `checks` runs the unit tests (Python 3.11 and 3.13), `ruff`, `shellcheck`, gitleaks, and the checks of
`scripts/`: isolation (the names that must never appear come from the organisation secret `ISOLATION_PATTERNS`,
never from a file of the repository), skills structure, independence from any one assistant, no assistant named
as author in a commit or a pull request.

```bash
python3 -m unittest discover -s tests
```

## Licence

LGPL-3.0-or-later.
