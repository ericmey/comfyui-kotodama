# Kotodama paired image eval (pilot)

This eval asks whether Kotodama's rewritten prompt improves a rendered image for
the user's original idea. It is a **12-case authored pilot**, not a claim about
all users, models, or image generators. The cases were written before this
runner was used. The completed pilot and its limits are in
[`results/pilot-2026-09-25/README.md`](results/pilot-2026-09-25/README.md).

## Outcome and controls

For each case, render two images through the **same ComfyUI workflow, image
checkpoint, sampler settings, dimensions, and seed**. The only changed input on
the image-generation path is the text fed to the conditioning node: original
rough idea versus Kotodama's enhanced prompt. Archive metadata also records the
arm and prompt, downstream of generation. A rater sees A/B images, the original
idea, and its required details, but not which arm produced either image. The
rater records:

- Which image better matches the original idea (`A`, `B`, or `tie`).
- Which image is visually stronger (`A`, `B`, or `tie`).
- How many listed details are visibly present in each image (0 to the case's
  listed maximum). Exact lettering should be counted only when legible.

Report every generated pair, including regressions, ties, malformed outputs,
and failed completions. A single example pair can illustrate the method but
cannot establish a win rate. The rater may decide a constraint is not visually
observable; record that in `notes` rather than quietly changing the case.

## Frozen prompt run

Run this from the ComfyUI host with its Python interpreter after configuring
Kotodama in ComfyUI Settings. Supply an exact model ID and an immutable model
revision supplied by the serving operator:

```bash
python evals/run_prompts.py \
  --model YOUR_MODEL_ID \
  --model-revision YOUR_IMMUTABLE_MODEL_REVISION \
  --output /tmp/kotodama-eval/prompts.json
```

The runner calls the same `KotodamaPromptEnhancer.enhance` method as the node.
It captures all twelve cases, including failures and per-case latency. It
records the case and system-prompt hashes, git head, parameters, and the
operator's model revision. **It cannot independently verify that the endpoint
served that revision.** Preserve a separate server-side revision receipt before
publishing a pinned-model claim. The runner does not print or save API keys.

## Prepare and render pairs

Prepare a blinded queue after choosing a fixed Atelier checkpoint pack and
hashing its recipe JSON and API-format ComfyUI workflow:

```bash
python evals/prepare_pairs.py /tmp/kotodama-eval/prompts.json \
  --output-dir /tmp/kotodama-eval/pairs \
  --blind-seed 2112 --image-seed 51000 \
  --width 1248 --height 832 \
  --checkpoint YOUR_CHECKPOINT_ID \
  --pack-sha256 YOUR_PACK_RECIPE_SHA256 \
  --workflow-sha256 YOUR_WORKFLOW_SHA256
```

`render_queue.jsonl` lists the exact prompt and seed for each arm. Render each
row in ComfyUI and save the image to its listed `image_file`. The two rows for
a case must use the same seed. The preparer records pack recipe/workflow hashes
as **operator-declared**, not independently verified. Those hashes do **not**
bind the model weight bytes; state that limit beside any result unless weight
hashes are separately collected. Preserve the recipe/workflow files and check
their hashes in the final run. Keep `answer_key.jsonl` from raters.

Place the recipe and API workflow in the pair directory as `pack_recipe.json`
and `workflow.json`. Verify every PNG's embedded graph before rating. The
default node IDs below match the included Atelier Krea2 graph; pass alternate
IDs when using another ComfyUI workflow:

```bash
python evals/verify_images.py --pairs-dir /tmp/kotodama-eval/pairs \
  --output /tmp/kotodama-eval/pairs/image-verification.json
```

This checks every positive prompt, seed, dimension, loader, sampler parameter,
and absence of LoRAs against the queue and recipe. It still cannot verify the
model weight bytes without separate hashes from the image host.

ComfyUI PNGs contain the full prompt in metadata. Use the blind exporter to
remove that metadata from rater copies while keeping the verified originals:

```bash
python evals/export_blind.py --pairs-dir /tmp/kotodama-eval/pairs \
  --output-dir /tmp/kotodama-eval/rater-1
```

Give raters only that exported directory: `blind_gallery.html`,
`blind_cases.jsonl`, `ratings.csv`, and the numbered images. Do not share the
answer key, render queue, or original PNGs until their ratings are frozen.
They fill every `intent_winner`, `quality_winner`, `details_a`, and `details_b`
cell. If possible, collect two independent rating sheets and show disagreement.
The scorer handles one sheet at a time; pass each completed rater sheet with
`--ratings` against the same verified originals. Report both scores and
disagreements rather than collapsing them into one number. State whether the
raters were people, AI systems, or a mix; do not present agent ratings as
human preference data.

```bash
python evals/score.py --pairs-dir /tmp/kotodama-eval/pairs \
  --ratings /tmp/kotodama-eval/rater-1/ratings.csv \
  --output /tmp/kotodama-eval/rater-1-report.json
```

The scorer rejects incomplete ratings, missing images, or any image whose hash
differs from `image-verification.json`. The report includes
SHA-256 for each rated image. Publish the raw prompt run, render queue,
workflow and pack recipe hashes, images, rating sheets, answer key, scorer
output, and any failures, with a description of the endpoint hardware and
runtime. Keep private endpoint URLs and credentials out of public artifacts.
