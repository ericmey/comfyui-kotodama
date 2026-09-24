"""Connection settings for an OpenAI-compatible chat endpoint.

Resolution order, first non-empty value wins:

1. real process environment (so a systemd/scheduled-task env or a shell
   export beats everything)
2. ``kotodama/.env`` in ComfyUI's user directory
3. a ``.env`` file sitting next to the node package

The API key is DELIBERATELY not a node widget. ComfyUI serialises every
widget value into the saved workflow JSON *and* into the PNG metadata of
every image the graph produces, so a key in a widget leaks into every
picture created from that workflow.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

NODE_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = NODE_ROOT / ".env"

UNCONFIGURED_MODEL = "<configure endpoint or fallback model>"


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a minimal KEY=VALUE .env. Missing file is not an error."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def user_env_file() -> Path | None:
    """Per-user config survives replacement of the custom-node folder."""
    try:
        import folder_paths
        return Path(folder_paths.get_user_directory()) / "kotodama" / ".env"
    except (ImportError, AttributeError):
        return None


def config_path() -> Path:
    return user_env_file() or ENV_FILE


def _sources():
    yield "env", os.environ
    user_file = user_env_file()
    if user_file is not None:
        yield "userdir", _read_env_file(user_file)
    yield "dotenv", _read_env_file(ENV_FILE)


def _lookup(name: str, default: str = "") -> str:
    for _, source in _sources():
        value = source.get(name, "").strip()
        if value:
            return value
    return default


def _setting(primary: str, legacy: str = "", default: str = "") -> str:
    """Read a new setting, retaining old LiteLLM names for existing installs."""
    return setting_with_source(primary, legacy, default)[0]


def setting_with_source(
    primary: str, legacy: str = "", default: str = ""
) -> tuple[str, str]:
    for label, source in _sources():
        value = source.get(primary, "").strip()
        if value:
            return value, label
        value = source.get(legacy, "").strip() if legacy else ""
        if value:
            return value, label
    return default, "none"


def base_url() -> str:
    return _setting("KOTODAMA_BASE_URL", "LITELLM_BASE_URL").rstrip("/")


def safe_base_url() -> str | None:
    """Return a display-safe endpoint; never reflect URL credentials or tokens."""
    value = base_url()
    if not value:
        return None
    try:
        parts = urlsplit(value)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            return None
    except ValueError:
        return None
    return value


def api_key() -> str:
    return _setting("KOTODAMA_API_KEY", "LITELLM_API_KEY")


def request_timeout() -> float:
    """Seconds to wait on a completion. 300s is headroom for slow local generations.

    Floored at 1.0s - ``timeout=0`` makes urllib fail immediately and produces a
    misleading "unreachable" error instead of a real timeout.
    """
    raw = _lookup("KOTODAMA_TIMEOUT", "300")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 300.0


def fallback_models() -> list[str]:
    """Models offered when the proxy cannot be reached at menu-build time."""
    raw = _lookup("KOTODAMA_FALLBACK_MODELS", "")
    listed = [m.strip() for m in raw.split(",") if m.strip()]
    return listed or [UNCONFIGURED_MODEL]
