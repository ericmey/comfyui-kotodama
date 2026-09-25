"""Client + config behaviour that does not need a live proxy."""

import os
import urllib.error
from unittest.mock import patch

import pytest

from kotodama import client, config
from kotodama.client import LiteLLMError


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _ok_choice(content="ok", finish_reason="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}


@pytest.fixture(autouse=True)
def _fresh_model_cache():
    client._MODEL_CACHE = None
    yield
    client._MODEL_CACHE = None


def _raise(exc):
    def _fn(*_a, **_k):
        raise exc

    return _fn


# --- seed ---


def test_seed_is_sent_including_zero() -> None:
    captured = {}

    def capture(path, payload, timeout):
        captured["payload"] = payload
        return _ok_choice("rewritten")

    with patch.object(client, "_request", capture):
        text = client.complete("example/main", "sys", "user", 0.8, 1024, 0)
    assert captured["payload"].get("seed") == 0  # seed 0 is sent to the API
    assert text == "rewritten"

    with patch.object(client, "_request", capture):
        client.complete("example/main", "sys", "user", 0.8, 1024, 7)
    assert captured["payload"].get("seed") == 7


def test_length_finish_reason_raises() -> None:
    with patch.object(client, "_request", lambda *a, **k: _ok_choice("half a prompt", "length")):
        with pytest.raises(LiteLLMError, match="max_tokens"):
            client.complete("example/main", "sys", "user", 0.8, 1024, 1)


def test_html_body_becomes_litellm_error() -> None:
    with patch.object(config, "base_url", return_value="https://example.invalid"):
        with patch.object(client, "urlopen", lambda *a, **k: _FakeResp(b"<html>nope</html>")):
            with pytest.raises(LiteLLMError, match="non-JSON"):
                client._request("/v1/chat/completions", {"x": 1}, timeout=1.0)


def test_socket_timeout_surfaces_as_timeout_hint() -> None:
    err = urllib.error.URLError(TimeoutError("read timed out"))
    with patch.object(config, "base_url", return_value="https://example.invalid"):
        with patch.object(client, "urlopen", _raise(err)):
            with pytest.raises(LiteLLMError) as exc:
                client._request("/v1/chat/completions", {"x": 1}, timeout=1.0)
    msg = str(exc.value)
    assert "timed out" in msg and "raise" in msg and "KOTODAMA_TIMEOUT" in msg


def test_plain_urlerror_keeps_the_unreachable_hint() -> None:
    with patch.object(config, "base_url", return_value="https://example.invalid"):
        with patch.object(client, "urlopen", _raise(urllib.error.URLError("name resolution failed"))):
            with pytest.raises(LiteLLMError) as exc:
                client._request("/v1/chat/completions", {"x": 1}, timeout=1.0)
    msg = str(exc.value)
    assert "Could not reach LiteLLM" in msg and "timed out" not in msg


@pytest.mark.parametrize(
    ("value", "want"),
    [("0", 1.0), ("0.0", 1.0), ("-5", 1.0), ("0.5", 1.0), ("120", 120.0), ("not-a-number", 300.0)],
)
def test_kotodama_timeout_is_floored_and_parsed(value: str, want: float) -> None:
    with patch.dict(os.environ, {"KOTODAMA_TIMEOUT": value}):
        assert config.request_timeout() == want


# --- list_models ---


def test_failed_models_fetch_is_negatively_cached() -> None:
    calls = {"n": 0}

    def down(*a, **k):
        calls["n"] += 1
        raise LiteLLMError("proxy down")

    with patch.object(config, "base_url", return_value="https://example.invalid"):
        with patch.object(client, "_request", down):
            models1, live1 = client.list_models()
            models2, live2 = client.list_models()
    assert calls["n"] == 1  # the network is hit once
    assert live1 is False and live2 is False
    assert len(models1) > 0 and models1 == models2  # fallback served


def test_null_models_data_is_treated_as_a_miss() -> None:
    with patch.object(config, "base_url", return_value="https://example.invalid"):
        with patch.object(client, "_request", lambda *a, **k: {"data": None}):
            _, live = client.list_models()
    assert live is False


def test_successful_models_fetch_is_live() -> None:
    with patch.object(config, "base_url", return_value="https://example.invalid"):
        with patch.object(client, "_request", lambda *a, **k: {"data": [{"id": "example/main"}]}):
            models, live = client.list_models()
    assert live is True and "example/main" in models


def test_unconfigured_install_never_contacts_an_endpoint() -> None:
    with patch.object(config, "base_url", return_value=""):
        with patch.object(client, "_request", side_effect=AssertionError("network attempted")):
            models, live = client.list_models()
    assert models == [config.UNCONFIGURED_MODEL] and not live
    with patch.object(config, "base_url", return_value=""):
        with patch.object(client, "urlopen", side_effect=AssertionError("network attempted")):
            with pytest.raises(LiteLLMError, match="KOTODAMA_BASE_URL"):
                client._request("/v1/models", None, timeout=1.0)


def test_model_cache_is_endpoint_scoped() -> None:
    # A settings change must not keep a stale menu.
    with patch.object(config, "base_url", side_effect=["https://one.example", "https://two.example"]):
        with patch.object(client, "_request", side_effect=[{"data": [{"id": "one"}]}, {"data": [{"id": "two"}]}]):
            first, _ = client.list_models()
            second, _ = client.list_models()
    assert first == ["one"] and second == ["two"]


# --- config names and precedence ---


def test_new_names_win_and_legacy_names_still_work() -> None:
    with patch.dict(
        os.environ, {"KOTODAMA_BASE_URL": "https://new.example", "LITELLM_BASE_URL": "https://old.example"}
    ):
        assert config.base_url() == "https://new.example"
    with patch.dict(os.environ, {"LITELLM_BASE_URL": "https://old.example"}):
        with patch.object(config, "_read_env_file", return_value={}):
            assert config.base_url() == "https://old.example"
    with patch.dict(os.environ, {"KOTODAMA_API_KEY": "new-key", "LITELLM_API_KEY": "old-key"}):
        assert config.api_key() == "new-key"


@pytest.mark.parametrize("process_value", ["", None], ids=["empty process env", "missing process env"])
def test_process_env_falls_through_to_dotenv(process_value: str | None) -> None:
    env = {} if process_value is None else {"KOTODAMA_FALLBACK_MODELS": process_value}
    with patch.dict(os.environ, env):
        if process_value is None:
            os.environ.pop("KOTODAMA_FALLBACK_MODELS", None)
        with patch.object(config, "_read_env_file", return_value={"KOTODAMA_FALLBACK_MODELS": "from-file"}):
            assert config._lookup("KOTODAMA_FALLBACK_MODELS", "default") == "from-file"
