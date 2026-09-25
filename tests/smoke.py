"""Live smoke test, run on the ComfyUI host itself.

A file, not an inline `python -c`: quoting a Python one-liner through
PowerShell over SSH is how you get a ParserError where a result should be.
Usage:  <comfy-python> tests/smoke.py [model]
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kotodama.enhancer import KotodamaPromptEnhancer  # noqa: E402

if len(sys.argv) < 2:
    sys.exit("Usage: python3 tests/smoke.py <your-model-id>")
model = sys.argv[1]

spec = KotodamaPromptEnhancer.INPUT_TYPES()["required"]
print("system_prompts:", spec["system_prompt"][0])
print("models:", len(spec["model"][0]), "| tooltip:", spec["model"][1]["tooltip"])

start = time.time()
(out,) = KotodamaPromptEnhancer().enhance(
    text="a person on a rooftop at night, city lights, raincoat",
    system_prompt="text-to-image",
    model=model,
    temperature=0.8,
    max_tokens=600,
    seed=3,
    passthrough_on_empty=False,
)
elapsed = time.time() - start

print("model:", model)
print(f"elapsed: {elapsed:.1f}s")
print("length:", len(out))
print("clean:", not out.lstrip().lower().startswith(("here", "prompt:", '"', "```")))
print("-----")
print(out[:400])

if not out:
    print("SMOKE FAIL: empty output")
    sys.exit(1)
print("SMOKE PASS")
