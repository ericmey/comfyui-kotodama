"""System-prompt library, checked against the real folder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kotodama import prompts  # noqa: E402

results = []


def check(label, ok):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    results.append(ok)


names = prompts.available()
check(f"krea2 discovered (found: {names})", "krea2" in names)
check("text-only default discovered", "text-to-image" in names)
check("text-only prompt does not claim to see an image", "do not invent" in prompts.load("text-to-image"))

body = prompts.load("krea2")
check("krea2 loads non-empty", len(body) > 1000)
check("START banner stripped", "########START" not in body)
check("END banner stripped", "##########END" not in body)
check("instruction survives", "Output ONLY the prompt" in body)


# Forgiving banner strip: a rewrap or whitespace edit of the canonical banner
# should still be removed. Done in-process rather than touching real files.
from kotodama.prompts import _strip_banners  # noqa: E402

sample = "real prompt line\n### START ###\nmore prompt\n### END ###\n"
check(
    "rewrapped banners stripped",
    _strip_banners(sample) == "real prompt line\nmore prompt",
)
check(
    "narrative comment with the word START survives",
    "### NARRATIVE START ###"
    in _strip_banners("### NARRATIVE START ###\nbody"),
)

try:
    prompts.load("does-not-exist")
    check("missing prompt raises", False)
except FileNotFoundError as exc:
    check("missing prompt raises and lists what IS available", "krea2" in str(exc))

for crafted in ("../README", "/tmp/x", "..\\README"):
    try:
        prompts.load(crafted)
        check(f"path-shaped name {crafted!r} rejected", False)
    except FileNotFoundError:
        check(f"path-shaped name {crafted!r} rejected", True)

# A tar from a Mac drops "._krea2" next to "krea2" on a Linux box; it showed
# up in the live dropdown on rika before this filter existed.
_junk = prompts.PROMPT_DIR / "._junktest.md"
_dup_md = prompts.PROMPT_DIR / "_duptest.md"
_dup_txt = prompts.PROMPT_DIR / "_duptest.txt"
try:
    _junk.write_text("x", encoding="utf-8")
    check("AppleDouble/dotfiles excluded from the menu",
          not any(n.startswith(".") for n in prompts.available()))
    _dup_md.write_text("from md", encoding="utf-8")
    _dup_txt.write_text("from txt", encoding="utf-8")
    names = prompts.available()
    check("duplicate stems appear once", names.count("_duptest") == 1)
    check("load prefers .md when both exist", prompts.load("_duptest") == "from md")
finally:
    _junk.unlink(missing_ok=True)
    _dup_md.unlink(missing_ok=True)
    _dup_txt.unlink(missing_ok=True)

print()
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
