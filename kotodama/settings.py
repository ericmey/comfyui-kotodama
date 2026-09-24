"""Read-only ComfyUI settings routes for Kotodama.

No browser route can write the endpoint or key. A connection test always uses
saved configuration, so a reachable ComfyUI server is not an arbitrary URL
probe or a way to redirect future prompts.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import urllib.error
import urllib.request

from . import client, config

_TEST_INTERVAL = 5.0
_TEST_TIMEOUT = 2.0
_TEST_LOCK = threading.Lock()
_LAST_TEST = 0.0


def status_payload() -> dict:
    _, url_source = config.setting_with_source("KOTODAMA_BASE_URL", "LITELLM_BASE_URL")
    _, key_source = config.setting_with_source("KOTODAMA_API_KEY", "LITELLM_API_KEY")
    return {
        "url": config.safe_base_url(),
        "key_set": bool(config.api_key()),
        "source": {"url": url_source, "key": key_source},
        "config_path": str(config.config_path()),
    }


def reserve_test() -> bool:
    """Reserve one outbound probe per five seconds, including failed probes."""
    global _LAST_TEST
    with _TEST_LOCK:
        now = time.monotonic()
        if now - _LAST_TEST < _TEST_INTERVAL:
            return False
        _LAST_TEST = now
        return True


def probe_saved_endpoint() -> dict:
    endpoint = config.safe_base_url()
    if endpoint is None:
        return {"ok": False, "status": None, "error": "not_configured"}

    req = urllib.request.Request(f"{endpoint}/v1/models")
    req.add_header("Accept", "application/json")
    key = config.api_key()
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with client.urlopen(req, timeout=_TEST_TIMEOUT) as response:
            status = response.status
            payload = json.loads(response.read(65537))
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return {"ok": False, "status": status, "error": "bad_response"}
        return {"ok": True, "status": status, "error": None}
    except urllib.error.HTTPError as exc:
        error = {401: "unauthorized", 403: "forbidden"}.get(exc.code, "bad_response")
        exc.close()
        return {"ok": False, "status": exc.code, "error": error}
    except TimeoutError:
        return {"ok": False, "status": None, "error": "timeout"}
    except urllib.error.URLError as exc:
        error = (
            "timeout"
            if isinstance(exc.reason, (TimeoutError, socket.timeout))
            else "unreachable"
        )
        return {"ok": False, "status": None, "error": error}
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {"ok": False, "status": None, "error": "bad_response"}


async def get_status(request):
    from aiohttp import web
    return web.json_response(status_payload())


async def post_test(request):
    from aiohttp import web
    has_input = request.query_string or request.content_length not in (None, 0)
    if not has_input:
        has_input = bool(await request.content.read(1))
    if has_input:
        return web.json_response(
            {"ok": False, "status": None, "error": "input_not_allowed"}, status=400
        )
    if not reserve_test():
        return web.json_response(
            {"ok": False, "status": None, "error": "rate_limited"}, status=429
        )
    return web.json_response(await asyncio.to_thread(probe_saved_endpoint))


def register_routes(routes):
    routes.get("/kotodama/status")(get_status)
    routes.post("/kotodama/test")(post_test)
