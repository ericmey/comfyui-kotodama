"""System-prompt library: every file in ``system_prompts/``.

Rescanned on every INPUT_TYPES call, which ComfyUI runs each time the
graph front-end loads. Dropping a new .md in the folder and refreshing
the browser is enough - no ComfyUI restart.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .config import NODE_ROOT

PROMPT_DIR = NODE_ROOT / "system_prompts"
SUFFIXES = (".md", ".txt")

# The krea2 prompt Eric supplied is fenced with these banners. They are for
# humans copy-pasting the file around; the model should never see them.
# Strip is forgiving: any line that is only '#' chars with optional whitespace
# and that mentions START or END (case-insensitive) is dropped. A single-space
# edit or a rewrap of the canonical banner no longer leaks literal hashes into
# the system prompt.
_BANNER_LINE = re.compile(
    r"^\s*#+\s*(?:START|END)\s*#*\s*$",
    re.IGNORECASE,
)


def available() -> list[str]:
    """Sorted stems of every system-prompt file. Never empty."""
    if not PROMPT_DIR.is_dir():
        return ["<no system_prompts folder>"]
    names = sorted({
        p.stem for p in PROMPT_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() in SUFFIXES
        and not p.name.startswith(".")  # dotfiles, and macOS "._" AppleDouble
        # forks, which a tar from a Mac carries onto a Linux box and which
        # otherwise appear in the dropdown as a prompt named "._krea2"
    })
    return names or ["<system_prompts folder is empty>"]


def _prompt_file(name: str, suffix: str) -> Path | None:
    """Resolve a prompt file, or None if ``name`` is not a single stem in PROMPT_DIR."""
    if not name or Path(name).name != name:
        return None
    base = PROMPT_DIR.resolve()
    candidate = (PROMPT_DIR / f"{name}{suffix}").resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def load(name: str) -> str:
    """Read one system prompt by stem, banners stripped."""
    for suffix in SUFFIXES:
        candidate = _prompt_file(name, suffix)
        if candidate is not None and candidate.is_file():
            return _strip_banners(candidate.read_text(encoding="utf-8"))

    raise FileNotFoundError(
        f"No system prompt named '{name}' in {PROMPT_DIR}.\n"
        f"  Available: {', '.join(available())}"
    )


def fingerprint(name: str) -> str:
    """Cache identity for a selected prompt, including edits to its file."""
    try:
        body = load(name)
    except FileNotFoundError:
        return f"missing:{name}"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _strip_banners(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not _BANNER_LINE.match(ln)]
    return "\n".join(lines).strip()
