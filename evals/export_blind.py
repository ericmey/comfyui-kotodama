"""Make a rater packet with prompt-bearing PNG metadata removed.

The source PNGs and their verification receipt remain unchanged in pairs-dir.
Only ancillary text chunks are removed; image-data chunks are copied verbatim.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import struct
from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n"
PRIVATE_CHUNKS = {b"tEXt", b"zTXt", b"iTXt", b"eXIf"}


def strip_metadata(raw: bytes) -> bytes:
    if not raw.startswith(PNG):
        raise ValueError("Not a PNG")
    out = bytearray(PNG)
    offset = len(PNG)
    saw_end = False
    while offset + 12 <= len(raw):
        size = struct.unpack(">I", raw[offset : offset + 4])[0]
        end = offset + 12 + size
        if end > len(raw):
            raise ValueError("Truncated PNG chunk")
        kind = raw[offset + 4 : offset + 8]
        if kind not in PRIVATE_CHUNKS:
            out.extend(raw[offset:end])
        offset = end
        if kind == b"IEND":
            saw_end = True
            break
    if not saw_end:
        raise ValueError("PNG lacks IEND")
    return bytes(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Output directory exists; preserve previous rating packet")
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "images").mkdir()
    for name in ("blind_gallery.html", "blind_cases.jsonl", "ratings.csv"):
        shutil.copy2(args.pairs_dir / name, args.output_dir / name)
    with (args.output_dir / "ratings.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))
    paths = {value for row in rows for value in (row["image_a"], row["image_b"])}
    for name in sorted(paths):
        if not name.startswith("images/") or ".." in Path(name).parts:
            parser.error(f"Unsafe image path: {name}")
        source = args.pairs_dir / name
        target = args.output_dir / name
        target.write_bytes(strip_metadata(source.read_bytes()))
    print(f"Exported {len(paths)} blind images to {args.output_dir}")


if __name__ == "__main__":
    main()
