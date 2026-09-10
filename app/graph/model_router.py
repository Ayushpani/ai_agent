"""LiteLLM-backed model router (doc §4, §6.2, §10.2). One SDK surface
across OpenRouter and Cloudflare Workers AI, with an ordered fallback
list per stage: if the primary free model is rate-limited or
unavailable, the next candidate is tried automatically, gated by the
quota monitor so we pre-empt a call we already know will fail.

Zero-cost constraint: every model_id below must resolve to a free-tier
endpoint.

Free-tier catalogs (especially OpenRouter's ":free" models) rotate and
deprecate on a timescale of weeks, not years — a slug hardcoded here
will eventually 404 the way any specific "current best free model"
claim would. Rather than re-editing this file every time that happens,
every stage's model list is overridable from the environment:

    ROUTER_MODELS=some-provider/some-model:free,fallback-provider/fallback:free
    SQL_GENERATOR_MODELS=...
    ANALYST_MODELS=...
    NARRATOR_MODELS=...

(comma-separated, first entry = primary, rest = failover chain). To find
a slug that is actually live right now: go to
https://openrouter.ai/models, filter to Free, open a model, and copy
the bare slug shown there (e.g. "google/gemma-4-26b-a4b-it:free") — the
human-readable name shown in the OpenRouter UI (e.g. "Google: Gemma 4
26B A4B (free)") is NOT the slug and will not work. You do not need to
add an "openrouter/" prefix yourself — _normalize_model_id below adds
it automatically for anything without a recognized provider prefix,
since that prefix is a LiteLLM routing detail OpenRouter's own site
never shows.
"""
from __future__ import annotations

import os

import litellm

from app.observability.quota_monitor import quota_monitor

# Fallback defaults used only when the corresponding env var is unset.
# Treat these as "known to have worked at some point" rather than a
# live guarantee — see the module docstring for how to replace them.
_DEFAULT_STAGE_MODELS: dict[str, list[str]] = {
    "router": [
        "openrouter/meta-llama/llama-3.2-3b-instruct:free",
        "cloudflare/@cf/meta/llama-3.1-8b-instruct",
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
    # Deep-research stages. The planner emits a small structured JSON, so
    # it runs on the same class of model as the router; synthesis is the
    # hardest cognitive step in the system and gets the strongest model.
    "research_planner": [
        "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/openai/gpt-oss-120b:free",
    ],
    "synthesis": [
        "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/openai/gpt-oss-120b:free",
    ],
}

_ENV_VAR_FOR_STAGE: dict[str, str] = {
    "router": "ROUTER_MODELS",
    "sql_generator": "SQL_GENERATOR_MODELS",
    "analyst": "ANALYST_MODELS",
    "narrator": "NARRATOR_MODELS",
    "research_planner": "RESEARCH_PLANNER_MODELS",
    "synthesis": "SYNTHESIS_MODELS",
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


_KNOWN_PROVIDER_PREFIXES = ("openrouter/", "cloudflare/")


def _normalize_model_id(model_id: str) -> str:
    """LiteLLM needs a '<provider>/<model>' route prefix to know which
    API to call, but OpenRouter's own site never shows that prefix — it
    only ever displays the bare slug (e.g. 'google/gemma-4-26b-a4b-it:free').
    Pasting that bare slug straight from openrouter.ai/models is the
    expected, easy mistake, so default anything without a recognized
    prefix to OpenRouter rather than erroring on it.
    """
    if model_id.startswith(_KNOWN_PROVIDER_PREFIXES):
        return model_id
    return f"openrouter/{model_id}"


def get_stage_models(stage: str) -> list[str]:
    env_var = _ENV_VAR_FOR_STAGE.get(stage)
    raw = os.environ.get(env_var) if env_var else None
    if raw:
        return [_normalize_model_id(m.strip()) for m in raw.split(",") if m.strip()]
    return _DEFAULT_STAGE_MODELS.get(stage, [])


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
    candidates = get_stage_models(stage)
    if not candidates:
        raise ValueError(
            f"No models configured for stage '{stage}'. Set "
            f"{_ENV_VAR_FOR_STAGE.get(stage, stage.upper() + '_MODELS')} in .env."
        )

    errors: list[str] = []

    for model_id in candidates:
        provider = _provider_key(model_id)

        if not quota_monitor.can_call(provider):
            errors.append(f"{model_id}: provider quota/rate limit reached locally")
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
                # A shared free-tier pool being momentarily saturated
                # (HTTP 429) is common and usually clears within seconds —
                # retry the SAME model a couple of times with backoff
                # before giving up on it and moving to the next candidate.
                num_retries=2,
            )
            quota_monitor.record_call(provider)
            return response.choices[0].message.content
        except Exception as e:  # rate limit, timeout, provider outage, bad slug, etc.
            errors.append(f"{model_id}: {e}")
            continue

    env_var = _ENV_VAR_FOR_STAGE.get(stage, stage.upper() + "_MODELS")
    raise AllProvidersExhaustedError(
        f"All candidates for stage '{stage}' failed:\n"
        + "\n".join(f"  - {err}" for err in errors)
        + f"\nIf these are 404/model-not-found errors, the slug(s) have "
        f"rotated out of the provider's free catalog — set {env_var} in "
        f".env to a currently-live slug (see this module's docstring)."
    )


def _api_key_for(model_id: str) -> str | None:
    if model_id.startswith("openrouter/"):
        return os.environ.get("OPENROUTER_API_KEY")
    if model_id.startswith("cloudflare/"):
        return os.environ.get("CLOUDFLARE_API_TOKEN")
    return None
