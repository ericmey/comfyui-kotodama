"""Create balanced, blinded image-render pairs from a prompt-run manifest."""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path


def prepare(run: dict, seed: int, image_seed: int) -> tuple[list[dict], list[dict], list[dict]]:
    rng = random.Random(seed)
    queue, key, rating_rows = [], [], []
    successful = [row for row in run["rows"] if row["status"] == "ok"]
    # Balance presentation side so a preference for image A cannot masquerade
    # as an enhancer effect. The final odd case is assigned by the blind seed.
    first_arms = ["raw"] * (len(successful) // 2) + ["enhanced"] * (
        len(successful) - len(successful) // 2
    )
    rng.shuffle(first_arms)
    first_by_id = {row["id"]: arm for row, arm in zip(successful, first_arms)}
    for index, row in enumerate(run["rows"]):
        if row["status"] != "ok":
            continue
        arms = [("raw", row["idea"]), ("enhanced", row["enhanced"])]
        if first_by_id[row["id"]] == "enhanced":
            arms.reverse()
        mapping = {}
        for label, (arm, prompt) in zip(("A", "B"), arms):
            mapping[label] = arm
            queue.append(
                {
                    "id": row["id"],
                    "arm": label,
                    "prompt": prompt,
                    "image_seed": image_seed + index,
                    "image_file": f"images/{row['id']}-{label}.png",
                }
            )
        key.append({"id": row["id"], "A": mapping["A"], "B": mapping["B"]})
        rating_rows.append(
            {
                "id": row["id"],
                "image_a": f"images/{row['id']}-A.png",
                "image_b": f"images/{row['id']}-B.png",
                "intent_winner": "",
                "quality_winner": "",
                "details_a": "",
                "details_b": "",
                "notes": "",
            }
        )
    return queue, key, rating_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="JSON from run_prompts.py")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--blind-seed", type=int, required=True)
    parser.add_argument("--image-seed", type=int, required=True)
    parser.add_argument("--checkpoint", required=True, help="Exact image checkpoint identifier")
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--workflow-sha256", required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Output directory exists; preserve prior evidence")
    run = json.loads(args.run.read_text())
    if run.get("schema") != 1:
        parser.error("Unsupported prompt-run schema")
    if any(
        len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower())
        for value in (args.checkpoint_sha256, args.workflow_sha256)
    ):
        parser.error("Checkpoint and workflow hashes must be SHA-256 hex digests")
    queue, key, rating_rows = prepare(run, args.blind_seed, args.image_seed)
    if not key:
        parser.error("No successful prompt completions to render")
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "images").mkdir()
    (args.output_dir / "render_queue.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in queue)
    )
    (args.output_dir / "answer_key.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in key)
    )
    (args.output_dir / "blind_cases.jsonl").write_text(
        "".join(
            json.dumps(
                {"id": row["id"], "idea": row["idea"], "must_show": row["must_show"]},
                ensure_ascii=False,
            ) + "\n"
            for row in run["rows"] if row["status"] == "ok"
        )
    )
    (args.output_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "prompt_run": str(args.run),
                "checkpoint": args.checkpoint,
                "checkpoint_sha256_declared": args.checkpoint_sha256,
                "workflow_sha256_declared": args.workflow_sha256,
                "hashes_verified_by_runner": False,
                "image_seed_base": args.image_seed,
                "paired_seed_rule": "same case ID uses the same seed for A and B",
                "blind_seed": args.blind_seed,
                "note": "Render queue only; no image generation or rating has occurred",
            },
            indent=2,
        ) + "\n"
    )
    with (args.output_dir / "ratings.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rating_rows[0]))
        writer.writeheader()
        writer.writerows(rating_rows)
    print(f"Prepared {len(key)} blind pairs in {args.output_dir}")


if __name__ == "__main__":
    main()
