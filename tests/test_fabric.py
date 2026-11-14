"""Tests of a working folder: texo.toml, the configuration of the hub, the packs of the marketplace, the threads,
mount, doctor, seed and the bridge (no hub, no network: the marketplace and the mirror are local repositories)."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from texo import __version__, bridge, cli, mount, packs, seed, threads  # noqa: E402
from texo.config import ConfigError, Fabric, find_root, hub_settings, write_texo_toml  # noqa: E402

CORE = Path(__file__).resolve().parent.parent

TOML = """
[texo]
organisation = "acme"
hub_url = "http://hub.test"
hub_token = "env:ACME_HUB_TOKEN"
marketplace = "{marketplace}"

[[thread]]
id = "laws"
type = "source"
driver = "git-mirror"
repo = "{mirror}"
ref = "v1"
data_class = "public"
guide = "Food safety acts: search, read the article, cite it."
"""

# what the route config of the hub answers for the organisation
REMOTE = {
    "organisation": "acme",
    "packs": [{"name": "bakery", "version": "v1.2.0"}],
    "threads": [
        {"id": "drive", "type": "connector", "driver": "mcp-http", "url": "https://drive.example/mcp",
         "auth": "env:ACME_DRIVE_TOKEN", "data_class": "customer", "writes": "confirm",
         "guide": "Documents of the customers: read, never copy them locally."},
        {"id": "news", "type": "source", "driver": "http", "url": "https://news.example/feed", "data_class": "public",
         "writes": "never", "hub_channel": True, "guide": "The local paper."},
        {"id": "laws", "type": "source", "driver": "http", "url": "https://laws.example", "data_class": "public",
         "writes": "never", "guide": "replaced by the local declaration"},
    ],
}

PACK = f"""
[pack]
name = "bakery"
version = "v1.2.0"
core = ">={__version__}, <99"
work_dirs = ["recipes"]

[[suggested_thread]]
id = "suppliers"
why = "the catalogues of the suppliers"
"""

SEED = """
[[activities]]
code = "baking"
name = "Baking"

