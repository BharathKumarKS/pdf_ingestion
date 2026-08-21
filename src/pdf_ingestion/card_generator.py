"""
Card generator -- Phase 2.

Generates pedagogical cards for every chunk ingested in Phase 1.
Each card type uses a dedicated COSTAR-format prompt loaded from
src/pdf_ingestion/prompts/. One LLM call is made per card type per chunk;
calls across types are parallelised within each chunk.

Card types
----------
summary       -- concise overview of the chunk (COSTAR summarizer prompt)
definition    -- key term or concept with explanation
example       -- worked example or real-world application
misconception -- common error or wrong mental model
question      -- 5-10 QA pairs per chunk (COSTAR qa_generator prompt)
objective     -- learning objective (Bloom's verb + outcome)
formula       -- key equation / formula
factoid       -- atomic, self-contained propositions (COSTAR propositioner prompt)

Performance
-----------
generate_cards_for_chunks() parallelises across chunks using CARD_GEN_WORKERS
threads. Within each chunk, all card-type calls are also parallelised, giving
O(workers × card_types) throughput on a GPU VM with Ollama.
"""
from __future__ import annotations

import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel

from src.core.config import Settings, get_settings
from src.pdf_ingestion.chunker import TextChunk


# -- Prompt loading ------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load a COSTAR prompt template from the prompts directory."""
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


# -- Card type enum ------------------------------------------------------------

class CardType(str, Enum):
    SUMMARY       = "summary"
    DEFINITION    = "definition"
    EXAMPLE       = "example"
    MISCONCEPTION = "misconception"
    QUESTION      = "question"
    OBJECTIVE     = "objective"
    FORMULA       = "formula"
    FACTOID       = "factoid"

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


# -- Pydantic response schemas (instructor enforces these) ---------------------

class _SingleCard(BaseModel):
    title: str
    content: str

class _NullableCard(BaseModel):
    title:   Optional[str] = None
    content: Optional[str] = None

class _QAPair(BaseModel):
    question: str
    answer:   str

class _QAPairList(BaseModel):
    pairs: list[_QAPair]

class _FactoidList(BaseModel):
    factoids: list[str]


# -- Response parsers ----------------------------------------------------------

class ResponseParser:
    """Stateless parsers for each card type's LLM response format."""

    _SKIP = {"n/a", "none", "not applicable", "no formula", "null", ""}

    @classmethod
    def _clean(cls, raw: str) -> str:
        return re.sub(r"```(?:json)?", "", raw).strip()

    @classmethod
    def _try_json(cls, raw: str):
        try:
            return json.loads(cls._clean(raw))
        except json.JSONDecodeError:
            return None

    @classmethod
    def parse_single_object(
        cls, raw: str, chunk: TextChunk, card_type: CardType
    ) -> list[GeneratedCard]:
        """Parse a {title, content} JSON object → 0 or 1 card."""
        data = cls._try_json(raw)
        if not data or not isinstance(data, dict):
            return []
        if str(data.get("content", "")).strip().lower() in cls._SKIP:
            return []
        if data is None or raw.strip().lower() in ("null", ""):
            return []
        content = str(data.get("content", "")).strip()
        if not content or content.lower() in cls._SKIP:
            return []
        return [GeneratedCard(
            card_id=str(uuid.uuid4()),
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            tenant_id=chunk.tenant_id,
            card_type=card_type.value,
            title=str(data.get("title", card_type.value.capitalize())).strip(),
            content=content,
        )]

    @classmethod
    def parse_qa_pairs(cls, raw: str, chunk: TextChunk) -> list[GeneratedCard]:
        """Parse a [{question, answer}] JSON array → multiple question cards."""
        data = cls._try_json(raw)
        if not isinstance(data, list):
            return []
        cards = []
        for item in data:
            if not isinstance(item, dict):
                continue
            q = str(item.get("question", "")).strip()
            a = str(item.get("answer", "")).strip()
            if not q or not a or q.lower() in cls._SKIP:
                continue
            cards.append(GeneratedCard(
                card_id=str(uuid.uuid4()),
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                tenant_id=chunk.tenant_id,
                card_type=CardType.QUESTION.value,
                title=q[:120],
                content=q,
                answer=a,
            ))
        return cards

    @classmethod
    def parse_factoids(cls, raw: str, chunk: TextChunk) -> list[GeneratedCard]:
        """Parse a [string, ...] JSON array → multiple factoid cards."""
        data = cls._try_json(raw)
        if not isinstance(data, list):
            return []
        cards = []
        for item in data:
            text = str(item).strip()
            if not text or text.lower() in cls._SKIP:
                continue
            cards.append(GeneratedCard(
                card_id=str(uuid.uuid4()),
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                tenant_id=chunk.tenant_id,
                card_type=CardType.FACTOID.value,
                title=text[:120],
                content=text,
            ))
        return cards


# -- Per-type generation config ------------------------------------------------

@dataclass
class _TypeConfig:
    prompt_file: str
    json_mode:   bool
    parser:      str   # "single_object" | "qa_pairs" | "factoids"


