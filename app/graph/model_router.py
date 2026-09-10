"""LiteLLM-backed model router (doc §4, §6.2, §10.2). One SDK surface
across OpenRouter and Cloudflare Workers AI, with an ordered fallback
list per stage: if the primary free model is rate-limited or
unavailable, the next candidate is tried automatically, gated by the
quota monitor so we pre-empt a call we already know will fail.

Zero-cost constraint: every model_id below must resolve to a free-tier
endpoint. Swap the model_id strings in STAGE_MODELS to change providers
without touching any node code.
"""
from __future__ import annotations

import os

import litellm

from app.observability.quota_monitor import quota_monitor

# doc §6.2 model assignment. First entry per stage is primary; the rest
# are the failover chain, tried in order.
STAGE_MODELS: dict[str, list[str]] = {
    "router": [
        "cloudflare/@cf/meta/llama-3.1-8b-instruct",
        "openrouter/meta-llama/llama-3.2-3b-instruct:free",
    ],
    "sql_generator": [
        "openrouter/qwen/qwen-2.5-coder-32b-instruct:free",
        "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    ],
    "analyst": [
        "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/openai/gpt-oss-120b:free",
    ],
    "narrator": [
        "openrouter/mistralai/mistral-7b-instruct:free",
        "openrouter/meta-llama/llama-3.2-3b-instruct:free",
    ],
}

STAGE_PROVIDER_FOR_QUOTA: dict[str, str] = {
    "cloudflare": "cloudflare_workers_ai",
    "openrouter": "openrouter",
}


class AllProvidersExhaustedError(RuntimeError):
    """Raised when every candidate in a stage's fallback chain is either
    quota-exhausted or fails the call. The system returns an honest
    'temporarily rate-limited' message rather than an error (doc §10.2).
    """


def _provider_key(model_id: str) -> str:
    prefix = model_id.split("/", 1)[0]
    return STAGE_PROVIDER_FOR_QUOTA.get(prefix, prefix)


def call_stage(
    stage: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> str:
    """Tries each candidate model for `stage` in order, skipping any whose
    provider is already at its rate/quota limit, and falling over to the
    next candidate on a hard failure.
    """
    candidates = STAGE_MODELS.get(stage)
    if not candidates:
        raise ValueError(f"No models configured for stage '{stage}'")

    last_error: Exception | None = None

    for model_id in candidates:
        provider = _provider_key(model_id)

        if not quota_monitor.can_call(provider):
            continue

        try:
            response = litellm.completion(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=_api_key_for(model_id),
            )
            quota_monitor.record_call(provider)
            return response.choices[0].message.content
        except Exception as e:  # rate limit, timeout, provider outage, etc.
            last_error = e
            continue

    raise AllProvidersExhaustedError(
        f"All candidates for stage '{stage}' exhausted or unavailable. "
        f"Last error: {last_error}"
    )


def _api_key_for(model_id: str) -> str | None:
    if model_id.startswith("openrouter/"):
        return os.environ.get("OPENROUTER_API_KEY")
    if model_id.startswith("cloudflare/"):
        return os.environ.get("CLOUDFLARE_API_TOKEN")
    return None
