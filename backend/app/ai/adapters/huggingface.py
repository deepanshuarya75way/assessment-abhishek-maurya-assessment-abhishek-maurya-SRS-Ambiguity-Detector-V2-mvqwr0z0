"""Hugging Face adapter: identity + Inference Providers router over the shared chat shape.

Generation is `POST /v1/chat/completions` and the credential probe is
`GET /v1/models` on `router.huggingface.co` — the documented
OpenAI-compatible surface (Bearer token, `{object: "list", data: [...]}`),
so the shared implementation fits unmodified. The legacy
`api-inference.huggingface.co` host no longer resolves (NXDOMAIN, verified
2026-09-24), which is why the registry pins the router origin instead.
"""

from app.ai.adapters.openai_compat import OpenAICompatAdapter
from app.ai.registry import PROVIDER_METADATA


class HuggingFaceProvider(OpenAICompatAdapter):
    id = "huggingface"
    display_name = PROVIDER_METADATA["huggingface"].display_name
    base_url = PROVIDER_METADATA["huggingface"].base_url


__all__ = ["HuggingFaceProvider"]
