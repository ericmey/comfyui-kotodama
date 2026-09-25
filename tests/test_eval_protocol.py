"""Contract tests for the eval's pairing and scoring arithmetic."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))

from prepare_pairs import prepare  # noqa: E402
from score import score  # noqa: E402
from verify_images import verify_one  # noqa: E402
from export_blind import strip_metadata  # noqa: E402


class EvalProtocolTests(unittest.TestCase):
    def test_pair_arms_share_image_seed_and_keep_both_prompts(self):
        run = {
            "rows": [
                {"id": "one", "idea": "raw", "enhanced": "better", "status": "ok"},
                {"id": "two", "idea": "raw2", "enhanced": "better2", "status": "ok"},
            ]
        }
        queue, key, ratings = prepare(run, seed=11, image_seed=900)
        self.assertEqual(len(queue), 4)
        self.assertEqual(len(key), len(ratings), 2)
        self.assertEqual(
            {item["prompt"] for item in queue}, {"raw", "better", "raw2", "better2"}
        )
        self.assertEqual([item["image_seed"] for item in queue], [900, 900, 901, 901])
        self.assertTrue(
            all({item["A"], item["B"]} == {"raw", "enhanced"} for item in key)
        )

    def test_scoring_unblinds_winners_and_rejects_missing_ratings(self):
        key = [{"id": "one", "A": "enhanced", "B": "raw"}]
        cases = [{"id": "one", "must_show": ["x", "y"]}]
        rating = [{"id": "one", "intent_winner": "A", "quality_winner": "tie", "details_a": "2", "details_b": "1"}]
        result = score(key, rating, cases)
        self.assertEqual(result["intent_wins"], {"enhanced": 1})
        self.assertEqual(result["quality_wins"], {"tie": 1})
        self.assertEqual(result["details_present"], {"raw": 1, "enhanced": 2})
        self.assertEqual(result["details_possible_per_arm"], 2)
        with self.assertRaisesRegex(ValueError, "every rendered pair"):
            score(key, [], cases)

    def test_embedded_graph_must_match_prompt_seed_and_pack(self):
        graph = {
            "1": {"inputs": {"text": "raw prompt"}},
            "2": {"inputs": {"seed": 42, "steps": 8, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
            "3": {"inputs": {"width": 512, "height": 512, "batch_size": 1}},
            "4": {"inputs": {"unet_name": "model", "weight_dtype": "default"}},
            "5": {"inputs": {"clip_name": "clip", "type": "krea2", "device": "default"}},
            "6": {"inputs": {"vae_name": "vae"}},
            "7": {"inputs": {f"lora_0{i}": "None" for i in range(1, 5)}},
        }
        nodes = dict(prompt="1", sampler="2", latent="3", unet="4", clip="5", vae="6", lora="7")
        pack = {"loras": [], "parameters": {
            "model.unet_name": "model", "model.weight_dtype": "default",
            "clip.clip_name": "clip", "clip.type": "krea2", "clip.device": "default",
            "vae.vae_name": "vae", "sampler.steps": 8, "sampler.cfg": 1.0,
            "sampler.name": "euler", "sampler.scheduler": "simple", "sampler.denoise": 1.0,
        }}
        row = {"prompt": "raw prompt", "image_seed": 42}
        manifest = {"width": 512, "height": 512}
        verify_one(row, graph, pack, manifest, nodes)
        graph["2"]["inputs"]["seed"] = 43
        with self.assertRaisesRegex(ValueError, "seed"):
            verify_one(row, graph, pack, manifest, nodes)

    def test_blind_export_removes_prompt_chunk_without_changing_image_data(self):
        import struct
        import zlib

        def chunk(kind, body):
            checksum = zlib.crc32(kind + body) & 0xFFFFFFFF
            return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", checksum)

        signature = b"\x89PNG\r\n\x1a\n"
        image_data = chunk(b"IDAT", b"pixel bytes")
        original = signature + chunk(b"tEXt", b"prompt\x00secret prompt") + image_data + chunk(b"IEND", b"")
        blind = strip_metadata(original)
        self.assertNotIn(b"secret prompt", blind)
        self.assertIn(image_data, blind)
        self.assertEqual(blind, signature + image_data + chunk(b"IEND", b""))


if __name__ == "__main__":
    unittest.main()
