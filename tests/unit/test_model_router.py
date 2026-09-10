import pytest

from app.graph.model_router import _normalize_model_id, get_stage_models


def test_bare_openrouter_slug_gets_prefixed():
    """The exact friction hit in practice: pasting the slug straight from
    openrouter.ai/models, which never shows the LiteLLM routing prefix."""
    assert _normalize_model_id("google/gemma-4-26b-a4b-it:free") == \
        "openrouter/google/gemma-4-26b-a4b-it:free"


def test_already_prefixed_openrouter_slug_untouched():
    assert _normalize_model_id("openrouter/google/gemma-4-26b-a4b-it:free") == \
        "openrouter/google/gemma-4-26b-a4b-it:free"


def test_cloudflare_prefix_untouched():
    assert _normalize_model_id("cloudflare/@cf/meta/llama-3.1-8b-instruct") == \
        "cloudflare/@cf/meta/llama-3.1-8b-instruct"


def test_get_stage_models_normalizes_env_override(monkeypatch):
    monkeypatch.setenv("ROUTER_MODELS", "google/gemma-4-26b-a4b-it:free, nvidia/nemotron-3-super:free")
    models = get_stage_models("router")
    assert models == [
        "openrouter/google/gemma-4-26b-a4b-it:free",
        "openrouter/nvidia/nemotron-3-super:free",
    ]


def test_get_stage_models_falls_back_to_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("ROUTER_MODELS", raising=False)
    models = get_stage_models("router")
    assert len(models) > 0
    assert all(m.startswith(("openrouter/", "cloudflare/")) for m in models)