_TYPE_CONFIGS: dict[CardType, _TypeConfig] = {
    CardType.SUMMARY:       _TypeConfig("summarizer.md",                json_mode=False, parser="single_object"),
    CardType.DEFINITION:    _TypeConfig("definition.md",                json_mode=True,  parser="single_object"),
    CardType.EXAMPLE:       _TypeConfig("example.md",                   json_mode=True,  parser="single_object"),
    CardType.MISCONCEPTION: _TypeConfig("misconception.md",             json_mode=True,  parser="single_object"),
    CardType.QUESTION:      _TypeConfig("question_answer_generator.md", json_mode=True,  parser="qa_pairs"),
    CardType.OBJECTIVE:     _TypeConfig("objective.md",                 json_mode=True,  parser="single_object"),
    CardType.FORMULA:       _TypeConfig("formula.md",                   json_mode=True,  parser="single_object"),
    CardType.FACTOID:       _TypeConfig("propositioner.md",             json_mode=True,  parser="factoids"),
}

# Summary uses token placeholders — fill with sensible defaults for chunk cards
_SUMMARY_MIN_TOKENS = 50
_SUMMARY_MAX_TOKENS = 150


# -- Stub (no Ollama needed for tests) -----------------------------------------

class StubLLM:
    """Returns deterministic template cards — zero Ollama dependency."""

    def generate_cards_for_chunk(self, chunk: TextChunk) -> list[GeneratedCard]:
        cards = []
        for ct in CardType:
            is_question = ct == CardType.QUESTION
            is_factoid  = ct == CardType.FACTOID
            cards.append(GeneratedCard(
                card_id=str(uuid.uuid4()),
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                tenant_id=chunk.tenant_id,
                card_type=ct.value,
                title=f"[stub] {ct.value.capitalize()} for chunk {chunk.chunk_index}",
                content=f"Stub {ct.value} content: {chunk.text[:60]}...",
                answer="Stub answer." if is_question else None,
            ))
        return cards

    def generate_cards_for_chunks(self, chunks: list[TextChunk]) -> list[GeneratedCard]:
        all_cards: list[GeneratedCard] = []
        for chunk in chunks:
            all_cards.extend(self.generate_cards_for_chunk(chunk))
        return all_cards


# -- LLM card generator --------------------------------------------------------

