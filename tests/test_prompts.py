"""System-prompt library, checked against the real folder."""

import re
import sys
from pathlib import Path
import pytest

from kotodama import prompts
from kotodama.prompts import _strip_banners


def test_bundled_prompts_are_discovered() -> None:
    names = prompts.available()
    assert "krea2" in names
    assert "text-to-image" in names  # text-only default discovered


def test_text_only_prompt_does_not_claim_to_see_an_image() -> None:
    assert "do not invent" in prompts.load("text-to-image")


def test_krea2_loads_with_banners_stripped() -> None:
    body = prompts.load("krea2")
    assert len(body) > 1000
    assert "########START" not in body
    assert "##########END" not in body
    assert "Output ONLY the prompt" in body  # the instruction survives


def test_rewrapped_banners_stripped() -> None:
    # A rewrap or whitespace edit of the canonical banner should still be removed.
    sample = "real prompt line\n### START ###\nmore prompt\n### END ###\n"
    assert _strip_banners(sample) == "real prompt line\nmore prompt"

# Prompt-library contract: every discovered preset must (a) load non-empty,
# (b) have its wrapper banners stripped, and (c) not affirm that the
# text-only node can inspect a reference image. Each check is run once per
# preset so a regression in any single file fails the suite by name.
_NEGATIVE_QUALIFIERS = ("do not", "never", "must not", "should not", "no ")


def _claims_unseen_image(body: str) -> bool:
    """True if `body` makes an unnegated claim about inspecting a reference image."""
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        s = sentence.lower()
        if "reference image" not in s:
            continue
        if any(n in s for n in _NEGATIVE_QUALIFIERS):
            continue
        return True
    return False


for preset in prompts.available():
    if preset.startswith("<"):
        continue  # placeholder returned when the folder is empty / missing
    body = prompts.load(preset)
    check(f"{preset}: loads non-empty", bool(body.strip()))
    check(f"{preset}: START banner stripped", "########START" not in body)
    check(f"{preset}: END banner stripped", "##########END" not in body)
    check(
        f"{preset}: text-only contract (no claim to inspect a reference image)",
        not _claims_unseen_image(body),
    )


# Forgiving banner strip: a rewrap or whitespace edit of the canonical banner
# should still be removed. Done in-process rather than touching real files.
from kotodama.prompts import _strip_banners  # noqa: E402


def test_narrative_comment_with_the_word_start_survives() -> None:
    assert "### NARRATIVE START ###" in _strip_banners("### NARRATIVE START ###\nbody")


def test_missing_prompt_raises_and_lists_what_is_available() -> None:
    with pytest.raises(FileNotFoundError, match="krea2"):
        prompts.load("does-not-exist")


@pytest.mark.parametrize("crafted", ["../README", "/tmp/x", "..\\README"])
def test_path_shaped_name_rejected(crafted: str) -> None:
    with pytest.raises(FileNotFoundError):
        prompts.load(crafted)


def test_menu_hygiene_dotfiles_and_duplicate_stems() -> None:
    # A tar from a Mac drops "._krea2" next to "krea2" on a Linux box; it showed
    # up in the live dropdown before this filter existed.
    junk = prompts.PROMPT_DIR / "._junktest.md"
    dup_md = prompts.PROMPT_DIR / "_duptest.md"
    dup_txt = prompts.PROMPT_DIR / "_duptest.txt"
    try:
        junk.write_text("x", encoding="utf-8")
        assert not any(n.startswith(".") for n in prompts.available())
        dup_md.write_text("from md", encoding="utf-8")
        dup_txt.write_text("from txt", encoding="utf-8")
        assert prompts.available().count("_duptest") == 1
        assert prompts.load("_duptest") == "from md"  # .md preferred when both exist
    finally:
        junk.unlink(missing_ok=True)
        dup_md.unlink(missing_ok=True)
        dup_txt.unlink(missing_ok=True)