[[rules]]
key = "allergens"
name = "Allergens"
body = "Never publish a recipe without its allergens."
severity = "never"
"""


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                            GIT_COMMITTER_EMAIL="t@t"))


def repository(path, files, tag):
    path.mkdir(parents=True)
    git("init", "--quiet", cwd=path)
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
    git("add", ".", cwd=path)
    git("commit", "--quiet", "-m", "content", cwd=path)
    git("tag", tag, cwd=path)


class FakeHub:
    def __init__(self, config=None, fail=False, status=0):
        self.config, self.fail, self.status, self.calls = config or REMOTE, fail, status, []

    def call(self, route, payload=None):
        from texo.hub import HubError
        self.calls.append((route, payload))
        if self.fail:
            raise HubError(self.status, "the token is invalid or expired" if self.status == 401 else "Odoo not reachable")
        if route == "whoami":
            return {"uid": 7, "login": "lead@acme.example", "name": "Lead", "role": "lead"}
        if route == "config":
            return json.loads(json.dumps(self.config))
        if route == "admin/seed":
            return {"industry": payload["industry"], "applied": payload["apply"], "counts": {"created": 2},
                    "items": [{"kind": "rule", "key": "allergens", "name": "Allergens", "status": "created"}]}
        return []


PROOFING = ("---\nname: proofing\ndescription: >-\n  The rising of the dough, from the mix to the oven. Use it when a batch\n"
            "  does not rise. Triggers: \"lievitazione\".\n---\n\n# proofing\n")


class FabricCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = unittest.mock.patch.dict(os.environ, {
            "TEXO_SHARED_DIR": str(self.tmp / "shared"), "TEXO_CONFIG_DIR": str(self.tmp / "config"),
            "TEXO_AGY_PROFILE": str(self.tmp / "no-profile"), "ACME_HUB_TOKEN": "secret-hub"})
        self.patch.start()
        for name in ("TEXO_ROOT", "ACME_DRIVE_TOKEN", "TEXO_MARKETPLACE"):
            os.environ.pop(name, None)
        self.mirror = self.tmp / "upstream"
        repository(self.mirror, {"act.md": "Art. 1. Allergens are listed.\n",
                                 "skills/upstream-guide/SKILL.md": "---\nname: upstream-guide\ndescription: d\n---\n",
                                 "big/file.txt": "not wanted"}, "v1")
        self.marketplace = self.tmp / "marketplace"
        repository(self.marketplace, {"packs/bakery/pack.toml": PACK, "packs/bakery/seed.toml": SEED,
                                      "packs/bakery/skills/proofing/SKILL.md": PROOFING,
                                      "packs/bakery/DESIGN.md": "# Stile del pacchetto\n\n- Le ricette in grammi.\n",
                                      "packs/other/pack.toml": "[pack]\nname = 'other'\n"}, "bakery-v1.2.0")
        self.root = self.tmp / "acme"
        self.root.mkdir()
        (self.root / "texo.toml").write_text(TOML.format(marketplace=self.marketplace, mirror=self.mirror))

    def tearDown(self):
        self.patch.stop()

    def fabric(self):
        return Fabric(self.root)

    def mount(self, hub=None, **kwargs):
        out = io.StringIO()
        code = mount.mount(self.fabric(), out=out, client=hub or FakeHub(), **kwargs)
        return code, out.getvalue()


class TestConfig(FabricCase):

    def test_the_root_is_found_from_a_subfolder_and_the_token_from_the_environment(self):
        (self.root / "docs").mkdir()
        self.assertEqual(find_root(self.root / "docs"), self.root)
        self.assertEqual(hub_settings(self.root / "docs"), ("http://hub.test", "secret-hub"))

    def test_a_credential_comes_from_the_env_file_of_the_organisation_never_from_a_file_others_read(self):
        env = self.tmp / "config" / "acme.env"
        env.parent.mkdir()
        env.write_text("ACME_DRIVE_TOKEN=from-file\n")
        os.chmod(env, 0o644)
        with self.assertRaisesRegex(ConfigError, "chmod 600"):
            self.fabric().secret("env:ACME_DRIVE_TOKEN")
        os.chmod(env, 0o600)
        self.assertEqual(self.fabric().secret("env:ACME_DRIVE_TOKEN"), "from-file")
        with self.assertRaisesRegex(ConfigError, "env:NAME"):
            self.fabric().secret("plain-value")

    def test_the_organisation_is_a_slug(self):
        (self.root / "texo.toml").write_text('[texo]\norganisation = "Acme Srl"\n')
        with self.assertRaises(ConfigError):
            self.fabric()

    def test_init_writes_the_hub_and_the_organisation_only(self):
        folder = self.tmp / "new"
        folder.mkdir()
        path = write_texo_toml(folder, "acme", "https://memoria.example.org/")
        fabric = Fabric(folder)
        self.assertEqual((fabric.organisation, fabric.texo["hub_url"]), ("acme", "https://memoria.example.org"))
        with self.assertRaisesRegex(ConfigError, "exists"):
            write_texo_toml(folder, "acme", "https://memoria.example.org")
        self.assertNotIn("TOKEN=", path.read_text())

    def test_the_hub_lists_the_configuration_and_texo_toml_adds_or_replaces(self):
        self.mount()
        fabric = self.fabric()
        self.assertEqual([p["name"] for p in fabric.packs], ["bakery"])
        threads_by_id = {t["id"]: t for t in fabric.threads}
        self.assertEqual(sorted(threads_by_id), ["drive", "laws", "news"])
        self.assertEqual((threads_by_id["laws"]["driver"], threads_by_id["laws"]["origin"]), ("git-mirror", "local"))
        self.assertEqual(threads_by_id["drive"]["origin"], "hub")


class TestThreadDeclarations(unittest.TestCase):

    def errors(self, **thread):
        base = {"id": "t", "type": "source", "driver": "http", "url": "https://x", "data_class": "public", "guide": "g"}
        return [message for level, message in threads.check(dict(base, **thread)) if level == "error"]

    def test_a_valid_thread_has_no_error(self):
        self.assertEqual(self.errors(), [])

    def test_the_rules_of_a_declaration(self):
        self.assertTrue(self.errors(writes="confirm"), "a source is read only")
        self.assertTrue(self.errors(type="connector", writes="confirm"), "a connector is never public")
        self.assertTrue(self.errors(driver="mcp-stdio", command="npx", args=["-y", "some-server"]),
                        "a package installed on the fly is pinned")
        self.assertFalse(self.errors(driver="mcp-stdio", command="npx", args=["-y", "@scope/server@1.4.2"]))
        self.assertTrue(self.errors(type="connector", driver="mcp-http", data_class="org", auth="abc123"),
                        "a credential is never written as its value")
        self.assertTrue(self.errors(driver="mcp-stdio", command="srv", env={"API_TOKEN": "abc"}))
        self.assertTrue(self.errors(driver="git-remote"), "a git source needs repo and ref")
        self.assertTrue(self.errors(data_class="secret"))
        self.assertTrue(self.errors(skills="skills"), "skills belong to a git-mirror")
        self.assertTrue(self.errors(driver="git-mirror", repo="r", ref="v1", paths=["docs"], skills="skills"),
                        "skills outside the paths checked out")
        self.assertFalse(self.errors(driver="git-mirror", repo="r", ref="v1", paths=["skills"], skills="skills"))
        self.assertFalse(self.errors(data_class="personal"), "the data of the person: a class of its own")
        self.assertFalse(self.errors(type="connector", driver="mcp-http", data_class="personal", writes="confirm"),
                         "a connector may hold the data of the person")


class TestMount(FabricCase):

    def test_mount_installs_the_pack_the_threads_the_assistants_and_the_agent_files(self):
        (self.root / ".mcp.json").write_text(json.dumps({"mcpServers": {"mine": {"command": "x"}}}))
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.local.json").write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]},
                                                                               "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}))
        code, out = self.mount()
        self.assertEqual(code, 0, out)
        settings = json.loads((self.root / ".claude" / "settings.local.json").read_text())
        self.assertEqual(settings["permissions"], {"allow": ["Bash(ls)"]}, "what the person set stays")
        self.assertEqual([h["command"] for e in settings["hooks"]["Stop"] for h in e["hooks"]][0], "mine")
        self.assertTrue(settings["hooks"]["Stop"][1]["hooks"][0]["command"].endswith(f"--root {self.root} hook stop"))
        self.assertEqual(sorted(settings["hooks"]), ["PreCompact", "SessionEnd", "Stop"])
        code, out = self.mount()
        self.assertEqual(len(json.loads((self.root / ".claude" / "settings.local.json").read_text())["hooks"]["Stop"]), 2,
                         "mounted twice, written once")
        pack = packs.folder(self.fabric(), {"name": "bakery", "version": "v1.2.0"})
        self.assertTrue((pack / "seed.toml").is_file())
        self.assertFalse((pack.parent / "other").exists(), "only the folder of the pack is checked out")
        self.assertIn("pack bakery suggests the thread suppliers: the catalogues of the suppliers", out)
        self.assertTrue((self.tmp / "shared" / "mirrors" / "laws" / "act.md").is_file())
        servers = json.loads((self.root / ".mcp.json").read_text())["mcpServers"]
        self.assertEqual(sorted(servers), ["drive", "memoria", "mine"], "what the person set stays")
        self.assertEqual(servers["drive"]["args"][-2:], ["run-thread", "drive"])
        self.assertNotIn("secret", json.dumps(servers), "no credential in a configuration file")
        index = (self.root / ".texo" / "THREADS.md").read_text()
        self.assertIn("| `drive` (warning) | connector | customer | confirm |", index)
        self.assertIn("ACME_DRIVE_TOKEN is not set", out)
        self.assertTrue((self.root / "recipes").is_dir(), "the working folders of the pack")
        for base in mount.SKILL_DIRS:
            self.assertTrue((self.root / base / "proofing" / "SKILL.md").is_file())
            self.assertTrue((self.root / base / "texo-sessione").exists() or not (CORE / "skills").is_dir())
        files = {name: (self.root / name).read_text() for name in mount.AGENT_FILES}
        for name, text in files.items():
            self.assertIn(mount.GENERATED, text, name)
            self.assertNotIn("<core>", text, name)
        self.assertIn("## All'apertura della cartella", files["AGENTS.md"], "the limits say what to read first")
        self.assertNotIn("## La cartella di lavoro", files["AGENTS.md"], "the infrastructure is in ARCHITECTURE.md")
        self.assertIn("- Pacchetti: `bakery` v1.2.0.", files["ARCHITECTURE.md"])
        self.assertIn("- Organizzazione: `acme`", files["ARCHITECTURE.md"])
        pack_skills = packs.folder(self.fabric(), {"name": "bakery", "version": "v1.2.0"}) / "skills"
        self.assertIn(f"- pacchetto bakery: `{pack_skills}/`: `proofing`.", files["ARCHITECTURE.md"],
                      "the skills by the folder they come from, with its full path")
        self.assertIn(f"- `{self.root / '.agents/skills'}/`", files["ARCHITECTURE.md"])
        architecture = files["ARCHITECTURE.md"]
        self.assertLess(architecture.index("- core: `"), architecture.index("- pacchetto bakery: `"),
                        "the origins in the order of precedence")
        self.assertFalse((self.root / "SKILLS.md").exists(), "each skill speaks for itself in its SKILL.md")
        self.assertIn("- Comincia un task con la skill `texo-sessione`", files["AGENTS.md"])
        design = files["DESIGN.md"]
        self.assertIn("### Pacchetto `bakery`\n\n- Le ricette in grammi.", design)
        self.assertLess(design.index("## Lo stile dei pacchetti"), design.index("## Lo stile dell'organizzazione"))
        self.assertNotIn("# Stile del pacchetto", design, "the title of the pack's file is the section")
        pointer = (self.root / "CLAUDE.md").read_text()
        self.assertEqual([line for line in pointer.splitlines() if line.startswith("@")],
                         ["@AGENTS.md", "@ARCHITECTURE.md", "@DESIGN.md", "@.texo/THREADS.md"])
        self.assertEqual(pointer, (self.root / "GEMINI.md").read_text())
        ignored = (self.root / ".gitignore").read_text().splitlines()
        self.assertTrue({"recipes/", "AGENTS.md", "ARCHITECTURE.md", "DESIGN.md", ".texo/",
                         ".claude/settings.local.json"} <= set(ignored))

    def test_a_pack_under_development_is_used_from_its_folder(self):
        local = self.tmp / "dev-marketplace" / "packs" / "bakery"
        (local / "skills" / "proofing").mkdir(parents=True)
        (local / "pack.toml").write_text(PACK)
        (local / "seed.toml").write_text(SEED)
        (local / "skills" / "proofing" / "SKILL.md").write_text("---\nname: proofing\ndescription: d\n---\n")
        toml = self.root / "texo.toml"
        toml.write_text(toml.read_text() + f'\n[[pack]]\nname = "bakery"\nversion = "v1.2.0"\npath = "{local}"\n')
        code, out = self.mount()
        self.assertEqual(code, 0, out)
        self.assertIn(f"[ok] pack bakery v1.2.0: a pack under development, used as it is: {local}", out)
        self.assertEqual(packs.folder(self.fabric(), self.fabric().packs[0]), local)
        self.assertFalse((self.tmp / "shared" / "mirrors" / "pack-bakery-v1.2.0").exists(), "nothing checked out")
        for base in mount.SKILL_DIRS:
            self.assertTrue((self.root / base / "proofing" / "SKILL.md").is_file())
        (local / "pack.toml").unlink()
        code, out = self.mount()
        self.assertEqual(code, 1)
        self.assertIn(f"[error] pack bakery v1.2.0: no pack.toml in {local}", out)

    def pack_with_threads(self, threads_toml):
        """The pack bakery v1.2.0 in another marketplace, carrying the given [[thread]] declarations."""
        marketplace = self.tmp / "marketplace-threads"
        repository(marketplace, {"packs/bakery/pack.toml": PACK + threads_toml, "packs/bakery/seed.toml": SEED},
                   "bakery-v1.2.0")
        toml = self.root / "texo.toml"
        toml.write_text(toml.read_text().replace(str(self.marketplace), str(marketplace)))

    def test_a_pack_declares_the_commands_that_count_as_a_check(self):
        self.pack_with_threads("""
