"""Read-only settings contract. Needs aiohttp, as it is inside ComfyUI."""

import asyncio
import json
import os
import socket
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("aiohttp")

from kotodama import client, config, settings  # noqa: E402

SENTINEL = "SENTINEL-KOTODAMA-KEY-7b5e"


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


@pytest.fixture
def configured():
    """A saved endpoint and key, with no user-dir or node .env interfering."""
    with patch.dict(
        os.environ, {"KOTODAMA_BASE_URL": "https://example.invalid", "KOTODAMA_API_KEY": SENTINEL}, clear=True
    ):
        with patch.object(config, "user_env_file", return_value=None):
            with patch.object(config, "_read_env_file", return_value={}):
                settings._LAST_TEST = 0.0
                yield


def test_saved_endpoint_only_and_key_never_returned(configured) -> None:
    status = run(settings.get_status(Request()))
    captured = []

    def fake_open(req, timeout):
        captured.append((req.full_url, req.get_header("Authorization"), timeout))
        return Response()

    with patch.object(client, "urlopen", side_effect=fake_open):
        result = settings.probe_saved_endpoint()
    assert result == {"ok": True, "status": 200, "error": None}
    assert captured == [("https://example.invalid/v1/models", f"Bearer {SENTINEL}", 2.0)]
    for fragment in (SENTINEL, SENTINEL[:4], SENTINEL[-4:]):
        assert fragment.encode() not in status.body
    assert SENTINEL not in json.dumps(result)
    assert json.loads(status.body)["key_set"] is True

    settings._LAST_TEST = 0.0
    with patch.object(client, "urlopen", side_effect=fake_open):
        tested = run(settings.post_test(Request()))
    assert tested.status == 200
    assert SENTINEL.encode() not in tested.body
    throttled = run(settings.post_test(Request()))
    assert throttled.status == 429
    assert json.loads(throttled.body) == {"ok": False, "status": None, "error": "rate_limited"}


def test_key_reflection_mutation_is_caught(configured) -> None:
    # The sentinel assertion above detects the one-line key-reflection mutant.
    mutant = dict(settings.status_payload(), key=config.api_key())
    assert SENTINEL in json.dumps(mutant)


@pytest.mark.parametrize(
    "request_obj", [Request(query="url=https://evil.invalid"), Request(body=b"{}")], ids=["query", "body"]
)
def test_input_rejected_before_outbound_call(configured, request_obj) -> None:
    with patch.object(settings, "probe_saved_endpoint", side_effect=AssertionError("outbound call")):
        refused = run(settings.post_test(request_obj))
    assert refused.status == 400
    assert json.loads(refused.body) == {"ok": False, "status": None, "error": "input_not_allowed"}


def test_five_second_rate_limit() -> None:
    with patch.object(settings.time, "monotonic", side_effect=[10.0, 11.0, 16.0]):
        settings._LAST_TEST = 0.0
        assert settings.reserve_test() is True
        assert settings.reserve_test() is False
        assert settings.reserve_test() is True


@pytest.mark.parametrize("url", ["https://user:secret@example.invalid", "https://example.invalid/?token=secret"])
def test_credential_shaped_urls_are_refused(url: str) -> None:
    with patch.object(config, "base_url", return_value=url):
        assert config.safe_base_url() is None


def test_env_beats_userdir_beats_node_dotenv() -> None:
    def read(path):
        if "kotodama-user" in str(path):
            return {"KOTODAMA_BASE_URL": "https://user.example"}
        return {"KOTODAMA_BASE_URL": "https://node.example"}

    with patch.object(config, "user_env_file", return_value=Path("/tmp/kotodama-user/.env")):
        with patch.object(config, "_read_env_file", side_effect=read):
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


def test_empty_environment_key_falls_through() -> None:
    with patch.object(config, "user_env_file", return_value=None):
        with patch.object(config, "_read_env_file", return_value={"KOTODAMA_API_KEY": "from-file"}):
            with patch.dict(os.environ, {"KOTODAMA_API_KEY": ""}, clear=True):
                assert config.api_key() == "from-file"
                assert config.setting_with_source("KOTODAMA_API_KEY")[1] == "dotenv"


def _serve(reply: bytes):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(1)
    port = listener.getsockname()[1]
    seen: list[bytes] = []

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


def test_redirect_never_forwards_bearer_key() -> None:
    second_port, second_seen, second_thread = _serve(
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
    )
    redirect = (
        f"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:{second_port}/stolen"
        "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    ).encode()
    first_port, first_seen, first_thread = _serve(redirect)
    with patch.dict(
        os.environ, {"KOTODAMA_BASE_URL": f"http://127.0.0.1:{first_port}", "KOTODAMA_API_KEY": SENTINEL}, clear=True
    ):
        with patch.object(config, "user_env_file", return_value=None):
            with patch.object(config, "_read_env_file", return_value={}):
                result = settings.probe_saved_endpoint()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)
    assert result == {"ok": False, "status": 302, "error": "bad_response"}
    assert len(first_seen) == 1 and SENTINEL.encode() in first_seen[0]
    assert second_seen == []
