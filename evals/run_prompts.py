"""Run the frozen Kotodama cases through the same enhancer as the ComfyUI node.

This creates prompt evidence, not an image-quality result. See evals/README.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kotodama.enhancer import KotodamaPromptEnhancer  # noqa: E402

CASES = Path(__file__).with_name("cases.jsonl")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def require_clean_tree() -> None:
    state = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True
    )
    if state.strip():
        raise RuntimeError("Commit the eval and run from a clean tree before collecting evidence")


def load_cases(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ids = [case["id"] for case in cases]
    if not cases or len(ids) != len(set(ids)):
        raise ValueError("Cases must be nonempty and have unique IDs")
    for case in cases:
        if (
            not re.fullmatch(r"[a-z0-9-]+", case["id"])
            or not isinstance(case["idea"], str)
            or not case["idea"].strip()
            or not isinstance(case["must_show"], list)
            or not case["must_show"]
            or any(not isinstance(detail, str) or not detail.strip() for detail in case["must_show"])
        ):
            raise ValueError(f"Incomplete case: {case['id']}")
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Exact chat model ID")
    parser.add_argument(
        "--model-revision",
        required=True,
        help="Operator-declared immutable revision of the served model",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--system-prompt", default="text-to-image")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=5119)
    args = parser.parse_args()

    if args.output.exists():
        parser.error("Output exists; use a new path so prior evidence is preserved")
    if not 0 <= args.temperature <= 2 or args.max_tokens < 64:
        parser.error("Temperature must be 0..2 and max tokens at least 64")

    cases = load_cases(CASES)
    require_clean_tree()
    system_file = ROOT / "system_prompts" / f"{args.system_prompt}.md"
    if not system_file.is_file():
        parser.error(f"System prompt file not found: {system_file}")

    manifest = {
        "schema": 1,
        "purpose": "prompt generation only; no image-quality claim",
        "git_head": git_head(),
        "git_dirty": False,
        "python_version": sys.version.split()[0],
        "cases_sha256": sha256(CASES),
        "system_prompt": args.system_prompt,
        "system_prompt_sha256": sha256(system_file),
        "model": args.model,
        "model_revision_declared": args.model_revision,
        "model_revision_verified_by_runner": False,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "seed": args.seed,
        "rows": [],
    }
    enhancer = KotodamaPromptEnhancer()
    for case in cases:
        start = time.monotonic()
        row = {
            "id": case["id"],
            "idea": case["idea"],
            "must_show": case["must_show"],
        }
        try:
            (row["enhanced"],) = enhancer.enhance(
                text=case["idea"],
                system_prompt=args.system_prompt,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                seed=args.seed,
                passthrough_on_empty=False,
            )
            row["status"] = "ok"
        except Exception as exc:  # A failed completion is evidence, not a dropped case.
            row["status"] = "error"
            row["error_type"] = type(exc).__name__
            # Error strings can include endpoint details. Keep the public artifact
            # free of URLs, credentials, and server response bodies.
        row["latency_ms"] = round((time.monotonic() - start) * 1000, 3)
        manifest["rows"].append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {args.output} ({sum(r['status'] == 'ok' for r in manifest['rows'])}/{len(cases)} completions)")


if __name__ == "__main__":
    main()
