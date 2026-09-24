"""Client + config behaviour that does not need a live proxy."""

import os
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kotodama import client, config  # noqa: E402
from kotodama.client import LiteLLMError  # noqa: E402

results = []


def check(label, ok):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    results.append(ok)


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
    return {
        "choices": [
            {"message": {"content": content}, "finish_reason": finish_reason}
        ]
    }


# --- seed ---

captured = {}


def _capture_complete(path, payload, timeout):
    captured["payload"] = payload
    return _ok_choice("rewritten")


with patch.object(client, "_request", _capture_complete):
    text = client.complete("example/main", "sys", "user", 0.8, 1024, 0)

check("seed 0 is sent to the API", captured["payload"].get("seed") == 0)
check("seed 0 completion returns content", text == "rewritten")

with patch.object(client, "_request", _capture_complete):
    client.complete("example/main", "sys", "user", 0.8, 1024, 7)
check("nonzero seed is sent", captured["payload"].get("seed") == 7)


# --- finish_reason length ---

try:
    with patch.object(
        client, "_request", lambda *a, **k: _ok_choice("half a prompt", "length")
    ):
        client.complete("example/main", "sys", "user", 0.8, 1024, 1)
    check("length finish_reason raises", False)
except LiteLLMError as exc:
    check("length finish_reason raises", "max_tokens" in str(exc))


# --- malformed JSON / HTML body ---

try:
    with patch.object(config, "base_url", return_value="https://example.invalid"):
        with patch.object(
            client,
            "urlopen",
            lambda *a, **k: _FakeResp(b"<html>nope</html>"),
        ):
            client._request("/v1/chat/completions", {"x": 1}, timeout=1.0)
    check("HTML body becomes LiteLLMError", False)
except LiteLLMError as exc:
    check("HTML body becomes LiteLLMError", "non-JSON" in str(exc))


# --- urllib socket.timeout surfaces as the timeout hint, not the unreachable hint ---

import socket  # noqa: E402

try:
    with patch.object(config, "base_url", return_value="https://example.invalid"):
        with patch.object(
            client,
            "urlopen",
            lambda *a, **k: (_ for _ in ()).throw(
                urllib.error.URLError(socket.timeout("read timed out"))
            ),
        ):
            client._request("/v1/chat/completions", {"x": 1}, timeout=1.0)
    check("urllib socket.timeout surfaces as timeout hint", False)
except LiteLLMError as exc:
    msg = str(exc)
    check(
        "urllib socket.timeout surfaces as timeout hint",
        "timed out" in msg and "raise" in msg and "KOTODAMA_TIMEOUT" in msg,
    )


# --- plain urllib URLError (non-timeout) keeps the unreachable hint ---

try:
    with patch.object(config, "base_url", return_value="https://example.invalid"):
        with patch.object(
            client,
            "urlopen",
            lambda *a, **k: (_ for _ in ()).throw(
                urllib.error.URLError("name resolution failed")
            ),
        ):
            client._request("/v1/chat/completions", {"x": 1}, timeout=1.0)
    check("plain URLError keeps the unreachable hint", False)
except LiteLLMError as exc:
    msg = str(exc)
    check(
        "plain URLError keeps the unreachable hint",
        "Could not reach LiteLLM" in msg and "timed out" not in msg,
    )


# --- config: KOTODAMA_TIMEOUT floored at 1.0s ---

_saved_timeout = os.environ.get("KOTODAMA_TIMEOUT")
try:
    for bad in ("0", "0.0", "-5"):
        os.environ["KOTODAMA_TIMEOUT"] = bad
        check(
            f"KOTODAMA_TIMEOUT={bad} is floored at 1.0",
            config.request_timeout() == 1.0,
        )
    os.environ["KOTODAMA_TIMEOUT"] = "0.5"
    check(
        "KOTODAMA_TIMEOUT=0.5 is floored at 1.0",
        config.request_timeout() == 1.0,
    )
    os.environ["KOTODAMA_TIMEOUT"] = "120"
    check(
        "KOTODAMA_TIMEOUT=120 is respected",
        config.request_timeout() == 120.0,
    )
    os.environ["KOTODAMA_TIMEOUT"] = "not-a-number"
    check(
        "KOTODAMA_TIMEOUT=not-a-number falls back to 300",
        config.request_timeout() == 300.0,
    )
