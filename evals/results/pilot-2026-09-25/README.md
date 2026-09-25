# Kotodama paired image pilot — 2026-09-25

**Status: independently reproduced before merge.** This is a 12-case authored pilot with one image seed per case and two blinded AI-agent visual raters. It measures these paired renders, not human preference or general performance.

## Question and method

For each rough image idea in `evals/cases.jsonl`, Kotodama produced one enhanced prompt. The rough and enhanced text were rendered through the same ComfyUI graph, loader names, sampler, dimensions, and image seed within each pair. A/B side was balanced and hidden from the two raters. Each rater saw the original idea and four required visible details, then chose which image better matched the idea, which looked better, and how many details were present. Both ratings were frozen before the A/B key was opened.

## Observed results

| Blinded AI-agent rater | Idea match: enhanced | Idea match: rough | Idea match: tie | Visual quality: enhanced | Visual quality: rough | Visual quality: tie | Visible details, enhanced | Visible details, rough |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Yua | 8 | 4 | 0 | 8 | 4 | 0 | 47/48 | 42/48 |
| Aoi | 8 | 2 | 2 | 5 | 2 | 5 | 45/48 | 40/48 |

The raters agreed that the rough prompt better matched the boat-under-bridge idea (`spatial-04`). They disagreed on `material-05`, `weather-08`, and `architecture-11`; Aoi recorded ties on `negative-06` and `typography-09`. All twelve pairs, ratings and notes are included. These are descriptive counts from two AI agents, not a statistical estimate or a human taste study.

## Receipts

- `prompt_run.public.json` is a redacted copy of the original prompt run (source SHA-256 recorded inside). The private routing alias is removed. Twelve of twelve prompt calls succeeded. The runner's declared model identity was not independently tied to weight bytes.
- `render_queue.jsonl` and `answer_key.jsonl` preserve each idea, A/B assignment and paired seed. `render_manifest.json`, `pack_recipe.json`, and `workflow.json` preserve the render setup. The manifest's “no image generation or rating has occurred” note describes its creation time; the subsequent image verification and rating files record the completed run.
- `image-verification.json` binds all 24 original ComfyUI PNG bytes to embedded prompt, seed, dimensions, loader names, sampler settings and absence of LoRAs. The workflow/pack hashes bind recipe files, not the model weights.
- `yua-ratings.csv` and `aoi-ratings.csv` are the frozen sheets. The two `*-score-v2.json` files are the scorer outputs. Image SHA-256 values are in the verification receipt and reports.
- The prompt-run source commit was `1b29f935b650fab8dfb671b667d6cce13098509d`. Its enhancer, client and system prompt files were diff-identical to the code base used for the later eval branch. The prompt runner recorded Python 3.14.7.

## Scope and limits

The ideas were authored by us and are not a blind holdout from users. There is one prompt completion and one render per arm and case, no repeated model sampling, and two AI-agent raters. Aoi explicitly regarded her visual-quality column as uncalibrated; the case notes and disagreement remain visible. The prompt-model routing alias and image-generator weight bytes were not immutably pinned. The prompt endpoint's and image host's hardware and runtime details were not recorded; only the prompt runner's Python version is in the archive. Exact pixel replay is therefore not promised, even though the recorded graphs and image bytes can be checked. This does not establish production quality, a population win rate, or a human preference result.

## Recheck

From the repository root, run `python evals/verify_images.py --pairs-dir evals/results/pilot-2026-09-25 --output /tmp/kotodama-images-recheck.json` to recheck image graphs; then run `python evals/score.py` once for each rating sheet, supplying this directory as `--pairs-dir` and a fresh output path. The scorer checks the archived image bytes against `image-verification.json` and preserves ties and failures. Rechecking with new outputs must not overwrite the archived reports.
