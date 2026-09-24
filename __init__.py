"""Kotodama - 言霊, the spirit that lives in words.

An LLM prompt enhancer for the middle of a ComfyUI workflow.
"""

try:
    from .kotodama.enhancer import KotodamaPromptEnhancer
except ImportError:  # direct-on-path import, matches comfyui-immich
    from kotodama.enhancer import KotodamaPromptEnhancer

NODE_CLASS_MAPPINGS = {
    "KotodamaPromptEnhancer": KotodamaPromptEnhancer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "KotodamaPromptEnhancer": "Kotodama Prompt Enhancer",
}

WEB_DIRECTORY = "./web"

try:
    from server import PromptServer
except ImportError:
    # The network-free tests import the node outside ComfyUI.
    pass
else:
    try:
        from .kotodama.settings import register_routes
    except ImportError:
        from kotodama.settings import register_routes

    register_routes(PromptServer.instance.routes)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
