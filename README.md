# texo_core

Texo — workspace and memory for AI agents at work. This repository is the core: the rules every agent follows
in a Texo fabric, the `texo` CLI that connects it to the memory and mounts its threads, the skills of the memory,
the model of the memory and the tools to measure it. It knows how an agent reaches the memory and how a thread is
mounted; it knows nothing of a sector (that is an industry) or of an organisation (that is its hub).

| Layer | Repository | What |
|---|---|---|
| core | `texo_core` (this one) | agnostic rules, `texo` CLI, thread drivers, memory skills, docs, checks |
| hub | [`texo_hub`](https://github.com/shouldoo/texo_hub) | the Odoo modules that keep the memory: the loom |
| industry | `texo_industry_<sector>` | conventions, references, playbooks, skills, hub seed and suggested threads of a sector |
| customer | `texo_customer_<name>` | the fabric: `texo.toml`, core and industries as submodules at tags, adapters, evaluation |

The words of the documentation: the warp is the core and the industries (the fixed structure), the weft the notes
of the memory, the loom the hub, the threads the sources, tools and connectors mounted, the fabric the composed
workspace of a customer.

## A fabric

```text
texo_customer_<name>/
├── AGENTS.md, CLAUDE.md, GEMINI.md       import core/AGENTS.md, each industry, .texo/THREADS.md, their own lines
├── texo.toml                             hub, industries, threads
├── core/                    → submodule texo_core at a tag
├── industry/<sector>/       → submodule texo_industry_<sector> at a tag
├── threads/<id>/                         adapters written for this customer (an MCP server or a CLI)
├── eval/                                 the questions and the measures of this customer
└── (gitignored) .texo/, .mcp.json, .gemini/settings.json, .agents/skills/, .claude/skills/
```

```toml
[texo]
customer = "acme"                       # credentials in ~/.config/texo/acme.env, mode 600
core = "v1.0.0"
hub_url = "https://memoria.example.org"
hub_token = "env:TEXO_HUB_TOKEN"        # never the value

[[industry]]
name = "odoo_partner"
version = "v1.0.0"

[[thread]]
id = "docs"
type = "source"
driver = "git-mirror"
repo = "github.com/<owner>/<repo>"
ref = "<tag or commit>"
data_class = "public"
guide = "When to read it and its limits."
```

Setting up a fabric, from its root:

```bash
git submodule update --init --recursive
bash core/setup/bootstrap.sh          # git hooks, assistant trust, texo mount
core/bin/texo doctor                  # the hub, every thread and every credential
```

## The CLI

`core/bin/texo`: Python 3.11 or later, standard library only.

| Command | What |
|---|---|
| `mount [--yes]` | checks the versions of core and industries and the declaration of every thread; clones the git-mirror sources; installs pinned CLIs (with `--yes`); writes the MCP configuration of Claude Code (`.mcp.json`), Gemini CLI (`.gemini/settings.json`) and the Antigravity profile; links the skills of core, industries and customer; generates `.texo/THREADS.md` |
| `doctor` | checks the hub, every thread and every credential, without showing it |
| `threads` | the threads of the fabric (also the tool `threads` of the MCP server `memoria`) |
| `thread <id> ls\|read\|search` | reads a git-remote source at its pinned ref, without cloning it |
| `seed [--apply --yes]` | the `hub/seed.toml` of every industry into the hub (route `admin/seed`, administrators): a dry run, then the writes |
| `mcp` | the MCP server `memoria` over stdio: the rules of the session as instructions, the memory as tools |
| `run-thread <id>` | started by the assistants: an MCP thread with its credentials, so no token is written in a configuration file |
| `whoami`, `rules`, `context`, `search`, `read`, `note`, `lesson`, `task`, `task-note`, `log-time`, `update`, `review`, `documents`, `document-write`, `sources-*`, … | the memory, as the person: every write needs `--yes` after the person agreed |

Outside a fabric the CLI takes the hub from `TEXO_HUB_URL` and `TEXO_HUB_TOKEN`.

## Contents

| Path | What |
|---|---|
| `AGENTS.md` | the rules of every agent in a fabric (the customer imports it) |
| `texo/` | the CLI: `hub.py` (the memory client and the MCP server), `config.py` (`texo.toml` and credentials), `threads.py` (drivers), `mount.py`, `seed.py`, `bridge.py` |
| `docs/` | `memoria.md` (the model of the memory), `fili.md` (threads), `ARCHITECTURE.md`, `blueprint.md` |
| `skills/` | `texo-sessione`, `memoria-consolidamento`, `memoria-ingestione`, `memoria-fonti` |
| `playbooks/` | a new memory system, its profile, the evaluation of the memory, the local coordination Odoo, the review of the knowledge |
| `scripts/` | `ingest.py` (documents into the memory, Docling or light converters), `eval_memoria.py` and `eval_varianti.py` (the measure of the search), the checks every Texo repository runs (`check_isolation.py`, `check_agents.py`, `check_skills.py`, `check_okf.py`, `check_attribution.py`) |
| `setup/` | `bootstrap.sh`, `install-git-hooks.sh`, `coordinamento-up.sh` (a local coordination Odoo with texo_hub at a release), `install-docling.sh` |

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
