"""Read-only settings contract; run with aiohttp available (as in ComfyUI)."""

import asyncio
import json
import os
import socket
import sys
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kotodama import client, config, settings  # noqa: E402


class Request:
    def __init__(self, query="", body=b""):
        self.query_string = query
        self.body = body
        self.content_length = len(body)
        self.content = self

    async def read(self, amount):
        return self.body[:amount]


class Response:
    status = 200

    def read(self, _limit):
        return b'{"data": [{"id": "my-model"}]}'

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def run(coro):
    return asyncio.run(coro)


SENTINEL = "SENTINEL-KOTODAMA-KEY-7b5e"
with patch.dict(os.environ, {
    "KOTODAMA_BASE_URL": "https://example.invalid",
    "KOTODAMA_API_KEY": SENTINEL,
}, clear=True):
    with patch.object(config, "user_env_file", return_value=None):
        with patch.object(config, "_read_env_file", return_value={}):
            status = run(settings.get_status(Request()))
            captured = []

            def fake_open(req, timeout):
                captured.append((req.full_url, req.get_header("Authorization"), timeout))
                return Response()

            with patch.object(client, "urlopen", side_effect=fake_open):
                result = settings.probe_saved_endpoint()
            assert result == {"ok": True, "status": 200, "error": None}
            assert captured == [("https://example.invalid/v1/models", f"Bearer {SENTINEL}", 2.0)]
            assert SENTINEL.encode() not in status.body
            assert SENTINEL[:4].encode() not in status.body
            assert SENTINEL[-4:].encode() not in status.body
            assert SENTINEL not in json.dumps(result)
            assert json.loads(status.body)["key_set"] is True
            settings._LAST_TEST = 0.0
            with patch.object(client, "urlopen", side_effect=fake_open):
                tested = run(settings.post_test(Request()))
            assert tested.status == 200
            assert SENTINEL.encode() not in tested.body
            throttled = run(settings.post_test(Request()))
            assert throttled.status == 429
            assert json.loads(throttled.body) == {
                "ok": False, "status": None, "error": "rate_limited"
            }
            print("[PASS] saved endpoint only, key never returned")

            # The sentinel assertion detects the one-line key-reflection mutant.
            mutant = dict(settings.status_payload(), key=config.api_key())
            assert SENTINEL in json.dumps(mutant)
            print("[PASS] key-reflection mutation is caught")

            with patch.object(settings, "probe_saved_endpoint", side_effect=AssertionError("outbound call")):
                for request in (Request(query="url=https://evil.invalid"), Request(body=b"{}")):
                    refused = run(settings.post_test(request))
                    assert refused.status == 400
                    assert json.loads(refused.body) == {
                        "ok": False, "status": None, "error": "input_not_allowed"
                    }
            print("[PASS] query and body rejected before outbound call")

with patch.object(settings.time, "monotonic", side_effect=[10.0, 11.0, 16.0]):
    settings._LAST_TEST = 0.0
    assert settings.reserve_test() is True
    assert settings.reserve_test() is False
    assert settings.reserve_test() is True
print("[PASS] five-second rate limit")

with patch.object(config, "base_url", return_value="https://user:secret@example.invalid"):
    assert config.safe_base_url() is None
with patch.object(config, "base_url", return_value="https://example.invalid/?token=secret"):
    assert config.safe_base_url() is None
print("[PASS] credential-shaped URLs are refused")

with patch.object(config, "user_env_file", return_value=Path("/tmp/kotodama-user/.env")):
    with patch.object(config, "_read_env_file", side_effect=lambda path: {
        "KOTODAMA_BASE_URL": "https://user.example"
    } if "kotodama-user" in str(path) else {"KOTODAMA_BASE_URL": "https://node.example"}):
        with patch.dict(os.environ, {}, clear=True):
            assert config.base_url() == "https://user.example"
            assert config.setting_with_source("KOTODAMA_BASE_URL")[1] == "userdir"
        with patch.dict(os.environ, {"KOTODAMA_BASE_URL": "https://env.example"}, clear=True):
            assert config.base_url() == "https://env.example"
            assert config.setting_with_source("KOTODAMA_BASE_URL")[1] == "env"
        with patch.dict(os.environ, {"KOTODAMA_BASE_URL": "", "KOTODAMA_API_KEY": ""}, clear=True):
            assert config.base_url() == "https://user.example"
            assert config.setting_with_source("KOTODAMA_BASE_URL")[1] == "userdir"
            assert config.api_key() == ""
print("[PASS] env > userdir > node dotenv precedence")

with patch.object(config, "user_env_file", return_value=None):
    with patch.object(config, "_read_env_file", return_value={"KOTODAMA_API_KEY": "from-file"}):
        with patch.dict(os.environ, {"KOTODAMA_API_KEY": ""}, clear=True):
            assert config.api_key() == "from-file"
            assert config.setting_with_source("KOTODAMA_API_KEY")[1] == "dotenv"
print("[PASS] empty environment key falls through")

def serve(reply):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(1)
    port = listener.getsockname()[1]
    seen = []

    def run_server():
        try:
            connection, _ = listener.accept()
            seen.append(connection.recv(4096))
            connection.sendall(reply)
            connection.close()
        except (OSError, TimeoutError):
            pass
        finally:
            listener.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return port, seen, thread


second_port, second_seen, second_thread = serve(
    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
)
redirect = (
    f"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:{second_port}/stolen"
    "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
).encode()
first_port, first_seen, first_thread = serve(redirect)
with patch.dict(os.environ, {
    "KOTODAMA_BASE_URL": f"http://127.0.0.1:{first_port}",
    "KOTODAMA_API_KEY": SENTINEL,
}, clear=True):
    with patch.object(config, "user_env_file", return_value=None):
        with patch.object(config, "_read_env_file", return_value={}):
            result = settings.probe_saved_endpoint()
first_thread.join(timeout=2)
second_thread.join(timeout=2)
assert result == {"ok": False, "status": 302, "error": "bad_response"}
assert len(first_seen) == 1 and SENTINEL.encode() in first_seen[0]
assert second_seen == []
print("[PASS] redirect never forwards bearer key")

print("8/8 passed")
