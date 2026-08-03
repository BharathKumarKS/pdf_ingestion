"""
Shared LLM caller — routes to Ollama or an OpenAI-compatible cluster.

All Phase 2 + Phase 3 LLM calls (card generation, RAPTOR summaries,
concept extraction) go through call_llm() so switching backends is a
single .env change:

  LLM_BACKEND=ollama   →  POST /api/generate   (Ollama format)
  LLM_BACKEND=openai   →  POST /v1/chat/completions  (OpenAI format)

The OpenAI path works with any OpenAI-compatible server:
  vLLM, LiteLLM, Together AI, Anyscale, Azure OpenAI, etc.
No ollama pull, no ollama serve — just point OPENAI_API_BASE at your
cluster endpoint and set OPENAI_MODEL to whatever the server exposes.
"""
from __future__ import annotations

import json

import httpx
from loguru import logger

from src.core.config import Settings, get_settings


def call_llm(
    prompt: str,
    system: str = "",
    settings: Settings | None = None,
    timeout: int | None = None,
    json_mode: bool = False,
) -> str:
    """
    Send a prompt to the configured LLM backend and return the response text.

    Args:
        prompt:    User prompt text.
        system:    Optional system message (ignored by some backends).
        settings:  Settings instance; falls back to get_settings().
        timeout:   Override the default timeout in seconds.
        json_mode: Request JSON output (format="json" on Ollama;
                   response_format={"type":"json_object"} on OpenAI).

    Returns:
        Raw response string from the model. Empty string on failure.
    """
    cfg = settings or get_settings()

    if cfg.use_stub_llm:
        return "{}"

    t = timeout or cfg.ollama_timeout

    if cfg.llm_backend == "openai":
        return _call_openai(prompt, system, cfg, t, json_mode)
    return _call_ollama(prompt, system, cfg, t, json_mode)


# ── Ollama ─────────────────────────────────────────────────────────────────

def _call_ollama(
    prompt: str,
    system: str,
    cfg: Settings,
    timeout: int,
    json_mode: bool,
) -> str:
    payload: dict = {
        "model":  cfg.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "top_p": 0.9},
    }
    if system:
        payload["system"] = system
    if json_mode:
        payload["format"] = "json"

    try:
        resp = httpx.post(
            f"{cfg.ollama_host}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as exc:
        logger.warning("Ollama call failed: {}", exc)
        return ""


# ── OpenAI-compatible ──────────────────────────────────────────────────────

def _call_openai(
    prompt: str,
    system: str,
    cfg: Settings,
    timeout: int,
    json_mode: bool,
) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model":       cfg.openai_model,
        "messages":    messages,
        "temperature": 0.3,
        "top_p":       0.9,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {"Content-Type": "application/json"}
    if cfg.openai_api_key and cfg.openai_api_key.lower() != "none":
        headers["Authorization"] = f"Bearer {cfg.openai_api_key}"

    try:
        resp = httpx.post(
            f"{cfg.openai_api_base.rstrip('/')}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        choices = resp.json().get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")
    except Exception as exc:
        logger.warning("OpenAI-compatible LLM call failed: {}", exc)
        return ""
