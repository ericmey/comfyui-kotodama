"""The node itself: text in, an enhanced prompt out."""

from __future__ import annotations

import re

from . import client, prompts

MAX_SEED = 0xFFFFFFFFFFFFFFFF

# Models routinely wrap their answer in a fence or in quotes - the krea2
# example output is itself shown quoted, so the model copies that. Neither
# belongs in a CLIP conditioning string.
_FENCE = re.compile(r"^```[a-zA-Z]*\n(.*?)\n?```$", re.DOTALL)
_LEAD_IN = re.compile(
    r"^(?:here(?:['\u2019]s| is)[^:\n]*:|prompt:|enhanced prompt:)\s*",
    re.IGNORECASE,
)


def clean(text: str) -> str:
    """Strip the wrappers a chat model adds around a bare prompt."""
    out = text.strip()

    fenced = _FENCE.match(out)
    if fenced:
        out = fenced.group(1).strip()

    out = _LEAD_IN.sub("", out).strip()

    # One pair of wrapping quotes. The krea2 spec REQUIRES quoted signage
    # inside the prompt ("OPEN LATE"), so unwrap only when what is left has
    # balanced quotes - that distinguishes a quoted whole from a prompt that
    # merely happens to end on a quoted sign.
    #
    # Iterating in order and breaking on the first match means a mixed-nested
    # shape like '"‘hi’"' (outer straight, inner curly) only strips the outer
    # straight pair - intentional. Stripping the inner curly pair too would
    # require a second pass and risks eating legitimate inner quotes.
    for quote in ('"', "'", "\u201c\u201d"):
        open_q, close_q = (quote[0], quote[-1])
        if len(out) > 1 and out.startswith(open_q) and out.endswith(close_q):
            inner = out[1:-1]
            balanced = (
                inner.count(open_q) == inner.count(close_q)
                if open_q != close_q
                else inner.count(open_q) % 2 == 0
            )
            if balanced:
                out = inner.strip()
                break

    return out.strip()


class KotodamaPromptEnhancer:
    """Send system prompt + input text to a chat endpoint, return the reply."""

    CATEGORY = "kotodama"
    FUNCTION = "enhance"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    DESCRIPTION = (
        "Rewrites an input prompt through an OpenAI-compatible chat model "
        "using a system prompt "
        "picked from the node's system_prompts/ folder. Output wires into a "
        "CLIPTextEncode text input."
    )

    @classmethod
    def INPUT_TYPES(cls):
        models, live = client.list_models()
        model_tooltip = (
            "Model returned by the configured endpoint."
            if live
            else "Endpoint unavailable or unconfigured; showing the fallback list."
        )
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": (
                            "The rough prompt to enhance. "
                            "Wire it in or type it here."
                        ),
                    },
                ),
                "system_prompt": (
                    prompts.available(),
                    {
                        "default": "text-to-image",
                        "tooltip": "A file in the node's system_prompts/ folder.",
                    },
                ),
                "model": (models, {"tooltip": model_tooltip}),
                "temperature": (
                    "FLOAT",
                    {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.05},
                ),
                "max_tokens": (
                    "INT",
                    {"default": 1024, "min": 64, "max": 32768, "step": 64},
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": MAX_SEED,
                        "tooltip": (
                            "Bump to force a re-run with identical other inputs. "
                            "ComfyUI caches node output on input identity, so "
                            "without a new seed the same text comes back. "
                            "Changing system_prompt, model, temperature, or "
                            "max_tokens already invalidates the cache."
                        ),
                    },
                ),
                "passthrough_on_empty": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": (
                            "Empty input text returns empty without calling the LLM. "
                            "Off = an empty input is an error."
                        ),
                    },
                ),
            },
        }

    @classmethod
    def IS_CHANGED(
        cls,
        text,
        system_prompt,
        model,
        temperature,
        max_tokens,
        seed,
        passthrough_on_empty,
    ):
        # An LLM is not a pure function of its inputs. The cache key has to
        # change whenever ANY input changes - including system_prompt,
        # model, temperature, max_tokens - or swapping one of those silently
        # returns the previously-cached enhanced prompt.
        # seed alone would not catch those edits.
        return (
            text,
            system_prompt,
            model,
            float(temperature),
            int(max_tokens),
            int(seed),
            bool(passthrough_on_empty),
            prompts.fingerprint(system_prompt),
            client.config.safe_base_url(),
        )

    def enhance(
        self,
        text,
        system_prompt,
        model,
        temperature,
        max_tokens,
        seed,
        passthrough_on_empty,
    ):
        source = (text or "").strip()
        if not source:
            if passthrough_on_empty:
                return ("",)
            raise ValueError(
                "Kotodama: input text is empty and passthrough_on_empty is off."
            )

        system = prompts.load(system_prompt)
        if model == client.config.UNCONFIGURED_MODEL:
            raise client.LiteLLMError(
                "Choose a model after setting KOTODAMA_BASE_URL and, if model "
                "discovery is unavailable, KOTODAMA_FALLBACK_MODELS; see the README."
            )
        reply = client.complete(
            model=model,
            system_prompt=system,
            user_text=source,
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            seed=int(seed),
        )
        cleaned = clean(reply)
        if not cleaned:
            raise client.LiteLLMError(
                f"Model '{model}' returned a prompt that cleaned to empty. "
                "Refusing to pass an empty string downstream - "
                "an empty conditioning renders a picture nobody asked for."
            )
        return (cleaned,)
