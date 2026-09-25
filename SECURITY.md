# Security policy

## Reporting a vulnerability

Please report security issues **privately** through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Please don't open a public issue for a suspected vulnerability.

Include what you found, how to reproduce it, and which version or commit you tested. You can expect an acknowledgement within a few days.

## Scope notes

Kotodama sends your prompt text to the OpenAI-compatible endpoint you configure, and stores your endpoint settings and API key in the ComfyUI user directory (`kotodama/.env`). The API key is write-only in the settings panel and is never returned to the browser.

ComfyUI has no login by default. Anyone who can reach your ComfyUI page can use the node and change its settings, so keep ComfyUI on a trusted network. Reports about protecting an internet-exposed ComfyUI itself belong with the ComfyUI project.
