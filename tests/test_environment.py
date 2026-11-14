"""The key of the machine: made with ssh-keygen, proved to the hub, turned into a token that renews itself."""
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import urllib.error
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE))

from texo import cli, environment, hub, mount  # noqa: E402
from texo.config import ConfigError, Fabric  # noqa: E402

HUB = "http://hub.example"
SOON = "%Y-%m-%d %H:%M:%S"


class Response:
    def __init__(self, body):
        self.body = json.dumps(body)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body.encode()


class FakeRegistry:
    """The two open routes of a hub, and a bearer route, as an opener: it knows the keys it was told, checks a
    signature as ssh-keygen does, and gives tokens that it can let expire."""

    def __init__(self, hours=12):
        self.known, self.challenges, self.tokens, self.calls, self.hours = {}, {}, {}, [], hours
        self.issued = 0

    def authorize(self, organisation, state="authorized"):
        self.known[environment.fingerprint(environment.public_key(organisation))] = state

    def refuse(self, request, code, message):
        raise urllib.error.HTTPError(request.full_url, code, message, {}, io.BytesIO(
            json.dumps({"message": message}).encode()))

    def verified(self, print_, signature, message):
        """Whether signature is the one of message by the key with this fingerprint, in the namespace of Texo."""
        with tempfile.NamedTemporaryFile("w", suffix=".sig", delete=False) as handle:
            handle.write(signature)
        try:
            result = subprocess.run(["ssh-keygen", "-Y", "check-novalidate", "-n", environment.NAMESPACE, "-s",
                                     handle.name], input=message, capture_output=True, text=True)
        finally:
            os.unlink(handle.name)
        return result.returncode == 0 and print_ in result.stdout

    def __call__(self, request, timeout=None):
        path = request.full_url.removeprefix(HUB)
        data = json.loads(request.data or b"{}")
        self.calls.append(path)
        if path == "/texo/environment/challenge":
            nonce = f"nonce-{len(self.calls)}"
            self.challenges[data.get("fingerprint")] = nonce
            return Response({"challenge": nonce, "namespace": environment.NAMESPACE})
        if path == "/texo/environment/token":
            print_ = data.get("fingerprint")
            nonce = self.challenges.pop(print_, None)
            if self.known.get(print_) != "authorized" or not nonce or not self.verified(print_, data.get("signature"), nonce):
                self.refuse(request, 403, "The environment is not known, not authorized, or did not prove its key.")
            self.issued += 1
            token = f"token-{self.issued}"
            self.tokens = {token: print_}          # the token before it is deleted
            until = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=self.hours)
            return Response({"token": token, "expires": until.strftime(SOON), "login": "lead", "environment": "laptop"})
        bearer = (request.get_header("Authorization") or "").removeprefix("Bearer ")
        if bearer not in self.tokens:
            self.refuse(request, 401, "invalid token")
        if path == "/texo/v1/environment":
            return Response({"environment": "laptop", "state": "authorized", "fingerprint": self.tokens[bearer],
                             "expires": "2026-11-15 08:00:00", "required": False})
        return Response({"uid": 7, "login": "lead", "role": "lead"})


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is not installed")
class TestEnvironment(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = unittest.mock.patch.dict(os.environ, {
            "TEXO_CONFIG_DIR": str(self.tmp / "config"), "TEXO_SHARED_DIR": str(self.tmp / "shared"),
            "TEXO_AGY_PROFILE": str(self.tmp / "no-profile")})
        self.patch.start()
        os.environ.pop("TEXO_HUB_TOKEN", None)
        self.registry = FakeRegistry()
        self.opener = unittest.mock.patch("urllib.request.urlopen", self.registry)
        self.opener.start()
        self.root = self.tmp / "acme"
        self.root.mkdir()
        (self.root / "texo.toml").write_text(f'[texo]\norganisation = "acme"\nhub_url = "{HUB}"\n')

    def tearDown(self):
        self.opener.stop()
        self.patch.stop()

    def fabric(self):
        return Fabric(self.root)

    def test_the_key_is_made_once_and_only_the_person_reads_it(self):
        self.assertFalse(environment.has_key("acme"))
        path = environment.create_key("acme")
        self.assertTrue(environment.has_key("acme"))
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(path.parent.stat().st_mode & 0o777), "0o700")
        key = environment.public_key("acme")
        self.assertEqual((key.split()[0], len(key.split())), ("ssh-ed25519", 2), "without its comment")
        listed = subprocess.run(["ssh-keygen", "-lf", f"{path}.pub"], capture_output=True, text=True).stdout.split()[1]
        self.assertEqual(environment.fingerprint(key), listed, "the fingerprint ssh-keygen shows")
        with self.assertRaises(ConfigError):
            environment.create_key("acme")
        print_, address = environment.describe(HUB, "acme")
        self.assertTrue(address.startswith(f"{HUB}/texo/environment?key=ssh-ed25519+"))
        self.assertNotIn(path.read_text().splitlines()[1], address, "nothing of the private key")

    def test_the_machine_proves_its_key_and_keeps_the_token_while_it_holds(self):
        environment.create_key("acme")
        with self.assertRaises(hub.HubError) as refused:
            environment.token(HUB, "acme")
        self.assertEqual(refused.exception.status, 403, "not registered yet")
        self.registry.authorize("acme")
        token = environment.token(HUB, "acme")
        self.assertEqual(token, "token-1")
        kept = environment.token_path("acme")
        self.assertEqual(oct(kept.stat().st_mode & 0o777), "0o600")
        self.assertEqual(json.loads(kept.read_text())["environment"], "laptop")
        calls = len(self.registry.calls)
        self.assertEqual(environment.token(HUB, "acme"), token)
        self.assertEqual(len(self.registry.calls), calls, "kept in its file: the hub is not asked again")
        self.assertEqual(self.fabric().hub(), (HUB, token), "the only bearer of the folder")
        # refused by the hub: a new one, unless another process already renewed the file
        self.assertEqual(environment.token(HUB, "acme", stale=token), "token-2")
        self.assertEqual(environment.token(HUB, "acme", stale=token), "token-2", "the file holds another: used")
        # another hub, or a token about to expire: asked again
        data = json.loads(kept.read_text())
        near = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(minutes=5)
        kept.write_text(json.dumps(dict(data, expires=near.strftime(SOON))))
        self.assertEqual(environment.token(HUB, "acme"), "token-3")

    def test_a_signature_of_another_key_or_namespace_is_refused(self):
        environment.create_key("acme")
        environment.create_key("other")
        self.registry.authorize("acme")
        print_ = environment.fingerprint(environment.public_key("acme"))
        nonce = environment.post(HUB, "/texo/environment/challenge", {"fingerprint": print_})["challenge"]
        with self.assertRaises(hub.HubError):
            environment.post(HUB, "/texo/environment/token",
                             {"fingerprint": print_, "signature": environment.sign("other", nonce)})
        self.assertTrue(self.registry.verified(print_, environment.sign("acme", "text"), "text"))
        self.assertFalse(self.registry.verified(print_, environment.sign("acme", "text"), "another text"))

    def test_a_client_that_outlives_its_token_renews_it(self):
        environment.create_key("acme")
        self.registry.authorize("acme")
        fabric = self.fabric()
        client = hub.Hub(*fabric.hub())
        client.renew = fabric.renewal()
        self.assertEqual(client.call("whoami")["login"], "lead")
        self.registry.tokens = {}                    # the token expired, or another process took a new one
        self.assertEqual(client.call("whoami")["login"], "lead", "renewed and asked again, without the assistant")
        self.assertEqual(client.token, "token-2")
        self.registry.known = {}                     # revoked: the renewal is refused, and said
        self.registry.tokens = {}
        with self.assertRaises(hub.HubError) as refused:
            client.call("whoami")
        self.assertEqual(refused.exception.status, 403)
        # a long-lived token of the person is not renewed: there is nothing to renew it with
        plain = hub.Hub(HUB, "by-hand")
        with self.assertRaises(hub.HubError) as refused:
            plain.call("whoami")
        self.assertEqual(refused.exception.status, 401)

    def test_the_mcp_server_goes_on_after_its_token_expired(self):
        environment.create_key("acme")
        self.registry.authorize("acme")
        client = cli.connect(type("Args", (), {"root": str(self.root)})())
        self.assertIsNotNone(client.renew)
        first = hub.handle_message(client, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                            "params": {"name": "whoami", "arguments": {}}})
        self.assertFalse(first["result"]["isError"])
        self.registry.tokens = {}
        again = hub.handle_message(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                            "params": {"name": "whoami", "arguments": {}}})
        self.assertFalse(again["result"]["isError"], again)

    def test_init_gives_the_machine_a_key_and_tells_the_person_what_to_open(self):
        folder, home = self.tmp / "work", self.tmp / "home"
        folder.mkdir()
        home.mkdir()
        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ, {"HOME": str(home)}):
            code = cli.main(["--root", str(folder), "init", HUB, "acme", "--wait", "0"], out=out, err=io.StringIO())
        text = out.getvalue()
        self.assertTrue(environment.has_key("acme"))
        print_ = environment.fingerprint(environment.public_key("acme"))
        self.assertIn(f"fingerprint is {print_}", text)
        self.assertIn(f"{HUB}/texo/environment?key=", text)
        self.assertIn("not authorized yet", text)
        self.assertEqual(code, mount.FROM_CACHE, "mounted with texo.toml alone: the hub does not know the machine yet")
        self.assertNotIn("token-", text)
        # the person confirmed in the browser: the next command works, and says so
        self.registry.authorize("acme")
        out = io.StringIO()
        self.assertEqual(cli.main(["--root", str(folder), "environment"], out=out, err=io.StringIO()), 0)
        self.assertIn("environment laptop: authorized, token until", out.getvalue())
        self.assertNotIn("token-", out.getvalue(), "a token is never printed")
        # revoked in the hub: the token kept in the file is not taken at its word
        self.registry.known, self.registry.tokens = {}, {}
        out = io.StringIO()
        self.assertEqual(cli.main(["--root", str(folder), "environment"], out=out, err=io.StringIO()), 1)
        self.assertIn("revoked", out.getvalue())

    def test_register_waits_for_the_confirmation(self):
        fabric = self.fabric()
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            if len(slept) == 2:
                self.registry.authorize("acme")

        out = io.StringIO()
        self.assertTrue(cli.register_environment(fabric, out, wait=60, sleep=sleep))
        self.assertEqual(slept, [cli.CONFIRM_EVERY] * 2)
        self.assertIn("registered and authorized", out.getvalue())
        out = io.StringIO()
        self.assertTrue(cli.register_environment(fabric, out, wait=0), "already registered: said at once")
        self.assertNotIn("open the address", out.getvalue())

    def test_a_folder_with_a_token_of_the_person_keeps_working_as_before(self):
        with unittest.mock.patch.dict(os.environ, {"TEXO_HUB_TOKEN": "by-hand"}):
            fabric = self.fabric()
            self.assertEqual(fabric.hub(), (HUB, "by-hand"))
            self.assertIsNone(fabric.renewal())
            out = io.StringIO()
            self.assertEqual(cli.environment_status(fabric, out), 0)
            self.assertIn("no key for the hub", out.getvalue())
        self.assertEqual(self.registry.calls, [], "the registry is never asked")

    def test_doctor_says_which_environment_the_machine_is(self):
        class Told:
            url, token = HUB, "x"

            def __init__(self, told):
                self.told = told

            def call(self, route, payload=None):
                if route == "environment":
                    if self.told is None:
                        raise hub.HubError(404, "not found")
                    return self.told
                return {}

        def doctor(told):
            out = io.StringIO()
            return mount.doctor_environment(self.fabric(), Told(told), out), out.getvalue()

        self.assertEqual(doctor(None), (False, ""), "a hub without the registry, a machine without a key: nothing")
        failed, text = doctor({"environment": None, "required": False})
        self.assertFalse(failed)
        self.assertIn("works with a token of the person", text)
        failed, text = doctor({"environment": None, "required": True})
        self.assertTrue(failed)
        self.assertIn("answers only its registered environments", text)
        failed, text = doctor({"environment": "laptop", "state": "authorized", "expires": "2026-11-15 08:00:00",
                               "required": True})
        self.assertEqual((failed, text), (False, "[ok] environment laptop: authorized, token until 2026-11-15 08:00:00 UTC\n"))
        environment.create_key("acme")
        self.assertIn("the hub keeps no registry", doctor(None)[1])
        with unittest.mock.patch("shutil.which", return_value=None):
            failed, text = doctor({"environment": "laptop"})
        self.assertTrue(failed)
        self.assertIn("ssh-keygen is not installed", text)


if __name__ == "__main__":
    unittest.main()
