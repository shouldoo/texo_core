"""Tests of the fabric: texo.toml, the threads, mount, doctor, seed and the bridge (no hub, no network)."""
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
from texo import __version__, bridge, cli, mount, seed, threads  # noqa: E402
from texo.config import ConfigError, Fabric, find_root, hub_settings  # noqa: E402

CORE = Path(__file__).resolve().parent.parent

TOML = f"""
[texo]
customer = "acme"
core = "v{__version__}"
hub_url = "http://hub.test"
hub_token = "env:ACME_HUB_TOKEN"

[[industry]]
name = "bakery"
version = "v1.2.0"

[[thread]]
id = "laws"
type = "source"
driver = "git-mirror"
repo = "{{mirror}}"
ref = "v1"
data_class = "public"
guide = "Food safety acts: search, read the article, cite it."

[[thread]]
id = "drive"
type = "connector"
driver = "mcp-http"
url = "https://drive.example/mcp"
auth = "env:ACME_DRIVE_TOKEN"
data_class = "customer"
writes = "confirm"
guide = "Documents of the customers: read, never copy them locally."

[[thread]]
id = "news"
type = "source"
driver = "http"
url = "https://news.example/feed"
data_class = "public"
hub_channel = true
guide = "The local paper."
"""

MANIFEST = f"""
[industry]
name = "bakery"
version = "v1.2.0"
core = ">={__version__}, <2"

[[suggested_thread]]
id = "recipes"
why = "the recipe book of the sector"
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


class FabricCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.patch = unittest.mock.patch.dict(os.environ, {
            "TEXO_SHARED_DIR": str(self.tmp / "shared"), "TEXO_CONFIG_DIR": str(self.tmp / "config"),
            "TEXO_AGY_PROFILE": str(self.tmp / "no-profile"), "ACME_HUB_TOKEN": "secret-hub"})
        self.patch.start()
        os.environ.pop("TEXO_ROOT", None)
        os.environ.pop("ACME_DRIVE_TOKEN", None)
        self.mirror = self.tmp / "upstream"
        self.mirror.mkdir()
        git("init", "--quiet", cwd=self.mirror)
        (self.mirror / "act.md").write_text("Art. 1. Allergens are listed.\n")
        git("add", ".", cwd=self.mirror)
        git("commit", "--quiet", "-m", "acts", cwd=self.mirror)
        git("tag", "v1", cwd=self.mirror)
        self.root = self.tmp / "acme"
        (self.root / "industry" / "bakery" / "hub").mkdir(parents=True)
        (self.root / "texo.toml").write_text(TOML.replace("{mirror}", str(self.mirror)))
        (self.root / "industry" / "bakery" / "texo_industry.toml").write_text(MANIFEST)
        (self.root / "industry" / "bakery" / "hub" / "seed.toml").write_text(SEED)

    def tearDown(self):
        self.patch.stop()

    def fabric(self):
        return Fabric(self.root)


class TestConfig(FabricCase):

    def test_the_root_is_found_from_a_subfolder_and_the_token_from_the_environment(self):
        (self.root / "docs").mkdir()
        self.assertEqual(find_root(self.root / "docs"), self.root)
        self.assertEqual(hub_settings(self.root / "docs"), ("http://hub.test", "secret-hub"))

    def test_a_credential_comes_from_the_env_file_of_the_customer_never_from_a_file_others_read(self):
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

    def test_the_customer_is_a_slug(self):
        (self.root / "texo.toml").write_text('[texo]\ncustomer = "Acme Srl"\n')
        with self.assertRaises(ConfigError):
            self.fabric()


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


class TestMount(FabricCase):

    def test_versions_requirements_and_suggestions_of_the_industries(self):
        problems = mount.check_fabric(self.fabric())
        self.assertEqual([p for p in problems if p[0] == "error"], [])
        self.assertIn(("info", "industry bakery suggests the thread recipes: the recipe book of the sector"), problems)
        (self.root / "texo.toml").write_text((self.root / "texo.toml").read_text().replace('"v1.2.0"', '"v1.3.0"')
                                             .replace(f'core = "v{__version__}"', 'core = "v0.9.0"'))
        errors = [m for level, m in mount.check_fabric(self.fabric()) if level == "error"]
        self.assertTrue(any("the mounted core is" in m for m in errors))
        self.assertTrue(any("the submodule is v1.2.0" in m for m in errors))

    def test_mount_clones_the_mirror_writes_the_assistants_and_the_index(self):
        out = io.StringIO()
        (self.root / ".mcp.json").write_text(json.dumps({"mcpServers": {"mine": {"command": "x"}}}))
        self.assertEqual(mount.mount(self.fabric(), out=out), 0, out.getvalue())
        mirror = self.tmp / "shared" / "mirrors" / "laws"
        self.assertTrue((mirror / "act.md").is_file())
        servers = json.loads((self.root / ".mcp.json").read_text())["mcpServers"]
        self.assertEqual(sorted(servers), ["drive", "memoria", "mine"], "what the person set stays")
        self.assertEqual(servers["drive"]["args"][-2:], ["run-thread", "drive"])
        self.assertNotIn("secret", json.dumps(servers), "no credential in a configuration file")
        self.assertIn("drive", json.loads((self.root / ".gemini" / "settings.json").read_text())["mcpServers"])
        index = (self.root / ".texo" / "THREADS.md").read_text()
        self.assertIn(f"`rg` in `{mirror}`", index)
        self.assertIn("| `drive` (warning) | connector | customer | confirm |", index)
        self.assertIn("ACME_DRIVE_TOKEN is not set", out.getvalue())
        # a thread removed from texo.toml leaves the assistants at the next mount
        text = (self.root / "texo.toml").read_text()
        (self.root / "texo.toml").write_text(text[:text.index('[[thread]]\nid = "drive"')])
        mount.mount(self.fabric(), out=io.StringIO())
        self.assertEqual(sorted(json.loads((self.root / ".mcp.json").read_text())["mcpServers"]), ["memoria", "mine"])

    def test_a_declaration_error_mounts_nothing(self):
        (self.root / "texo.toml").write_text((self.root / "texo.toml").read_text().replace(
            'auth = "env:ACME_DRIVE_TOKEN"', 'auth = "abc123"'))
        out = io.StringIO()
        self.assertEqual(mount.mount(self.fabric(), out=out), 1)
        self.assertFalse((self.root / ".mcp.json").exists())
        self.assertIn("Nothing mounted", out.getvalue())

    def test_doctor_reports_the_missing_mirror_and_the_missing_credential(self):
        out = io.StringIO()
        with unittest.mock.patch.object(threads, "doctor_http", return_value=("ok", "answers 200")):
            self.assertEqual(mount.doctor(self.fabric(), out=out), 1)
        self.assertIn("[error] laws: not mounted", out.getvalue())
        self.assertIn("[error] drive: ACME_DRIVE_TOKEN is not set", out.getvalue())
        self.assertNotIn("secret-hub", out.getvalue())
        mount.mount(self.fabric(), out=io.StringIO())
        os.environ["ACME_DRIVE_TOKEN"] = "x"
        out = io.StringIO()
        with unittest.mock.patch.object(threads, "doctor_http", return_value=("ok", "answers 200")):
            self.assertEqual(mount.doctor(self.fabric(), out=out), 0, out.getvalue())

    def test_the_cli_lists_the_threads_and_refuses_an_unknown_one(self):
        mount.mount(self.fabric(), out=io.StringIO())
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(cli.main(["--root", str(self.root), "threads"], out=out, err=err), 0)
        self.assertIn("laws [source, public, writes never]", out.getvalue())
        self.assertEqual(cli.main(["--root", str(self.root), "thread", "nope", "ls"], out=out, err=err), 1)
        self.assertIn("no thread nope", err.getvalue())


class TestSeed(FabricCase):

    def test_the_seed_goes_to_the_hub_as_a_dry_run_then_applied(self):
        calls = []

        class Hub:
            def call(self, route, payload=None):
                calls.append((route, payload))
                if route == "admin/seed":
                    return {"industry": "bakery", "applied": payload["apply"], "counts": {"created": 2},
                            "items": [{"kind": "rule", "key": "allergens", "name": "Allergens", "status": "created"}]}
                return []

        out = io.StringIO()
        seed.seed(self.fabric(), Hub(), out=out)
        route, payload = calls[0]
        self.assertEqual((route, payload["industry"], payload["apply"]), ("admin/seed", "bakery", False))
        self.assertEqual(payload["rules"][0]["key"], "allergens")
        self.assertEqual([c[0] for c in calls[1:]], ["search_read"], "a dry run creates no channel")
        self.assertIn("(dry run)", out.getvalue())
        calls.clear()
        seed.seed(self.fabric(), Hub(), apply=True, out=io.StringIO())
        self.assertEqual([c[0] for c in calls], ["admin/seed", "search_read", "sources/channel"])
        argv = ["--root", str(self.root), "seed", "--apply"]
        self.assertEqual(cli.main(argv, out=io.StringIO(), err=io.StringIO()), 2,
                         "--apply needs --yes")

    def test_an_unknown_table_is_refused(self):
        (self.root / "industry" / "bakery" / "hub" / "seed.toml").write_text("[[recipes]]\nname = 'x'\n")
        with self.assertRaisesRegex(ConfigError, "unknown tables recipes"):
            seed.payload(self.fabric(), self.fabric().industries[0])


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
