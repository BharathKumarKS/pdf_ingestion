"""
Card generator — Phase 2.

Calls Ollama/Llama 3.2 in a single pass to produce all 7 pedagogical card
types for every chunk ingested in Phase 1.

Card types
----------
summary      – concise overview of the chunk
definition   – key term or concept with explanation
example      – worked example or real-world application
misconception– common error or wrong mental model
question     – Socratic Q&A pair (content = question, answer = answer)
objective    – learning objective statement (Bloom's verb + outcome)
formula      – key equation / formula (or "N/A" if none)
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx
from loguru import logger

from src.core.config import Settings, get_settings
from src.pdf_ingestion.chunker import TextChunk


# ── Card type enum ────────────────────────────────────────────────────────

class CardType(str, Enum):
    SUMMARY       = "summary"
    DEFINITION    = "definition"
    EXAMPLE       = "example"
    MISCONCEPTION = "misconception"
    QUESTION      = "question"
    OBJECTIVE     = "objective"
    FORMULA       = "formula"

ALL_CARD_TYPES = [t.value for t in CardType]


# ── Data contract ─────────────────────────────────────────────────────────

@dataclass
class GeneratedCard:
    card_id:     str
    chunk_id:    str
    document_id: str
    tenant_id:   str
    card_type:   str
    title:       str
    content:     str
    answer:      Optional[str] = None   # question cards only
    metadata:    dict = field(default_factory=dict)


# ── LLM prompt ────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are an expert pedagogy assistant. "
    "Respond ONLY with valid JSON — no markdown fences, no prose."
)

_PROMPT_TMPL = """\
Given the educational text below, produce exactly 7 learning cards.

TEXT:
{text}

Return a JSON object with these exact keys:
{{
  "summary":       {{"title": "...", "content": "..."}},
  "definition":    {{"title": "...", "content": "..."}},
  "example":       {{"title": "...", "content": "..."}},
  "misconception": {{"title": "...", "content": "..."}},
  "question":      {{"title": "...", "content": "...", "answer": "..."}},
  "objective":     {{"title": "...", "content": "..."}},
  "formula":       {{"title": "...", "content": "..."}}
}}

Rules:
- summary:        1-2 sentence overview.
- definition:     define the single most important term.
- example:        one concrete worked example or application.
- misconception:  one common wrong belief and why it is wrong.
- question:       a Socratic question + correct answer.
- objective:      start with a Bloom's verb (e.g. Explain, Calculate, Derive).
- formula:        write the key equation; use "N/A" if there is none.
- All values must be non-empty strings.
"""


# ── Stub (no Ollama needed for tests) ────────────────────────────────────

class StubLLM:
    """Returns deterministic template cards — zero Ollama dependency."""

    def generate_cards_for_chunk(self, chunk: TextChunk) -> list[GeneratedCard]:
        cards = []
        for ct in CardType:
            is_question = ct == CardType.QUESTION
            cards.append(
                GeneratedCard(
                    card_id=str(uuid.uuid4()),
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    tenant_id=chunk.tenant_id,
                    card_type=ct.value,
                    title=f"[stub] {ct.value.capitalize()} for chunk {chunk.chunk_index}",
                    content=f"Stub {ct.value} content: {chunk.text[:60]}…",
                    answer="Stub answer." if is_question else None,
                )
            )
        return cards

    def generate_cards_for_chunks(self, chunks: list[TextChunk]) -> list[GeneratedCard]:
        all_cards: list[GeneratedCard] = []
        for chunk in chunks:
            all_cards.extend(self.generate_cards_for_chunk(chunk))
        return all_cards


# ── Ollama client ─────────────────────────────────────────────────────────

class OllamaCardGenerator:
    """Generates 7 cards per chunk via a single Ollama/Llama 3.2 call."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()

    def generate_cards_for_chunk(self, chunk: TextChunk) -> list[GeneratedCard]:
        prompt = _PROMPT_TMPL.format(text=chunk.text.strip())
        raw_json = self._call_ollama(prompt)
        return self._parse_response(raw_json, chunk)

    def generate_cards_for_chunks(
        self, chunks: list[TextChunk]
    ) -> list[GeneratedCard]:
        all_cards: list[GeneratedCard] = []
        for chunk in chunks:
            try:
                cards = self.generate_cards_for_chunk(chunk)
                all_cards.extend(cards)
                logger.debug(
                    "Generated {} cards for chunk {}", len(cards), chunk.chunk_index
                )
            except Exception as exc:
                logger.warning(
                    "Card generation failed for chunk {} ({}), skipping", chunk.chunk_index, exc
                )
        logger.success(
            "Generated {} cards total for {} chunks",
            len(all_cards), len(chunks),
        )
        return all_cards

    # ── Internals ─────────────────────────────────────────────────────────

    def _call_ollama(self, prompt: str) -> str:
        url = f"{self._cfg.ollama_host}/api/generate"
        payload = {
            "model":  self._cfg.ollama_model,
            "prompt": prompt,
            "system": _SYSTEM,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.3, "top_p": 0.9},
        }
        try:
            resp = httpx.post(url, json=payload, timeout=self._cfg.ollama_timeout)
            resp.raise_for_status()
            return resp.json().get("response", "{}")
        except Exception as exc:
            raise RuntimeError(f"Ollama call failed: {exc}") from exc

    def _parse_response(
        self, raw: str, chunk: TextChunk
    ) -> list[GeneratedCard]:
        # Strip accidental markdown fences
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Attempt partial extraction via regex
            data = self._extract_partial(raw)

        cards: list[GeneratedCard] = []
        for ct in CardType:
            block = data.get(ct.value, {})
            if not isinstance(block, dict):
                block = {}
            title   = str(block.get("title",   f"{ct.value.capitalize()} — chunk {chunk.chunk_index}"))
            content = str(block.get("content", ""))
            answer  = str(block.get("answer", "")) if ct == CardType.QUESTION else None

            cards.append(
                GeneratedCard(
                    card_id=str(uuid.uuid4()),
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    tenant_id=chunk.tenant_id,
                    card_type=ct.value,
                    title=title,
                    content=content or f"[empty {ct.value}]",
                    answer=answer or (None if ct != CardType.QUESTION else ""),
                )
            )
        return cards

    @staticmethod
    def _extract_partial(raw: str) -> dict:
        """Best-effort regex extraction when JSON parse fails entirely."""
        result: dict = {}
        for ct in CardType:
            pattern = rf'"{ct.value}"\s*:\s*\{{([^}}]+)\}}'
            m = re.search(pattern, raw, re.DOTALL)
            if m:
                inner = m.group(1)
                title_m   = re.search(r'"title"\s*:\s*"([^"]+)"', inner)
                content_m = re.search(r'"content"\s*:\s*"([^"]+)"', inner)
                result[ct.value] = {
                    "title":   title_m.group(1)   if title_m   else ct.value,
                    "content": content_m.group(1) if content_m else "",
                }
        return result


# ── Factory ───────────────────────────────────────────────────────────────

def get_card_generator(
    settings: Settings | None = None,
) -> StubLLM | OllamaCardGenerator:
    cfg = settings or get_settings()
    if cfg.use_stub_llm:
        return StubLLM()
    return OllamaCardGenerator(settings=cfg)