finally:
    if _saved_timeout is None:
        os.environ.pop("KOTODAMA_TIMEOUT", None)
    else:
        os.environ["KOTODAMA_TIMEOUT"] = _saved_timeout


# --- list_models negative cache ---

client._MODEL_CACHE = None
calls = {"n": 0}


def _down(*a, **k):
    calls["n"] += 1
    raise LiteLLMError("proxy down")


with patch.object(config, "base_url", return_value="https://example.invalid"):
    with patch.object(client, "_request", _down):
        models1, live1 = client.list_models()
        models2, live2 = client.list_models()

check("failed models fetch hits the network once", calls["n"] == 1)
check("failed models fetch is not live", live1 is False and live2 is False)
check("failed models fetch serves fallback", len(models1) > 0 and models1 == models2)

client._MODEL_CACHE = None
with patch.object(config, "base_url", return_value="https://example.invalid"):
    with patch.object(
        client, "_request", lambda *a, **k: {"data": None}
    ):
        _, live_null = client.list_models()
check("null models data is treated as a miss", live_null is False)

client._MODEL_CACHE = None
with patch.object(config, "base_url", return_value="https://example.invalid"):
    with patch.object(
        client, "_request", lambda *a, **k: {"data": [{"id": "example/main"}]}
    ):
        models_ok, live_ok = client.list_models()
check("successful models fetch is live", live_ok is True and "example/main" in models_ok)


# --- an unconfigured fresh install never contacts a house endpoint ---

client._MODEL_CACHE = None
with patch.object(config, "base_url", return_value=""):
    with patch.object(client, "_request", side_effect=AssertionError("network attempted")):
        unconfigured_models, unconfigured_live = client.list_models()
check(
    "unconfigured model menu is non-live",
    unconfigured_models == [config.UNCONFIGURED_MODEL] and not unconfigured_live,
)
try:
    with patch.object(config, "base_url", return_value=""):
        with patch.object(client, "urlopen", side_effect=AssertionError("network attempted")):
            client._request("/v1/models", None, timeout=1.0)
    check("unconfigured request fails before network", False)
except LiteLLMError as exc:
    check("unconfigured request fails before network", "KOTODAMA_BASE_URL" in str(exc))


# --- new names take precedence, old names remain compatible ---

with patch.dict(os.environ, {"KOTODAMA_BASE_URL": "https://new.example", "LITELLM_BASE_URL": "https://old.example"}):
    check("new endpoint name wins", config.base_url() == "https://new.example")
with patch.dict(os.environ, {"LITELLM_BASE_URL": "https://old.example"}):
    with patch.object(config, "_read_env_file", return_value={}):
        check("legacy endpoint name still works", config.base_url() == "https://old.example")
with patch.dict(os.environ, {"KOTODAMA_API_KEY": "new-key", "LITELLM_API_KEY": "old-key"}):
    check("new API key name wins", config.api_key() == "new-key")


# Cache entries are scoped to endpoint, so a settings change cannot keep a stale menu.
client._MODEL_CACHE = None
with patch.object(config, "base_url", side_effect=["https://one.example", "https://two.example"]):
    with patch.object(client, "_request", side_effect=[{"data": [{"id": "one"}]}, {"data": [{"id": "two"}]}]):
        first, _ = client.list_models()
        second, _ = client.list_models()
check("model cache is endpoint-scoped", first == ["one"] and second == ["two"])


# --- config: empty process env falls through to .env ---

_saved = os.environ.get("KOTODAMA_FALLBACK_MODELS")
try:
    os.environ["KOTODAMA_FALLBACK_MODELS"] = ""
    with patch.object(
        config, "_read_env_file", return_value={"KOTODAMA_FALLBACK_MODELS": "from-file"}
    ):
        check(
            "empty process env falls through to .env",
            config._lookup("KOTODAMA_FALLBACK_MODELS", "default") == "from-file",
        )
    os.environ.pop("KOTODAMA_FALLBACK_MODELS", None)
    with patch.object(
        config, "_read_env_file", return_value={"KOTODAMA_FALLBACK_MODELS": "from-file"}
    ):
        check(
            "missing process env falls through to .env",
            config._lookup("KOTODAMA_FALLBACK_MODELS", "default") == "from-file",
        )
finally:
    if _saved is None:
        os.environ.pop("KOTODAMA_FALLBACK_MODELS", None)
    else:
        os.environ["KOTODAMA_FALLBACK_MODELS"] = _saved

client._MODEL_CACHE = None

print()
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