[[check]]
name = "oven tests"
pattern = 'oven\\s+--test'
""")
        code, out = self.mount()
        self.assertEqual(code, 0, out)
        self.assertIn("[ok] checks of the packs: oven tests", out)
        written = json.loads((self.root / ".texo" / "checks.json").read_text())
        self.assertEqual(written, {"checks": [{"name": "oven tests", "pattern": "oven\\s+--test",
                                               "origin": "pack bakery"}]})
        from texo import hooks
        self.assertEqual(hooks.check_of("oven  --test all", hooks.load_checks(self.root)), "oven tests")
        self.assertEqual(mount.check_problems({"name": "x", "pattern": "("})[0][:38],
                         "check x: pattern is a regular expressi")
        self.assertEqual(mount.check_problems({"pattern": "x"}), ["a [[check]] has a name"])
        self.assertEqual(mount.check_problems({"name": "x"})[0][:16], "check x: pattern")

    def test_a_pack_carries_its_threads_and_the_hub_may_replace_them(self):
        self.pack_with_threads(f"""
[[thread]]
id = "guides"
type = "source"
driver = "git-mirror"
repo = "{self.mirror}"
ref = "v1"
skills = "skills"
data_class = "public"
guide = "The guides of the sector."
""")
        code, out = self.mount()
        self.assertEqual(code, 0, out)
        self.assertIn("[ok] guides: cloned v1", out)
        for base in mount.SKILL_DIRS:
            self.assertTrue((self.root / base / "upstream-guide" / "SKILL.md").is_file(), "its skills are linked")
        self.assertIn("- filo guides: `", (self.root / "ARCHITECTURE.md").read_text(), "and their folder named")
        guides = next(t for t in self.fabric().threads if t["id"] == "guides")
        self.assertEqual(guides["origin"], "pack bakery")
        config = json.loads(json.dumps(REMOTE))
        config["threads"].append({"id": "guides", "type": "source", "driver": "git-mirror", "repo": str(self.mirror),
                                  "ref": "v1", "skills": "skills", "data_class": "public", "guide": "Ours."})
        code, out = self.mount(hub=FakeHub(config))
        self.assertEqual(code, 0, out)
        guides = next(t for t in self.fabric().threads if t["id"] == "guides")
        self.assertEqual((guides["origin"], guides["guide"]), ("hub", "Ours."), "the hub replaces the pack's")

    def test_a_pack_carries_no_connector(self):
        self.pack_with_threads("""
