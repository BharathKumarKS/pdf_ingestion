"""
Card generator -- Phase 2.

Calls Ollama/Llama 3.2 in a single pass to produce all 7 pedagogical card
types for every chunk ingested in Phase 1.

Card types
----------
summary      -- concise overview of the chunk
definition   -- key term or concept with explanation
example      -- worked example or real-world application
misconception-- common error or wrong mental model
question     -- Socratic Q&A pair (content = question, answer = answer)
objective    -- learning objective statement (Bloom's verb + outcome)
formula      -- key equation / formula (or "N/A" if none)

Performance
-----------
generate_cards_for_chunks() uses a ThreadPoolExecutor with CARD_GEN_WORKERS
threads so multiple Ollama requests run in parallel. On a GPU VM with Ollama
serving Llama 3.2, setting CARD_GEN_WORKERS=8 cuts card generation time by
~8x (from ~25 hours sequential to ~3 hours for 5k chunks).
"""
from __future__ import annotations

import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx
from loguru import logger

from src.core.config import Settings, get_settings
from src.pdf_ingestion.chunker import TextChunk


# -- Card type enum ------------------------------------------------------------

class CardType(str, Enum):
    SUMMARY       = "summary"
    DEFINITION    = "definition"
    EXAMPLE       = "example"
    MISCONCEPTION = "misconception"
    QUESTION      = "question"
    OBJECTIVE     = "objective"
    FORMULA       = "formula"

ALL_CARD_TYPES = [t.value for t in CardType]


# -- Data contract -------------------------------------------------------------

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


# -- LLM prompt ----------------------------------------------------------------

_SYSTEM = (
    "You are an expert pedagogy assistant. "
    "Respond ONLY with valid JSON -- no markdown fences, no prose."
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


# -- Stub (no Ollama needed for tests) -----------------------------------------

class StubLLM:
    """Returns deterministic template cards -- zero Ollama dependency."""

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
                    content=f"Stub {ct.value} content: {chunk.text[:60]}...",
                    answer="Stub answer." if is_question else None,
                )
            )
        return cards

    def generate_cards_for_chunks(self, chunks: list[TextChunk]) -> list[GeneratedCard]:
        all_cards: list[GeneratedCard] = []
        for chunk in chunks:
            all_cards.extend(self.generate_cards_for_chunk(chunk))
        return all_cards


# -- Ollama client -------------------------------------------------------------

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
        """
        Generate cards for all chunks in parallel using a thread pool.

        Each Ollama HTTP call is independent, so threads provide real
        concurrency even with the GIL. CARD_GEN_WORKERS controls parallelism
        (default 4; increase to 8+ on a GPU VM running Ollama).
        """
        workers = self._cfg.card_gen_workers
        all_cards: list[GeneratedCard] = []
        failed = 0

        logger.info(
            "Generating cards for {} chunks with {} parallel workers...",
            len(chunks), workers,
        )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_chunk = {
                executor.submit(self.generate_cards_for_chunk, chunk): chunk
                for chunk in chunks
            }
            for future in as_completed(future_to_chunk):
                chunk = future_to_chunk[future]
                try:
                    cards = future.result()
                    all_cards.extend(cards)
                    if chunk.chunk_index % 100 == 0:
                        logger.debug(
                            "Progress: {} cards done (chunk {})",
                            len(all_cards), chunk.chunk_index,
                        )
                except Exception as exc:
                    failed += 1
                    logger.warning(
                        "Card generation failed for chunk {} ({}), skipping",
                        chunk.chunk_index, exc,
                    )

        logger.success(
            "Generated {} cards for {} chunks ({} failed)",
            len(all_cards), len(chunks), failed,
        )
        return all_cards

    # -- Internals -------------------------------------------------------------

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
            data = self._extract_partial(raw)

        cards: list[GeneratedCard] = []
        for ct in CardType:
            block = data.get(ct.value, {})
            if not isinstance(block, dict):
                block = {}
            title   = str(block.get("title",   f"{ct.value.capitalize()} -- chunk {chunk.chunk_index}"))
            content = str(block.get("content", ""))
            if ct == CardType.QUESTION:
                raw_answer = str(block.get("answer", "")).strip()
                answer = raw_answer if raw_answer else None
            else:
                answer = None

            cards.append(
                GeneratedCard(
                    card_id=str(uuid.uuid4()),
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    tenant_id=chunk.tenant_id,
                    card_type=ct.value,
                    title=title,
                    content=content or f"[empty {ct.value}]",
                    answer=answer,
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
                entry: dict = {
                    "title":   title_m.group(1)   if title_m   else ct.value,
                    "content": content_m.group(1) if content_m else "",
                }
                if ct == CardType.QUESTION:
                    answer_m = re.search(r'"answer"\s*:\s*"([^"]+)"', inner)
                    entry["answer"] = answer_m.group(1) if answer_m else ""
                    if not answer_m:
                        logger.warning(
                            "Could not extract 'answer' from partial JSON for question card"
                        )
                result[ct.value] = entry
        return result


# -- Factory -------------------------------------------------------------------

def get_card_generator(
    settings: Settings | None = None,
) -> StubLLM | OllamaCardGenerator:
    cfg = settings or get_settings()
    if cfg.use_stub_llm:
        return StubLLM()
    return OllamaCardGenerator(settings=cfg)
