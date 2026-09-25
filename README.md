# Kotodama for ComfyUI

Kotodama takes a rough text idea, asks an OpenAI-compatible chat model to rewrite it as an image prompt, and returns a `STRING` for `CLIPTextEncode`. It accepts **text only**. It does not inspect reference images.


## What it does

One real run: the same image model and the same seed, rendered from each prompt.

| Your rough idea | Kotodama's prompt |
|---|---|
| ![Render from the rough idea](docs/images/example-raw.jpg) | ![Render from the enhanced prompt](docs/images/example-enhanced.jpg) |
| *a lighthouse keeper's cat watching a storm from the window* | *A lighthouse keeper's cat sits in profile on a wide bay window ledge, gazing out at a raging storm through the rain-streaked glass. The cat is a fluffy tabby with striking green eyes … occasional forks of lightning illuminating the churning sea far below. Inside, warm lamplight glows against the cool blue-gray tones of the tempest …* |

The enhancer adds specific, steerable detail (the tabby's green eyes, the lightning, the lamplight on the glass), and the render follows it. This is one illustrative run with the `text-to-image` preset on a local OpenAI-compatible model, generated in 4.8 s. Your model and seed will produce different text. Whether enhancement improves images in general is what the evaluation measures, not this example.

## Install

**From ComfyUI-Manager (recommended):** open **Custom Nodes Manager**, search for **Kotodama Prompt Enhancer**, install, and restart ComfyUI. It is published on the [Comfy Registry](https://registry.comfy.org/nodes/comfyui-kotodama) as `comfyui-kotodama`.

**With comfy-cli:** `comfy node install comfyui-kotodama`

**Manually:** clone or copy this repository into `ComfyUI/custom_nodes/comfyui-kotodama`, then restart ComfyUI. The node uses Python's standard library and needs no extra package install.

Copy `.env.example` to `.env` in this directory and configure the root URL of an OpenAI-compatible service:

```dotenv
KOTODAMA_BASE_URL=http://127.0.0.1:4000
KOTODAMA_API_KEY=your-key-if-required
KOTODAMA_FALLBACK_MODELS=your-model-id
```

The URL is the service root, **without `/v1`**. Kotodama calls `/v1/models` for the menu and `/v1/chat/completions` to run the node. An API key is optional for a trusted local service. Use HTTPS for a remote service. If the model listing route is unavailable, set `KOTODAMA_FALLBACK_MODELS` to one or more exact model IDs, separated by commas. The menu marks that list as a fallback rather than live discovery.

Environment variables override `.env`. Existing installs using `LITELLM_BASE_URL` and `LITELLM_API_KEY` continue to work; the `KOTODAMA_*` names win when both are present. `KOTODAMA_TIMEOUT` defaults to 300 seconds and has a one-second minimum.

For an install managed by a package manager, put the same `.env` file at `<ComfyUI user directory>/kotodama/.env` so replacing the node folder does not remove it. Configuration precedence is process environment, then that user-directory file, then `.env` in this node folder. The **Kotodama connection** row in ComfyUI Settings shows the resolved URL, whether a key is set, which source won, and the preferred file path. Its **Test connection** button checks only the saved endpoint. The panel cannot edit or reveal a key.

**Keep the API key out of node widgets.** ComfyUI saves widget values in workflow JSON and may embed them in generated PNG metadata. `.env` is ignored by Git; keep the file private and restrict access to your ComfyUI host. Anyone who can administer an exposed ComfyUI instance may be able to run nodes or inspect its files, so protect ComfyUI itself.

## Use

Add **Kotodama Prompt Enhancer**, enter or connect rough `text`, select a system prompt and model, then connect its `prompt` output to `CLIPTextEncode.text`. To expose that input on CLIPTextEncode, right-click the node and choose **Convert widget to input → text**.

The default `text-to-image` system prompt works from text alone. The `krea2` preset is retained for existing workflows and has been adjusted to work from text only. You can add your own `.md` or `.txt` file to `system_prompts/` and refresh the browser; its stem appears in the menu. Editing the selected file changes the node's cache identity on the next run. The node strips `### START ###` and `### END ###` banner lines from prompt files.

Changing a widget or the selected prompt file reruns the node. To request another response with otherwise identical inputs, change `seed`. The seed is sent to the chat endpoint, but a provider may ignore it. An empty input is an error by default; enable `passthrough_on_empty` only if an empty downstream conditioning string is intentional.

The node fails visibly on connection, authentication, malformed response, truncated output, and empty output. It will not silently replace a failed request with a blank prompt.

## Privacy and troubleshooting

Your input text and selected system prompt are sent to the configured chat endpoint. Choose an endpoint whose data handling fits your workflow. The generated prompt can also be saved with the workflow or image by ComfyUI.

- **Configure endpoint or fallback model** in the model menu: set `KOTODAMA_BASE_URL` and, if `/v1/models` is unavailable, `KOTODAMA_FALLBACK_MODELS`; then refresh ComfyUI's node menu or restart the server.
- **401/403**: check `KOTODAMA_API_KEY` and your provider's permissions.
- **Connection or timeout**: check the endpoint from the ComfyUI host; raise `KOTODAMA_TIMEOUT`, lower `max_tokens`, or use a faster model if generation is slow.
- **Redirect response**: set `KOTODAMA_BASE_URL` to the final endpoint. Kotodama refuses redirects so the bearer key cannot be forwarded to another URL.
- **Wrong model list**: set `KOTODAMA_FALLBACK_MODELS` to the provider's exact IDs and refresh. A fallback menu does not confirm the endpoint is reachable.

## Tests

The offline suite runs without ComfyUI or a live provider. With [uv](https://docs.astral.sh/uv/):

```sh
uv run --group dev pytest
```

Or with plain pip: `pip install pytest aiohttp` and then `python -m pytest`.

The settings-route tests are included; they need `aiohttp` (part of the dev group, and already provided by ComfyUI).

To test a configured provider from its ComfyUI host, run `python3 tests/smoke.py your-model-id` with the same Python interpreter as ComfyUI. This sends one short test prompt to your endpoint.

## License

MIT. See [LICENSE](LICENSE).

## Credits

Maintained by Eric Mey. This public release was prepared with AI collaborators.
