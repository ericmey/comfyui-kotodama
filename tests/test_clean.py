"""The output cleaner is the part that silently corrupts a prompt if it
overreaches, so it gets tested against the shapes models actually emit."""

from unittest.mock import patch

import pytest

from kotodama import prompts
from kotodama.client import LiteLLMError
from kotodama.enhancer import KotodamaPromptEnhancer, clean


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        pytest.param("A woman on a rooftop.", "A woman on a rooftop.", id="plain text untouched"),
        pytest.param('"A woman on a rooftop."', "A woman on a rooftop.", id="wrapping quotes stripped"),
        pytest.param("```\nA woman on a rooftop.\n```", "A woman on a rooftop.", id="code fence stripped"),
        pytest.param("```text\nA woman on a rooftop.\n```", "A woman on a rooftop.", id="language fence stripped"),
        pytest.param("Here is the prompt:\nA woman on a rooftop.", "A woman on a rooftop.", id="lead-in stripped"),
        pytest.param(
            "Here’s the prompt:\nA woman on a rooftop.", "A woman on a rooftop.", id="curly-apostrophe lead-in stripped"
        ),
        # The krea2 spec REQUIRES quoted signage inside the prompt. Eating those
        # quotes would silently change what gets rendered.
        pytest.param(
            'A storefront sign reading "OPEN LATE" at dusk.',
            'A storefront sign reading "OPEN LATE" at dusk.',
            id="inner quotes survive",
        ),
        pytest.param(
            '"A sign reading "OPEN LATE" at dusk."',
            'A sign reading "OPEN LATE" at dusk.',
            id="wrapped prompt keeps its inner quotes",
        ),
        pytest.param("“A woman on a rooftop.”", "A woman on a rooftop.", id="smart quotes stripped"),
        pytest.param('"“hi”"', "“hi”", id="nested straight-outer curly-inner only strips outer"),
        pytest.param("   \n  ", "", id="whitespace only -> empty"),
    ],
)
def test_clean(raw: str, want: str) -> None:
    assert clean(raw) == want


# --- IS_CHANGED: every relevant input must invalidate the cache ---

BASE = dict(
    text="a woman on a rooftop",
    system_prompt="krea2",
    model="example/main",
    temperature=0.8,
    max_tokens=1024,
    seed=0,
    passthrough_on_empty=True,
)


@pytest.mark.parametrize(
    ("field", "alt"),
    [
        ("text", "a different woman"),
        ("system_prompt", "different-prompt"),
        ("model", "example/small"),
        ("temperature", 0.5),
        ("max_tokens", 2048),
        ("seed", 1),
        ("passthrough_on_empty", False),
    ],
)
def test_is_changed_reacts_to_each_input(field: str, alt: object) -> None:
    ref = KotodamaPromptEnhancer.IS_CHANGED(**BASE)
    assert KotodamaPromptEnhancer.IS_CHANGED(**dict(BASE, **{field: alt})) != ref


def test_is_changed_is_deterministic_for_identical_inputs() -> None:
    assert KotodamaPromptEnhancer.IS_CHANGED(**BASE) == KotodamaPromptEnhancer.IS_CHANGED(**BASE)


def test_changing_endpoint_invalidates_cached_output() -> None:
    ref = KotodamaPromptEnhancer.IS_CHANGED(**BASE)
    with patch("kotodama.enhancer.client.config.safe_base_url", return_value="https://other.example"):
        assert KotodamaPromptEnhancer.IS_CHANGED(**BASE) != ref


def test_changing_api_key_invalidates_cache_without_exposing_it() -> None:
    with patch("kotodama.enhancer.client.config.api_key", return_value="test-key-a"):
        first_key = KotodamaPromptEnhancer.IS_CHANGED(**BASE)
    with patch("kotodama.enhancer.client.config.api_key", return_value="test-key-b"):
        second_key = KotodamaPromptEnhancer.IS_CHANGED(**BASE)
    assert first_key != second_key
    assert "test-key-a" not in repr(first_key)


def test_editing_selected_prompt_invalidates_cache() -> None:
    probe = prompts.PROMPT_DIR / "_cache_probe.md"
    try:
        probe.write_text("first version", encoding="utf-8")
        key1 = KotodamaPromptEnhancer.IS_CHANGED(**dict(BASE, system_prompt="_cache_probe"))
        probe.write_text("second version", encoding="utf-8")
        key2 = KotodamaPromptEnhancer.IS_CHANGED(**dict(BASE, system_prompt="_cache_probe"))
    finally:
        probe.unlink(missing_ok=True)
    assert key1 != key2


def test_input_defaults() -> None:
    spec = KotodamaPromptEnhancer.INPUT_TYPES()["required"]
    assert spec["system_prompt"][1]["default"] == "text-to-image"  # text-only prompt is the default
    assert spec["passthrough_on_empty"][1]["default"] is False  # empty input fails by default


def _enhance_with_reply(reply: str) -> tuple[str]:
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


def test_enhance_refuses_cleaned_empty_reply() -> None:
    with pytest.raises(LiteLLMError, match="empty string downstream"):
        _enhance_with_reply("   \n  ")


def test_enhance_returns_cleaned_prompt() -> None:
    assert _enhance_with_reply("A woman on a rooftop.") == ("A woman on a rooftop.",)
