"""The output cleaner is the part that silently corrupts a prompt if it
overreaches, so it gets tested against the shapes models actually emit."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kotodama.client import LiteLLMError  # noqa: E402
from kotodama.enhancer import KotodamaPromptEnhancer, clean  # noqa: E402
from kotodama import prompts  # noqa: E402


def check(label, got, want):
    status = "PASS" if got == want else "FAIL"
    print(f"[{status}] {label}")
    if got != want:
        print(f"    want: {want!r}")
        print(f"    got:  {got!r}")
    return got == want


results = []

results.append(check("plain text untouched",
    clean("A woman on a rooftop."), "A woman on a rooftop."))

results.append(check("wrapping quotes stripped",
    clean('"A woman on a rooftop."'), "A woman on a rooftop."))

results.append(check("code fence stripped",
    clean("```\nA woman on a rooftop.\n```"), "A woman on a rooftop."))

results.append(check("language fence stripped",
    clean("```text\nA woman on a rooftop.\n```"), "A woman on a rooftop."))

results.append(check("lead-in stripped",
    clean("Here is the prompt:\nA woman on a rooftop."), "A woman on a rooftop."))

results.append(check("curly-apostrophe lead-in stripped",
    clean("Here’s the prompt:\nA woman on a rooftop."), "A woman on a rooftop."))

# The krea2 spec REQUIRES quoted signage inside the prompt. Eating those
# quotes would silently change what gets rendered.
results.append(check("inner quotes survive",
    clean('A storefront sign reading "OPEN LATE" at dusk.'),
    'A storefront sign reading "OPEN LATE" at dusk.'))

results.append(check("wrapped prompt keeps its inner quotes",
    clean('"A sign reading "OPEN LATE" at dusk."'),
    'A sign reading "OPEN LATE" at dusk.'))

results.append(check("smart quotes stripped",
    clean("“A woman on a rooftop.”"), "A woman on a rooftop."))

results.append(check("nested straight-outer curly-inner only strips outer",
    clean('"\u201chi\u201d"'), "\u201chi\u201d"))

results.append(check("whitespace only -> empty",
    clean("   \n  "), ""))


# --- IS_CHANGED: every relevant input must invalidate the cache ---


def check_bool(label, ok):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}")
    return ok


base = dict(
    text="a woman on a rooftop",
    system_prompt="krea2",
    model="example/main",
    temperature=0.8,
    max_tokens=1024,
    seed=0,
    passthrough_on_empty=True,
)

ref = KotodamaPromptEnhancer.IS_CHANGED(**base)
for field, alt in (
    ("text", "a different woman"),
    ("system_prompt", "different-prompt"),
    ("model", "example/small"),
    ("temperature", 0.5),
    ("max_tokens", 2048),
    ("seed", 1),
    ("passthrough_on_empty", False),
):
    tweaked = dict(base, **{field: alt})
    changed = KotodamaPromptEnhancer.IS_CHANGED(**tweaked)
    results.append(check_bool(
        f"IS_CHANGED reacts to {field!r} change",
        changed != ref,
    ))

# Sanity: identical inputs return an equal key
results.append(check_bool(
    "IS_CHANGED is deterministic for identical inputs",
    KotodamaPromptEnhancer.IS_CHANGED(**base) == ref,
))

with patch("kotodama.enhancer.client.config.safe_base_url", return_value="https://other.example"):
    results.append(check_bool(
        "changing endpoint invalidates cached output",
        KotodamaPromptEnhancer.IS_CHANGED(**base) != ref,
    ))

_cache_probe = prompts.PROMPT_DIR / "_cache_probe.md"
try:
    _cache_probe.write_text("first version", encoding="utf-8")
    key1 = KotodamaPromptEnhancer.IS_CHANGED(**dict(base, system_prompt="_cache_probe"))
    _cache_probe.write_text("second version", encoding="utf-8")
    key2 = KotodamaPromptEnhancer.IS_CHANGED(**dict(base, system_prompt="_cache_probe"))
    results.append(check_bool("editing selected prompt invalidates cache", key1 != key2))
finally:
    _cache_probe.unlink(missing_ok=True)

spec = KotodamaPromptEnhancer.INPUT_TYPES()["required"]
results.append(check_bool(
    "text-only prompt is the default",
    spec["system_prompt"][1]["default"] == "text-to-image",
))
results.append(check_bool(
    "empty input fails by default",
    spec["passthrough_on_empty"][1]["default"] is False,
))

def _enhance_with_reply(reply):
    node = KotodamaPromptEnhancer()
    with patch("kotodama.enhancer.prompts.load", return_value="system"):
        with patch("kotodama.enhancer.client.complete", return_value=reply):
            return node.enhance(
                text="a woman on a rooftop",
                system_prompt="krea2",
                model="example/main",
                temperature=0.8,
                max_tokens=1024,
                seed=0,
                passthrough_on_empty=True,
            )


try:
    _enhance_with_reply("   \n  ")
    results.append(check("enhance refuses cleaned-empty reply", False, True))
except LiteLLMError as exc:
    results.append(check(
        "enhance refuses cleaned-empty reply",
        "empty string downstream" in str(exc),
        True,
    ))

got = _enhance_with_reply("A woman on a rooftop.")
results.append(check("enhance returns cleaned prompt", got, ("A woman on a rooftop.",)))

print()
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
