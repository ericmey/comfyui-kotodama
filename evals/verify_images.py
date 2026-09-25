"""Verify rendered PNGs against the frozen queue and ComfyUI graph metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def embedded_graph(raw: bytes) -> dict:
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Not a PNG")
    offset = 8
    while offset + 12 <= len(raw):
        size = struct.unpack(">I", raw[offset : offset + 4])[0]
        kind = raw[offset + 4 : offset + 8]
        data = raw[offset + 8 : offset + 8 + size]
        if len(data) != size:
            raise ValueError("Truncated PNG chunk")
        offset += size + 12
        if kind == b"tEXt" and data.startswith(b"prompt\x00"):
            return json.loads(data.split(b"\x00", 1)[1])
        if kind == b"IEND":
            break
    raise ValueError("PNG lacks ComfyUI prompt metadata")


def verify_one(row: dict, graph: dict, pack: dict, manifest: dict, nodes: dict) -> None:
    inputs = lambda label: graph[nodes[label]]["inputs"]
    if inputs("prompt")["text"] != row["prompt"]:
        raise ValueError("Embedded positive prompt differs from frozen queue")
    if int(inputs("sampler")["seed"]) != row["image_seed"]:
        raise ValueError("Embedded image seed differs from frozen queue")
    latent = inputs("latent")
    if (latent["width"], latent["height"], latent["batch_size"]) != (
        manifest["width"], manifest["height"], 1
    ):
        raise ValueError("Embedded dimensions or batch size differ")
    params = pack["parameters"]
    expected = {
        ("unet", "unet_name"): params["model.unet_name"],
        ("unet", "weight_dtype"): params["model.weight_dtype"],
        ("clip", "clip_name"): params["clip.clip_name"],
        ("clip", "type"): params["clip.type"],
        ("clip", "device"): params["clip.device"],
        ("vae", "vae_name"): params["vae.vae_name"],
        ("sampler", "steps"): params["sampler.steps"],
        ("sampler", "cfg"): params["sampler.cfg"],
        ("sampler", "sampler_name"): params["sampler.name"],
        ("sampler", "scheduler"): params["sampler.scheduler"],
        ("sampler", "denoise"): params["sampler.denoise"],
    }
    for (node, field), value in expected.items():
        if inputs(node)[field] != value:
            raise ValueError(f"Embedded {node}.{field} differs from pack recipe")
    if "lora" in nodes and pack.get("loras") == []:
        loras = inputs("lora")
        if any(loras[f"lora_0{i}"] != "None" for i in range(1, 5)):
            raise ValueError("Unexpected LoRA in supposedly LoRA-free render")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prompt-node", default="201")
    parser.add_argument("--sampler-node", default="302")
    parser.add_argument("--latent-node", default="301")
    parser.add_argument("--unet-node", default="101")
    parser.add_argument("--clip-node", default="102")
    parser.add_argument("--vae-node", default="103")
    parser.add_argument("--lora-node", default="104")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; preserve prior receipt")
    root = args.pairs_dir
    manifest = json.loads((root / "render_manifest.json").read_text())
    pack_path, workflow_path = root / "pack_recipe.json", root / "workflow.json"
    if sha256(pack_path) != manifest["pack_recipe_sha256_declared"]:
        parser.error("Pack recipe hash differs from manifest")
    if sha256(workflow_path) != manifest["workflow_sha256_declared"]:
        parser.error("Workflow hash differs from manifest")
    pack = json.loads(pack_path.read_text())
    if pack["id"] != manifest["checkpoint"]:
        parser.error("Pack ID differs from manifest")
    nodes = {
        "prompt": args.prompt_node, "sampler": args.sampler_node,
        "latent": args.latent_node, "unet": args.unet_node,
        "clip": args.clip_node, "vae": args.vae_node, "lora": args.lora_node,
    }
    queue = [json.loads(line) for line in (root / "render_queue.jsonl").read_text().splitlines()]
    if len(queue) == 0 or len(queue) != len({(row["id"], row["arm"]) for row in queue}):
        parser.error("Empty or duplicate render queue")
    verified = []
    for row in queue:
        expected = f"images/{row['id']}-{row['arm']}.png"
        if row["image_file"] != expected:
            parser.error(f"Unexpected image path: {row['image_file']}")
        image = root / expected
        if not image.is_file():
            parser.error(f"Missing image: {image}")
        raw = image.read_bytes()
        try:
            verify_one(row, embedded_graph(raw), pack, manifest, nodes)
        except (KeyError, TypeError, ValueError) as exc:
            parser.error(f"{expected}: {exc}")
        verified.append({"image_file": expected, "sha256": hashlib.sha256(raw).hexdigest()})
    result = {
        "schema": 1,
        "verified_images": len(verified),
        "pack_recipe_sha256": sha256(pack_path),
        "workflow_sha256": sha256(workflow_path),
        "weights_hash_verified": False,
        "node_ids": nodes,
        "images": verified,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Verified {len(verified)} images against queue and embedded graph")


if __name__ == "__main__":
    main()