[[thread]]
id = "inbox"
type = "connector"
driver = "mcp-http"
url = "https://mail.example/mcp"
data_class = "customer"
writes = "confirm"
guide = "The mail of the customers."
""")
        code, out = self.mount()
        self.assertEqual(code, 1, out)
        self.assertIn("inbox: a pack bakery carries only public sources", out)
        self.assertIn("Nothing mounted", out)

    def test_the_files_the_person_wrote_are_never_overwritten(self):
        (self.root / "AGENTS.md").write_text("# Our rules\n")
        code, out = self.mount()
        self.assertEqual((self.root / "AGENTS.md").read_text(), "# Our rules\n")
        self.assertIn("AGENTS.md is yours", out)
        self.assertNotIn("AGENTS.md", (self.root / ".gitignore").read_text().splitlines())

    def test_without_the_hub_the_configuration_read_last_time_is_used(self):
        self.mount()
        code, out = self.mount(hub=FakeHub(fail=True))
        self.assertEqual(code, 0, out)
        self.assertIn("the configuration read on", out)
        self.assertEqual(sorted(t["id"] for t in self.fabric().threads), ["drive", "laws", "news"])

    def test_a_pack_that_needs_another_core_or_another_version_mounts_nothing(self):
        config = json.loads(json.dumps(REMOTE))
        config["packs"] = [{"name": "bakery", "version": "v1.3.0"}]
        code, out = self.mount(hub=FakeHub(config))
        self.assertEqual(code, 1)
        self.assertIn("pack bakery", out)
        self.assertFalse((self.root / ".mcp.json").exists())

    def test_a_thread_removed_from_the_hub_leaves_the_assistants(self):
        self.mount()
        config = json.loads(json.dumps(REMOTE))
        config["threads"] = [t for t in config["threads"] if t["id"] != "drive"]
        self.mount(hub=FakeHub(config))
        self.assertNotIn("drive", json.loads((self.root / ".mcp.json").read_text())["mcpServers"])

    def test_a_declaration_error_mounts_nothing(self):
        config = json.loads(json.dumps(REMOTE))
        config["threads"][0]["auth"] = "abc123"
        code, out = self.mount(hub=FakeHub(config))
        self.assertEqual(code, 1)
        self.assertIn("Nothing mounted", out)

    def test_doctor_reports_what_is_missing(self):
        out = io.StringIO()
        with unittest.mock.patch.object(threads, "doctor_http", return_value=("ok", "answers 200")):
            self.assertEqual(mount.doctor(self.fabric(), out=out, client=FakeHub()), 1)
        self.assertIn("[error] laws: not mounted", out.getvalue())
        self.mount()
        os.environ["ACME_DRIVE_TOKEN"] = "x"
        out = io.StringIO()
        with unittest.mock.patch.object(threads, "doctor_http", return_value=("ok", "answers 200")):
            self.assertEqual(mount.doctor(self.fabric(), out=out, client=FakeHub()), 0, out.getvalue())
        self.assertIn("[ok] hub: lead@acme.example, role lead", out.getvalue())
        self.assertIn("[ok] pack bakery v1.2.0: installed", out.getvalue())
        self.assertNotIn("secret-hub", out.getvalue())

    def test_doctor_asks_the_hub_with_the_token(self):
        self.mount()
        os.environ["ACME_DRIVE_TOKEN"] = "x"
        with unittest.mock.patch.object(threads, "doctor_http", return_value=("ok", "answers 200")):
            out = io.StringIO()
            self.assertEqual(mount.doctor(self.fabric(), out=out, client=FakeHub(fail=True, status=401)), 1)
            self.assertIn("[error] hub 401: the token is invalid or expired", out.getvalue())
            out = io.StringIO()
            other = dict(json.loads(json.dumps(REMOTE)), organisation="another")
            self.assertEqual(mount.doctor(self.fabric(), out=out, client=FakeHub(other)), 0, out.getvalue())
            self.assertIn("[warning] the hub names the organisation another, texo.toml acme", out.getvalue())

    def test_the_cli_lists_the_threads_and_says_where_a_pack_is(self):
        self.mount()
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(cli.main(["--root", str(self.root), "threads"], out=out, err=err), 0)
        self.assertIn("laws [source, public, writes never]", out.getvalue())
        out = io.StringIO()
        self.assertEqual(cli.main(["--root", str(self.root), "where", "--pack", "bakery"], out=out, err=err), 0)
        self.assertTrue(out.getvalue().strip().endswith("packs/bakery"))
        self.assertEqual(cli.main(["--root", str(self.root), "thread", "nope", "ls"], out=out, err=err), 1)
        self.assertIn("no thread nope", err.getvalue())


class TestPersonalFolder(FabricCase):
    """A working folder that is also the person's: rules of its own, hooks of its own, personal threads."""

    PERSONAL = """
[[thread]]
id = "google"
type = "connector"
driver = "mcp-http"
url = "http://127.0.0.1:18001/mcp"
data_class = "personal"
writes = "confirm"
guide = "Mail, Drive and calendar of the person."
"""

    HOOK = """
[[hook]]
id = "guard"
event = "PreToolUse"
matcher = "*"
command = "python3 {root}/guard.py --rules '{\\"deny\\": []}'"
"""

    def add(self, text):
        toml = self.root / "texo.toml"
        toml.write_text(toml.read_text() + text)

    def test_the_rules_of_the_person_are_imported_never_written(self):
        code, out = self.mount()
        self.assertNotIn(mount.LOCAL_RULES, (self.root / "AGENTS.md").read_text(), "no file, no mention")
        (self.root / mount.LOCAL_RULES).write_text("# Le mie regole\n")
        for _ in range(2):
            code, out = self.mount()
            self.assertEqual(code, 0, out)
        agents = (self.root / "AGENTS.md").read_text()
        self.assertEqual(agents.count("## Le regole di questa cartella"), 1, "mounted twice, written once")
        self.assertIn(f"`{mount.LOCAL_RULES}`", agents)
        self.assertEqual((self.root / mount.LOCAL_RULES).read_text(), "# Le mie regole\n")
        pointer = (self.root / "CLAUDE.md").read_text()
        self.assertEqual([line for line in pointer.splitlines() if line.startswith("@")],
                         ["@AGENTS.md", f"@{mount.LOCAL_RULES}", "@ARCHITECTURE.md", "@DESIGN.md", "@.texo/THREADS.md"])
        self.assertIn(f"`{mount.LOCAL_RULES}`", (self.root / "ARCHITECTURE.md").read_text())
        self.assertNotIn(mount.LOCAL_RULES, (self.root / ".gitignore").read_text().splitlines(), "it is versioned")
        (self.root / mount.LOCAL_RULES).unlink()
        self.mount()
        self.assertNotIn(mount.LOCAL_RULES, (self.root / "CLAUDE.md").read_text())

    def test_a_hook_of_texo_toml_is_written_once_for_each_assistant(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.local.json").write_text(json.dumps(
            {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]}]}}))
        (self.root / ".agents").mkdir()
        (self.root / ".agents" / "hooks.json").write_text(json.dumps({"start": {"SessionStart": []}}))
        self.add(self.HOOK)
        for _ in range(2):
            code, out = self.mount()
            self.assertEqual(code, 0, out)
        command = f"python3 {self.root}/guard.py --rules '{{\"deny\": []}}'"
        pre = json.loads((self.root / ".claude" / "settings.local.json").read_text())["hooks"]["PreToolUse"]
        self.assertEqual(pre, [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]},
                               {"matcher": "*", "hooks": [{"type": "command", "command": command}]}],
                         "what the person set stays, the hook once")
        agents_hooks = json.loads((self.root / ".agents" / "hooks.json").read_text())
        self.assertEqual(agents_hooks["guard"]["PreToolUse"][0]["hooks"][0]["command"], command)
        self.assertIn("start", agents_hooks, "what the person set stays")
        self.assertIn(".agents/hooks.json", (self.root / ".gitignore").read_text().splitlines())
        self.assertIn("`guard` (PreToolUse)", (self.root / "ARCHITECTURE.md").read_text())
        toml = self.root / "texo.toml"
        toml.write_text(toml.read_text().replace(self.HOOK, ""))
        code, out = self.mount()
        settings = json.loads((self.root / ".claude" / "settings.local.json").read_text())["hooks"]
        self.assertEqual(settings["PreToolUse"], [pre[0]], "a hook removed from texo.toml leaves the assistants")
        self.assertNotIn("guard", json.loads((self.root / ".agents" / "hooks.json").read_text()))

    START = """
[[hook]]
id = "start"
event = "SessionStart"
matcher = "startup"
command = "python3 {root}/start.py"
"""

    def test_the_hooks_file_nests_only_the_hooks_about_a_tool(self):
        self.add(self.HOOK + self.START)
        code, out = self.mount()
        self.assertEqual(code, 0, out)
        written = json.loads((self.root / ".agents" / "hooks.json").read_text())
        self.assertEqual(written["guard"]["PreToolUse"][0]["matcher"], "*")
        self.assertEqual(written["guard"]["PreToolUse"][0]["hooks"][0]["type"], "command")
        self.assertEqual(written["start"], {"SessionStart": [
            {"type": "command", "command": f"python3 {self.root}/start.py"}]},
            "the command itself: the assistant that reads the file refuses all of it on a nested one here")
        start = json.loads((self.root / ".claude" / "settings.local.json").read_text())["hooks"]["SessionStart"]
        self.assertEqual(start[-1]["matcher"], "startup", "the settings of an assistant keep the matcher")
        self.assertEqual(mount.check_hooks_file(self.fabric()), [])
        self.assertEqual(list(written["texo-note"]), ["Stop"], "the hook of the session note, where it is raised")
        note = written["texo-note"]["Stop"][0]
        self.assertEqual(note["type"], "command")
        self.assertTrue(note["command"].endswith(f"texo --root {self.root} hook stop"), note["command"])

    def test_doctor_says_when_the_hooks_file_loads_no_hook(self):
        self.add(self.HOOK)
        self.mount()
        path = self.root / ".agents" / "hooks.json"
        data = json.loads(path.read_text())
        data["start"] = {"SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "x"}]}]}
        path.write_text(json.dumps(data))
        problems = mount.check_hooks_file(self.fabric())
        self.assertEqual([level for level, _ in problems], ["error"])
        self.assertIn("the hook start (SessionStart)", problems[0][1])
        self.assertIn("no hook of the file is loaded", problems[0][1])
        os.environ["ACME_DRIVE_TOKEN"] = "x"
        out = io.StringIO()
        with unittest.mock.patch.object(threads, "doctor_http", return_value=("ok", "answers 200")):
            self.assertEqual(mount.doctor(self.fabric(), out=out, client=FakeHub()), 1)
        self.assertIn("[error] .agents/hooks.json: the hook start (SessionStart)", out.getvalue())
        path.write_text("{not json")
        self.assertIn("cannot be read", mount.check_hooks_file(self.fabric())[0][1])
        self.mount()

    def test_a_hook_comes_only_from_texo_toml_and_is_checked(self):
        config = json.loads(json.dumps(REMOTE))
        config["hooks"] = [{"id": "remote", "event": "PreToolUse", "command": "curl evil"}]
        code, out = self.mount(hub=FakeHub(config))
        self.assertEqual(code, 0, out)
        self.assertIn("the hub lists hooks: ignored", out)
        self.assertNotIn("curl evil", (self.root / ".claude" / "settings.local.json").read_text())
        self.add('\n[[hook]]\nid = "x"\nevent = "BeforeEverything"\ncommand = "true"\n')
        code, out = self.mount()
        self.assertEqual(code, 1)
        self.assertIn("hook x: event is one of", out)

    def test_a_personal_thread_is_declared_only_in_texo_toml(self):
        self.add(self.PERSONAL)
        code, out = self.mount()
        self.assertEqual(code, 0, out)
        self.assertIn("personal threads: google: nothing passes between them and the hub", out)
        index = (self.root / ".texo" / "THREADS.md").read_text()
        self.assertIn("| `google` | connector | personal | confirm |", index)
        self.assertIn("nulla passa tra un", index)
        config = json.loads(json.dumps(REMOTE))
        config["threads"].append({"id": "family", "type": "source", "driver": "http", "url": "https://f",
                                  "data_class": "personal", "writes": "never", "guide": "g"})
        code, out = self.mount(hub=FakeHub(config))
        self.assertEqual(code, 1)
        self.assertIn("family: a personal thread is declared only in texo.toml", out)


class TestInit(FabricCase):

    def test_init_makes_a_working_folder_and_mounts_it_even_without_the_hub(self):
        folder, home = self.tmp / "work", self.tmp / "home"
        folder.mkdir()
        home.mkdir()
        out, err = io.StringIO(), io.StringIO()
        with unittest.mock.patch.dict(os.environ, {"HOME": str(home), "PATH": "/usr/bin:/bin"}):
            code = cli.main(["--root", str(folder), "init", "http://127.0.0.1:9", "acme"], out=out, err=err)
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        self.assertIn("only texo.toml is used", out.getvalue())
        trusted = json.loads((home / ".claude.json").read_text())["projects"][str(folder)]
        self.assertTrue(trusted["hasTrustDialogAccepted"])
        self.assertEqual(trusted["enabledMcpjsonServers"], ["memoria"], "only the server of the core")
        self.assertEqual(oct((home / ".claude.json").stat().st_mode & 0o777), "0o600")
        self.assertTrue((folder / "AGENTS.md").is_file() and (folder / ".mcp.json").is_file())
        self.assertEqual(cli.main(["--root", str(folder), "init", "http://127.0.0.1:9", "acme"], out=io.StringIO(),
                                  err=err), 1, "a working folder is initialised once")


class TestConfigCommands(FabricCase):

    def test_config_set_sends_the_lists_of_the_file_and_applies_only_with_yes(self):
        path = self.tmp / "config.toml"
        path.write_text('[texo]\norganisation = "acme"\n\n[[pack]]\nname = "bakery"\nversion = "v1.2.0"\n')
        payload = cli.config_payload(path, apply=False)
        self.assertEqual(payload, {"apply": False, "packs": [{"name": "bakery", "version": "v1.2.0"}], "slug": "acme"})
        self.assertNotIn("threads", payload, "a list left out of the file is not touched in the hub")
        argv = ["--root", str(self.root), "config-set", str(path), "--apply"]
        self.assertEqual(cli.main(argv, out=io.StringIO(), err=io.StringIO()), 2, "--apply needs --yes")
        (self.tmp / "empty.toml").write_text("# nothing\n")
        with self.assertRaisesRegex(ConfigError, "nothing to set"):
            cli.config_payload(self.tmp / "empty.toml", apply=True)
        answer = {"applied": False, "counts": {"created": 1}, "items": [
            {"kind": "pack", "key": "bakery", "status": "created"}, {"kind": "thread", "key": "x", "status": "unchanged"}]}
        self.assertEqual(cli.render_changes(answer).splitlines(), ["1 created (dry run: texo config-set <file> --apply --yes)",
                                                                   "  [created] pack bakery"])


class TestSeed(FabricCase):

    def test_the_seed_of_the_packs_goes_to_the_hub_as_a_dry_run_then_applied(self):
        self.mount()
        hub = FakeHub()
        out = io.StringIO()
        seed.seed(self.fabric(), hub, out=out)
        routes = [route for route, _ in hub.calls]
        self.assertEqual(routes, ["admin/seed", "search_read"], "a dry run creates no channel")
        self.assertEqual(hub.calls[0][1]["rules"][0]["key"], "allergens")
        self.assertIn("(dry run)", out.getvalue())
        hub.calls.clear()
        seed.seed(self.fabric(), hub, apply=True, out=io.StringIO())
        self.assertEqual([route for route, _ in hub.calls], ["admin/seed", "search_read", "sources/channel"])
        argv = ["--root", str(self.root), "seed", "--apply"]
        self.assertEqual(cli.main(argv, out=io.StringIO(), err=io.StringIO()), 2, "--apply needs --yes")

    def test_an_unknown_table_is_refused(self):
        self.mount()
        folder = packs.folder(self.fabric(), {"name": "bakery", "version": "v1.2.0"})
        (folder / "seed.toml").write_text("[[recipes]]\nname = 'x'\n")
        with self.assertRaisesRegex(ConfigError, "unknown tables recipes"):
            seed.payload(self.fabric(), self.fabric().packs[0])


class TestBridge(unittest.TestCase):

    def test_server_sent_events_become_messages(self):
        body = 'event: message\ndata: {"jsonrpc": "2.0", "id": 1, "result": {}}\n\n'
        self.assertEqual(list(bridge.events(body)), [{"jsonrpc": "2.0", "id": 1, "result": {}}])

    def test_the_mcp_server_memoria_answers_the_handshake_of_doctor(self):
        status, message = threads.mcp_stdio_handshake(
            [str(CORE / "bin" / "texo"), "mcp"], env=dict(os.environ, TEXO_HUB_URL="http://127.0.0.1:9",
                                                          TEXO_HUB_TOKEN="x"), cwd=tempfile.mkdtemp())
        self.assertEqual((status, message), ("ok", f"MCP server memoria {__version__}"))


if __name__ == "__main__":
    unittest.main()
