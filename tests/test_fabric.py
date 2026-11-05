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
    def __init__(self, config=None, fail=False):
        self.config, self.fail, self.calls = config or REMOTE, fail, []

    def call(self, route, payload=None):
        from texo.hub import HubError
        self.calls.append((route, payload))
        if self.fail:
            raise HubError(0, "Odoo not reachable")
        if route == "config":
            return json.loads(json.dumps(self.config))
        if route == "admin/seed":
            return {"industry": payload["industry"], "applied": payload["apply"], "counts": {"created": 2},
                    "items": [{"kind": "rule", "key": "allergens", "name": "Allergens", "status": "created"}]}
        return []


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
                                      "packs/bakery/skills/proofing/SKILL.md": "---\nname: proofing\ndescription: d\n---\n",
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


class TestMount(FabricCase):

    def test_mount_installs_the_pack_the_threads_the_assistants_and_the_agent_files(self):
        (self.root / ".mcp.json").write_text(json.dumps({"mcpServers": {"mine": {"command": "x"}}}))
        code, out = self.mount()
        self.assertEqual(code, 0, out)
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
        agents = (self.root / "AGENTS.md").read_text()
        self.assertIn(mount.GENERATED, agents)
        self.assertIn("Skill packs: bakery v1.2.0", agents)
        self.assertNotIn("<core>", agents)
        self.assertIn("@AGENTS.md", (self.root / "CLAUDE.md").read_text())
        ignored = (self.root / ".gitignore").read_text().splitlines()
        self.assertTrue({"recipes/", "AGENTS.md", ".texo/"} <= set(ignored))

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
            self.assertEqual(mount.doctor(self.fabric(), out=out), 1)
        self.assertIn("[error] laws: not mounted", out.getvalue())
        self.mount()
        os.environ["ACME_DRIVE_TOKEN"] = "x"
        out = io.StringIO()
        with unittest.mock.patch.object(threads, "doctor_http", return_value=("ok", "answers 200")):
            self.assertEqual(mount.doctor(self.fabric(), out=out), 0, out.getvalue())
        self.assertIn("[ok] pack bakery v1.2.0: installed", out.getvalue())
        self.assertNotIn("secret-hub", out.getvalue())

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
        self.assertEqual(oct((home / ".claude.json").stat().st_mode & 0o777), "0o600")
        self.assertTrue((folder / "AGENTS.md").is_file() and (folder / ".mcp.json").is_file())
        self.assertEqual(cli.main(["--root", str(folder), "init", "http://127.0.0.1:9", "acme"], out=io.StringIO(),
                                  err=err), 1, "a working folder is initialised once")


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
        self.assertEqual((status, message), ("ok", "MCP server memoria 2.0"))


if __name__ == "__main__":
    unittest.main()
