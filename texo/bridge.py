"""texo run-thread <id>: how an assistant reaches an MCP thread without a credential in its configuration.

The configuration of every assistant names texo run-thread; this process reads the credentials from the
environment or the customer's env file at start. An mcp-stdio thread becomes its own process with them in
its environment; an mcp-http thread is bridged: JSON-RPC lines on stdin go to the server over Streamable
HTTP with the token as bearer, and its answers (JSON or server-sent events) come back as lines on stdout.
"""
import json
import os
import sys
import urllib.error
import urllib.request

from .mount import thread_env
from .threads import events  # noqa: F401  (the bridge reads server-sent events as doctor does)

TIMEOUT = 300


def run_stdio(fabric, thread):
    os.chdir(fabric.root)
    command = [thread["command"], *thread.get("args", [])]
    os.execvpe(command[0], command, thread_env(fabric, thread))


def bridge_http(fabric, thread, stdin=sys.stdin, stdout=sys.stdout):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if thread.get("auth"):
        headers["Authorization"] = f"Bearer {fabric.secret(thread['auth'])}"
    session = None
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        message = json.loads(line)
        request_headers = dict(headers, **({"Mcp-Session-Id": session} if session else {}))
        request = urllib.request.Request(thread["url"], data=line.encode(), headers=request_headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                session = response.headers.get("Mcp-Session-Id") or session
                body = response.read().decode("utf-8", errors="replace")
                kind = response.headers.get("Content-Type", "")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            if "id" in message:
                text = f"{thread['id']}: {getattr(error, 'code', '')} {getattr(error, 'reason', error)}".strip()
                stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"],
                                         "error": {"code": -32000, "message": text}}) + "\n")
                stdout.flush()
            continue
        answers = list(events(body)) if "text/event-stream" in kind else ([json.loads(body)] if body.strip() else [])
        for answer in answers:
            stdout.write(json.dumps(answer, ensure_ascii=False) + "\n")
        stdout.flush()


def run_thread(fabric, thread):
    if thread.get("driver") == "mcp-stdio":
        run_stdio(fabric, thread)
    elif thread.get("driver") == "mcp-http":
        bridge_http(fabric, thread)
    else:
        raise SystemExit(f"{thread.get('id')} is not an MCP thread")
