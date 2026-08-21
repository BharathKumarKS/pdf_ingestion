"""
Pipeline configuration loader.

Reads config.yaml from the project root and provides per-stage LLM settings,
instructor client factory for structured outputs, and token counting.
Falls back to .env Settings when config.yaml is absent.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        logger.warning("config.yaml not found — using .env defaults")
        return {}
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    logger.info("Loaded config.yaml from {}", _CONFIG_PATH)
    return cfg


def get_section(section: str) -> dict[str, Any]:
    return load_config().get(section, {})


def get_model(section: str, fallback: str = "openai/gpt-oss-20b") -> str:
    model = get_section(section).get("model", fallback)
    return model if isinstance(model, str) and model.strip() else fallback


def build_instructor_client(section: str) -> Any:
    """
    Create a patched instructor OpenAI client for the given config section.

    API key precedence:
      1. api_key in config.yaml section
      2. OPENAI_API_KEY environment variable
      3. API_KEY environment variable
      4. "dummy" (for endpoints that don't require auth)
    """
    import instructor
    import openai

    cfg = get_section(section)
    api_key = cfg.get("api_key")
    if not (isinstance(api_key, str) and api_key.strip()):
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY") or "dummy"

    base_url = cfg.get("base_url", "")
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url.strip():
        client_kwargs["base_url"] = base_url

    return instructor.patch(openai.OpenAI(**client_kwargs))


def count_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return len(text) // 4
