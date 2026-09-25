"""Contract tests for the eval's pairing and scoring arithmetic."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))

from prepare_pairs import prepare  # noqa: E402
from score import score  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
