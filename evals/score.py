"""Score completed blind A/B ratings against the concealed assignment key."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
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
    parser.add_argument("--ratings", type=Path, help="Completed blind rating CSV")
    parser.add_argument(
        "--verification",
        type=Path,
        help="Image verification JSON (defaults to pairs-dir/image-verification.json)",
    )
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; preserve prior result")
    verification_path = args.verification or args.pairs_dir / "image-verification.json"
    verification = json.loads(verification_path.read_text())
    if verification.get("verified_images") != len(verification.get("images", [])):
        parser.error("Malformed image verification receipt")
    verified_hashes = {row["image_file"]: row["sha256"] for row in verification["images"]}
    key = [json.loads(line) for line in (args.pairs_dir / "answer_key.jsonl").read_text().splitlines()]
    ratings_path = args.ratings or args.pairs_dir / "ratings.csv"
    with ratings_path.open(newline="") as file:
        ratings = list(csv.DictReader(file))
    cases = [json.loads(line) for line in args.cases.read_text().splitlines()]
    image_hashes = {}
    render_manifest = json.loads((args.pairs_dir / "render_manifest.json").read_text())
    expected_size = (render_manifest["width"], render_manifest["height"])
    for row in ratings:
        for field in ("image_a", "image_b"):
            arm = "A" if field == "image_a" else "B"
            expected = f"images/{row['id']}-{arm}.png"
            if row[field] != expected:
                parser.error(f"Unexpected image path for {row['id']} {arm}")
            image = args.pairs_dir / row[field]
            if not image.is_file():
                parser.error(f"Rated image is missing: {image}")
            raw = image.read_bytes()
            if not raw.startswith(b"\x89PNG\r\n\x1a\n") or raw[12:16] != b"IHDR":
                parser.error(f"Rated image is not a PNG: {image}")
            if struct.unpack(">II", raw[16:24]) != expected_size:
                parser.error(f"Rated image has wrong dimensions: {image}")
            image_hashes[str(image.relative_to(args.pairs_dir))] = hashlib.sha256(raw).hexdigest()
        if image_hashes[row["image_a"]] == image_hashes[row["image_b"]] and (
            row["intent_winner"].strip().upper() != "TIE"
            or row["quality_winner"].strip().upper() != "TIE"
            or row["details_a"] != row["details_b"]
        ):
            parser.error(f"{row['id']}: identical image files require tie ratings")
    result = score(key, ratings, cases)
    if image_hashes != verified_hashes:
        parser.error("Rated image hashes differ from verification receipt")
    result["image_sha256"] = image_hashes
    result["image_verification_sha256"] = hashlib.sha256(
        verification_path.read_bytes()
    ).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
