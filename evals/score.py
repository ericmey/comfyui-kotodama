"""Score completed blind A/B ratings against the concealed assignment key."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def score(key_rows: list[dict], ratings: list[dict], case_rows: list[dict]) -> dict:
    key = {row["id"]: row for row in key_rows}
    cases = {row["id"]: row for row in case_rows}
    if len(key) != len(key_rows) or len(cases) != len(case_rows):
        raise ValueError("Duplicate IDs")
    if any({row.get("A"), row.get("B")} != {"raw", "enhanced"} for row in key_rows):
        raise ValueError("Each assignment must contain one raw and one enhanced arm")
    if {row["id"] for row in ratings} != set(key) or len(ratings) != len(key):
        raise ValueError("Ratings must cover every rendered pair exactly once")
    totals = {
        "intent": Counter(),
        "quality": Counter(),
        "detail_count": {"raw": 0, "enhanced": 0},
        "detail_possible": 0,
    }
    for row in ratings:
        id_ = row["id"]
        max_details = len(cases[id_]["must_show"])
        for field in ("intent", "quality"):
            choice = row[f"{field}_winner"].strip().upper()
            if choice not in ("A", "B", "TIE"):
                raise ValueError(f"{id_}: {field}_winner must be A, B, or tie")
            totals[field]["tie" if choice == "TIE" else key[id_][choice]] += 1
        for arm in ("A", "B"):
            count = int(row[f"details_{arm.lower()}"])
            if not 0 <= count <= max_details:
                raise ValueError(f"{id_}: details_{arm.lower()} outside 0..{max_details}")
            totals["detail_count"][key[id_][arm]] += count
        totals["detail_possible"] += max_details
    return {
        "pairs": len(ratings),
        "intent_wins": dict(totals["intent"]),
        "quality_wins": dict(totals["quality"]),
        "details_present": totals["detail_count"],
        "details_possible_per_arm": totals["detail_possible"],
        "limits": "Authored cases and human ratings; no population or causal claim beyond these paired renders.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs-dir", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; preserve prior result")
    key = [json.loads(line) for line in (args.pairs_dir / "answer_key.jsonl").read_text().splitlines()]
    with (args.pairs_dir / "ratings.csv").open(newline="") as file:
        ratings = list(csv.DictReader(file))
    cases = [json.loads(line) for line in args.cases.read_text().splitlines()]
    image_hashes = {}
    for row in ratings:
        for field in ("image_a", "image_b"):
            arm = "A" if field == "image_a" else "B"
            expected = f"images/{row['id']}-{arm}.png"
            if row[field] != expected:
                parser.error(f"Unexpected image path for {row['id']} {arm}")
            image = args.pairs_dir / row[field]
            if not image.is_file():
                parser.error(f"Rated image is missing: {image}")
            if not image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                parser.error(f"Rated image is not a PNG: {image}")
            image_hashes[str(image.relative_to(args.pairs_dir))] = hashlib.sha256(
                image.read_bytes()
            ).hexdigest()
    result = score(key, ratings, cases)
    result["image_sha256"] = image_hashes
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