class OllamaCardGenerator:
    """
    Generates cards for each chunk via one LLM call per card type.
    Uses instructor + Pydantic for structured outputs when config.yaml
    provides an endpoint; falls back to raw JSON parsing otherwise.
    Calls are parallelised across card types within each chunk, and across
    chunks using CARD_GEN_WORKERS threads.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg     = settings or get_settings()
        self._prompts = self._load_all_prompts()
        self._parser  = ResponseParser()
        self._instructor_client = self._init_instructor_client()

    @staticmethod
    def _init_instructor_client():
        """Build instructor client from config.yaml if available."""
        try:
            from src.core.pipeline_config import build_instructor_client
            client = build_instructor_client("card_generation")
            logger.info("CardGenerator: using instructor client (structured outputs)")
            return client
        except Exception as exc:
            logger.warning("CardGenerator: instructor unavailable ({}), using raw LLM", exc)
            return None

    @staticmethod
    def _load_all_prompts() -> dict[CardType, str]:
        prompts = {}
        for ct, cfg in _TYPE_CONFIGS.items():
            try:
                prompts[ct] = _load_prompt(cfg.prompt_file)
            except FileNotFoundError as exc:
                logger.warning("Prompt file missing for {}: {}", ct.value, exc)
        return prompts

    # -- Public API ------------------------------------------------------------

    def generate_cards_for_chunk(self, chunk: TextChunk) -> list[GeneratedCard]:
        """Generate all card types for one chunk, parallelised across types."""
        all_cards: list[GeneratedCard] = []
        with ThreadPoolExecutor(max_workers=len(CardType)) as pool:
            futures = {
                pool.submit(self._generate_one_type, chunk, ct): ct
                for ct in CardType
                if ct in self._prompts
            }
            for future in as_completed(futures):
                ct = futures[future]
                try:
                    all_cards.extend(future.result())
                except Exception as exc:
                    logger.warning(
                        "Card type '{}' failed for chunk {} ({})",
                        ct.value, chunk.chunk_index, exc,
                    )
        return all_cards

    def generate_cards_for_chunks(self, chunks: list[TextChunk]) -> list[GeneratedCard]:
        """Generate all cards for all chunks, parallelised across chunks."""
        workers  = self._cfg.card_gen_workers
        all_cards: list[GeneratedCard] = []
        failed = 0

        logger.info(
            "Generating cards for {} chunks ({} worker threads)...",
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
                            "Progress: {} cards, chunk {}",
                            len(all_cards), chunk.chunk_index,
                        )
                except Exception as exc:
                    failed += 1
                    logger.warning(
                        "All cards failed for chunk {} ({}), skipping",
                        chunk.chunk_index, exc,
                    )

        logger.success(
            "Generated {} cards for {} chunks ({} failed)",
            len(all_cards), len(chunks), failed,
        )
        return all_cards

    # -- Internals -------------------------------------------------------------

    # Nullable card types legitimately return bare "null" when the chunk has no
    # relevant content (e.g. formula on a biographical paragraph). Instructor
    # retries 3× before failing on these, adding noise and 3× the LLM calls.
    # Use raw LLM + parsing for nullable types; instructor for the rest.
    _NULLABLE_TYPES = {CardType.DEFINITION, CardType.EXAMPLE,
                       CardType.MISCONCEPTION, CardType.FORMULA}

    def _generate_one_type(
        self, chunk: TextChunk, card_type: CardType
    ) -> list[GeneratedCard]:
        """Make one LLM call for one card type and parse the response."""
        cfg    = _TYPE_CONFIGS[card_type]
        prompt = self._build_prompt(card_type, chunk.text)

        use_instructor = (
            self._instructor_client is not None
            and card_type not in self._NULLABLE_TYPES
        )
        if use_instructor:
            return self._generate_with_instructor(prompt, chunk, card_type, cfg.parser)

        raw = self._call_llm(prompt=prompt, json_mode=cfg.json_mode)
        return self._parse(raw, chunk, card_type, cfg.parser)

    def _generate_with_instructor(
        self, prompt: str, chunk: TextChunk, card_type: CardType, parser: str
    ) -> list[GeneratedCard]:
        """Use instructor for guaranteed schema-valid structured output."""
        from src.core.pipeline_config import get_model

        model = get_model("card_generation")
        messages = [{"role": "user", "content": prompt}]

        try:
            if parser == "qa_pairs":
                result: _QAPairList = self._instructor_client.chat.completions.create(
                    model=model, response_model=_QAPairList, messages=messages, max_retries=2,
                )
                return [
                    GeneratedCard(
                        card_id=str(uuid.uuid4()), chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id, tenant_id=chunk.tenant_id,
                        card_type=CardType.QUESTION.value,
                        title=p.question[:120], content=p.question, answer=p.answer,
                    )
                    for p in result.pairs if p.question.strip() and p.answer.strip()
                ]

            elif parser == "factoids":
                result: _FactoidList = self._instructor_client.chat.completions.create(
                    model=model, response_model=_FactoidList, messages=messages, max_retries=2,
                )
                return [
                    GeneratedCard(
                        card_id=str(uuid.uuid4()), chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id, tenant_id=chunk.tenant_id,
                        card_type=CardType.FACTOID.value,
                        title=f[:120], content=f,
                    )
                    for f in result.factoids if f.strip()
                ]

            else:
                # Nullable single-card types (definition, example, misconception, formula)
                nullable = card_type in (CardType.DEFINITION, CardType.EXAMPLE,
                                         CardType.MISCONCEPTION, CardType.FORMULA)
                schema = _NullableCard if nullable else _SingleCard
                result = self._instructor_client.chat.completions.create(
                    model=model, response_model=schema, messages=messages, max_retries=2,
                )
                content = (result.content or "").strip()
                if not content:
                    return []
                return [GeneratedCard(
                    card_id=str(uuid.uuid4()), chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id, tenant_id=chunk.tenant_id,
                    card_type=card_type.value,
                    title=(result.title or card_type.value.capitalize()).strip(),
                    content=content,
                )]

        except Exception as exc:
            logger.warning("Instructor failed for {} chunk {} ({}), falling back",
                           card_type.value, chunk.chunk_index, exc)
            raw = self._call_llm(prompt=prompt, json_mode=_TYPE_CONFIGS[card_type].json_mode)
            return self._parse(raw, chunk, card_type, parser)

    def _build_prompt(self, card_type: CardType, text: str) -> str:
        template = self._prompts[card_type]
        if card_type == CardType.SUMMARY:
            template = template.format(
                min_tokens=_SUMMARY_MIN_TOKENS,
                max_tokens=_SUMMARY_MAX_TOKENS,
            )
        return f"{template}\n\nTEXT:\n{text.strip()}"

    def _call_llm(self, prompt: str, json_mode: bool) -> str:
        from src.core.llm import call_llm
        system = (
            "Respond ONLY with valid JSON — no markdown fences, no prose."
            if json_mode else
            "You are an expert physics educator. Follow all instructions precisely."
        )
        raw = call_llm(
            prompt=prompt,
            system=system,
            settings=self._cfg,
            json_mode=json_mode,
        )
        if not raw:
            raise RuntimeError("LLM returned empty response")
        return raw

    def _parse(
        self, raw: str, chunk: TextChunk, card_type: CardType, parser: str
    ) -> list[GeneratedCard]:
        if parser == "qa_pairs":
            return ResponseParser.parse_qa_pairs(raw, chunk)
        if parser == "factoids":
            return ResponseParser.parse_factoids(raw, chunk)
        # single_object — handles nullable responses (definition, example, etc.)
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        if cleaned.lower() in ("null", ""):
            return []
        return ResponseParser.parse_single_object(raw, chunk, card_type)


# -- Factory -------------------------------------------------------------------

def get_card_generator(
    settings: Settings | None = None,
) -> StubLLM | OllamaCardGenerator:
    cfg = settings or get_settings()
    if cfg.use_stub_llm:
        return StubLLM()
    return OllamaCardGenerator(settings=cfg)
