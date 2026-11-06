"""The conscience — response-side guardrails (Week 6, Act II).

**C2 — the tier-1 cheap heuristics** (cost ≈ 0, latency microseconds): format and lexical checks that
need no model. The lesson plan's escalation ladder, Tier 1: "cheap heuristics do not prove
groundedness; they cheaply DISPROVE it in the easy cases, so the model tiers never see them."

Two checks, both pure stdlib:
  * **citation validity** — does every page the answer cites actually appear in the retrieved set?
    A citation to a page that was never retrieved is the "footnote that does not hold".
  * **numbers in evidence** — does every number in the answer appear *somewhere* in the evidence?
    "A number that appears in no passage is a near-certain fabrication, catchable by string search."

⚠️ These are **disprovers**, not verifiers. A passing answer is not proven grounded — only an
answer that fails is proven suspect. C1/C3 (NLI + judge) are the tiers that actually verify.
"""
from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

# A page citation in ANY form the generator actually emits — `[Page 141]`, the CJK bracket
# `【Page 141】`, or `(page 141)` — with ANY whitespace between the word and the number. This is
# the §I115 fix: the model emits U+202F / U+00A0, which a literal ASCII space does not match.
_CITATION_RE = re.compile(r"[\[【(]\s*[Pp]age\s*(\d+)\s*[\]】)]")

# A number: digits with optional thousands separators and a decimal part.
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def cited_pages(answer: str) -> set[int]:
    """The page numbers an answer cites, in any of the emitted formats."""
    return {int(m) for m in _CITATION_RE.findall(answer or "")}


@dataclass
class CitationValidity:
    cited: set[int] = field(default_factory=set)
    valid: set[int] = field(default_factory=set)
    invalid: set[int] = field(default_factory=set)

    @property
    def all_valid(self) -> bool:
        """True when every cited page was retrieved (vacuously true when nothing is cited)."""
        return not self.invalid


def check_citation_validity(answer: str, retrieved_pages) -> CitationValidity:
    """C2 — every cited page must be in the retrieved set (the citation-validity check)."""
    retrieved = {int(p) for p in (retrieved_pages or [])}
    cited = cited_pages(answer)
    return CitationValidity(cited=cited, valid=cited & retrieved, invalid=cited - retrieved)


@dataclass
class NumberCheck:
    numbers: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def all_supported(self) -> bool:
        return not self.unsupported


def _normalised_numbers(text: str) -> list[str]:
    """Number tokens with thousands separators removed, in order, de-duplicated."""
    seen: list[str] = []
    for m in _NUMBER_RE.finditer(text or ""):
        n = m.group(0).replace(",", "")
        if n not in seen:
            seen.append(n)
    return seen


def check_numbers_in_evidence(answer: str, evidence_texts) -> NumberCheck:
    """C2 — every number in the answer must appear in the evidence (a fabrication disprover).

    The evidence is normalised (thousands separators removed) and each answer number is matched at
    a token boundary, so ``42`` is not "found" inside ``1042``. A number absent from every passage
    is a near-certain fabrication.
    """
    evidence_norm = " ".join(evidence_texts or []).replace(",", "")
    numbers = _normalised_numbers(answer)
    unsupported = [
        n for n in numbers
        if not re.search(rf"(?<![\d.]){re.escape(n)}(?![\d.])", evidence_norm)
    ]
    return NumberCheck(numbers=numbers, unsupported=unsupported)


# ══════════════════════════════════════════════════════════════════════════════
# C1 — the assertion–evidence BIPARTITE GRAPH (Week 6, Act II, Lab 7)
#
# Ported VERBATIM from `Labs/Week_6/response_grounding/src/response_grounding/*.py`:
#   claim_extractor · claim_document_matrix_builder · semantic_similarity_filter ·
#   nli_entailment_checker · groundedness_evaluator
# The only adaptations are (a) the LLM client: the lab's `instructor`+`OpenAI` is replaced by this
# repo's `call_llm` (json_mode) with the SAME Pydantic `ClaimExtraction` schema and the same
# sentence-split fallback, and (b) the two model stages take an INJECTABLE encoder/checker so the
# offline stub can stand in — the repo's `USE_STUB_*` convention (the lab loads the model in the
# constructor; here the factories decide).
#
# The graph: left nodes are CLAIMS (atomic assertions extracted from the answer), right nodes are
# EVIDENCE (the retrieved passages). Edges are scored twice — a cheap MiniLM cosine pre-filter
# (τ 0.5), then an expensive NLI cross-encoder (τ 0.55). A claim that keeps NO edge is an
# **isolated left node** — the graph's picture of a hallucination: an assertion nothing supports.
# ══════════════════════════════════════════════════════════════════════════════

_DEFAULT_SIMILARITY_MODEL = "all-MiniLM-L6-v2"
_DEFAULT_NLI_MODEL = "cross-encoder/nli-deberta-v3-base"

_CLAIM_EXTRACTOR_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "claim_extractor_system_prompt.md"
)


@lru_cache(maxsize=1)
def claim_extractor_system_prompt() -> str:
    """The COSTAR claim-extraction system prompt (copied from the lab's `prompts/`)."""
    return _CLAIM_EXTRACTOR_PROMPT_PATH.read_text(encoding="utf-8").strip()


class ClaimExtraction(BaseModel):
    """Structured claim list returned by the extraction LLM (the lab's schema)."""

    claims: list[str] = Field(
        default_factory=list,
        description="Ordered factual, verifiable claims from the input; one string per claim.",
    )


def _parse_claim_json(raw: str) -> list[str] | None:
    """Parse the extractor reply into claims: a JSON object ``{"claims": [...]}`` or a bare array.

    Returns None when nothing parses, so the caller falls back to sentence splitting rather than
    scoring an empty answer as grounded.
    """
    if not raw:
        return None
    text = raw.strip()
    # Strip a ```json fence if the model added one.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    for candidate in (text, text[text.find("{") : text.rfind("}") + 1],
                      text[text.find("[") : text.rfind("]") + 1]):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:  # noqa: BLE001 — try the next shape
            continue
        if isinstance(parsed, dict):
            parsed = parsed.get("claims")
        if isinstance(parsed, list):
            claims = [str(c).strip() for c in parsed if str(c).strip()]
            if claims:
                return claims
    return None


class ClaimExtractor:
    """Extracts discrete factual claims from response text using the configured LLM.

    Uses this repo's :func:`src.core.llm.call_llm` in JSON mode with the lab's
    ``ClaimExtraction`` schema. If structured extraction yields nothing, falls back to
    sentence-boundary splitting (the lab's fallback, verbatim).
    """

    def __init__(self, cfg=None) -> None:
        self._cfg = cfg

    def extract(self, response_text: str) -> list[str]:
        """Extract individual claims from the full response text, in order of appearance."""
        if not response_text or not response_text.strip():
            return []

        from src.core.llm import call_llm

        try:
            raw = call_llm(
                prompt=response_text,
                system=claim_extractor_system_prompt(),
                settings=self._cfg,
                timeout=60,
                json_mode=True,
            )
            claims = _parse_claim_json(raw)
            if claims:
                return claims
        except Exception:  # noqa: BLE001 — any extraction failure falls back, as in the lab
            pass

        return self._fallback_sentence_split(response_text)

    @staticmethod
    def _fallback_sentence_split(response_text: str) -> list[str]:
        """Fallback extractor based on sentence boundaries (verbatim from the lab)."""
        raw_claims = re.split(r"[.!?]\s+|\n+", response_text.strip())
        return [claim.strip() for claim in raw_claims if claim and claim.strip()]


class ClaimDocumentMatrixBuilder:
    """The Cartesian product of claims and evidence documents (verbatim from the lab).

    Each matrix element is one (claim, document) edge to be scored by the later
    similarity and entailment stages.
    """

    def build(self, claims: list[str], documents: list[str]) -> list[dict]:
        """Build the claim–document matrix. Each edge has ``claim_index``, ``document_index``,
        ``claim`` and ``document``."""
        matrix: list[dict] = []
        for claim_index, claim in enumerate(claims):
            for document_index, document in enumerate(documents):
                matrix.append({
                    "claim_index": claim_index,
                    "document_index": document_index,
                    "claim": claim,
                    "document": document,
                })
        return matrix


# ── The offline stand-ins (USE_STUB_NLI) ─────────────────────────────────────
# Deterministic and dependency-free: the encoder is a fixed-width hashed bag-of-words so that
# cosine similarity is a lexical-overlap proxy (a real model is semantic; this is NOT), and the
# NLI stand-in scores entailment as the fraction of the claim's tokens present in the document.
# They exist so the fast suite tests the GRAPH's wiring offline — never for a measured number.

_STUB_EMBED_DIM = 512


def _stub_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower())


class _StubEncoder:
    """Offline stand-in for a ``SentenceTransformer`` (``.encode`` returns normalised rows)."""

    def encode(self, texts, normalize_embeddings: bool = True, show_progress_bar: bool = False):
        import numpy as np

        rows = []
        for text in texts:
            vec = np.zeros(_STUB_EMBED_DIM, dtype=np.float64)
            for tok in _stub_tokens(text):
                vec[zlib.crc32(tok.encode("utf-8")) % _STUB_EMBED_DIM] += 1.0
            rows.append(vec)
        mat = np.vstack(rows) if rows else np.zeros((0, _STUB_EMBED_DIM))
        if normalize_embeddings and len(mat):
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            mat = mat / norms
        return mat


class _StubNLIConfig:
    """The stub cross-encoder's head labels — the REAL DeBERTa NLI class order.

    ⚠️ ``cross-encoder/nli-deberta-v3-base`` maps ``{0: contradiction, 1: entailment, 2: neutral}``
    (verified live 2026-11-05), NOT the more intuitive alphabetical/contradiction-neutral-entailment
    order. The stub mirrors it so a test cannot pass on a class order the real model does not have.
    """

    id2label = {0: "contradiction", 1: "entailment", 2: "neutral"}


class _StubNLIInner:
    """Stands in for ``CrossEncoder.model`` so ``_resolve_entailment_class_index`` reads a config."""

    config = _StubNLIConfig()


class _StubCrossEncoder:
    """Offline stand-in for a ``CrossEncoder`` NLI model.

    ``.predict(pairs)`` returns a ``(n, 3)`` softmax-shaped array in the DeBERTa class order
    ``[contradiction, entailment, neutral]``; the entailment column is the fraction of the claim's
    tokens that appear in the document. Carries ``.model.config.id2label`` so the lab's verbatim
    :func:`_resolve_entailment_class_index` resolves to the entailment column.
    """

    def __init__(self) -> None:
        self.model = _StubNLIInner()

    def predict(self, pairs, show_progress_bar: bool = False,
                convert_to_numpy: bool = True, apply_softmax: bool = True):
        import numpy as np

        out = []
        for document, claim in pairs:
            claim_toks = set(_stub_tokens(claim))
            doc_toks = set(_stub_tokens(document))
            p_entail = (len(claim_toks & doc_toks) / len(claim_toks)) if claim_toks else 0.0
            rest = (1.0 - p_entail) / 2.0
            out.append([rest, p_entail, rest])  # [contradiction, entailment, neutral]
        return np.asarray(out, dtype=np.float64) if out else np.zeros((0, 3))


class SemanticSimilarityFilter:
    """First-level filter: drop claim–document pairs below a cosine similarity cutoff.

    Similarity is the cosine of sentence-transformer embeddings of the claim and document text.
    Pairs strictly above ``similarity_threshold`` are kept and annotated with a
    ``semantic_similarity`` field. Ported from the lab; the encoder is injectable.
    """

    def __init__(self, similarity_threshold: float = 0.5, model_name: str | None = None,
                 encoder=None) -> None:
        self.similarity_threshold = similarity_threshold
        if encoder is not None:
            self._model = encoder
        else:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name or _DEFAULT_SIMILARITY_MODEL)

    def filter_pairs(self, matrix: list[dict]) -> list[dict]:
        """Keep edges whose claim–document cosine similarity exceeds the threshold."""
        if not matrix:
            return []

        import numpy as np

        claims = [str(edge["claim"]) for edge in matrix]
        documents = [str(edge["document"]) for edge in matrix]
        claim_emb = self._model.encode(claims, normalize_embeddings=True, show_progress_bar=False)
        doc_emb = self._model.encode(documents, normalize_embeddings=True, show_progress_bar=False)
        similarities = np.sum(np.asarray(claim_emb) * np.asarray(doc_emb), axis=1)

        kept: list[dict] = []
        for edge, sim in zip(matrix, similarities, strict=True):
            score = float(sim)
            if score > self.similarity_threshold:
                enriched = dict(edge)
                enriched["semantic_similarity"] = score
                kept.append(enriched)
        return kept


class NLIEntailmentChecker:
    """Scores claim–document pairs with a cross-encoder NLI model.

    Premise is the document, hypothesis the claim; ``entailment_probability`` is the softmax
    probability of the entailment class. Ported from the lab; the model is injectable.
    """

    def __init__(self, entailment_threshold: float = 0.55, model_name: str | None = None,
                 model=None) -> None:
        self.entailment_threshold = entailment_threshold
        if model is not None:
            self._model = model
        else:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(model_name or _DEFAULT_NLI_MODEL)
        self._entailment_idx = _resolve_entailment_class_index(self._model)

    def score_edges(self, candidate_edges: list[dict]) -> list[dict]:
        """Score each candidate edge with ``entailment_probability`` and ``is_entailing``."""
        if not candidate_edges:
            return []

        import numpy as np

        pairs = [(str(edge["document"]), str(edge["claim"])) for edge in candidate_edges]
        probs = np.asarray(
            self._model.predict(pairs, show_progress_bar=False,
                                convert_to_numpy=True, apply_softmax=True),
            dtype=np.float64,
        )
        if probs.ndim == 1:
            probs = probs.reshape(1, -1)
        if probs.shape[1] == 1:
            probabilities = probs[:, 0].astype(float)
        else:
            probabilities = probs[:, self._entailment_idx].astype(float)

        scored: list[dict] = []
        for edge, probability in zip(candidate_edges, probabilities, strict=True):
            prob = float(probability)
            enriched = dict(edge)
            enriched["entailment_probability"] = prob
            enriched["is_entailing"] = prob >= self.entailment_threshold
            scored.append(enriched)
        return scored


def _resolve_entailment_class_index(model) -> int:
    """The index of the model's ``entailment`` head (verbatim from the lab)."""
    cfg = model.model.config
    id2label = getattr(cfg, "id2label", None)
    if not id2label:
        return 1
    for key, label in id2label.items():
        idx = int(key) if not isinstance(key, int) else key
        if str(label).lower() == "entailment":
            return idx
    return 1


class GroundednessEvaluator:
    """Runs the groundedness pipeline for a set of claims against documents.

    Composes matrix construction, semantic filtering, and entailment scoring. A claim is grounded
    if at least one retained edge is entailing; the groundedness score is the fraction of grounded
    claims. An ISOLATED left node (a claim with no retained edge) is the graph's hallucination
    signature. Ported from the lab.
    """

    def __init__(self, matrix_builder: ClaimDocumentMatrixBuilder,
                 semantic_filter: SemanticSimilarityFilter,
                 nli_checker: NLIEntailmentChecker) -> None:
        self.matrix_builder = matrix_builder
        self.semantic_filter = semantic_filter
        self.nli_checker = nli_checker

    def evaluate(self, claims: list[str], documents: list[str]) -> dict:
        """Evaluate all claims against the evidence documents.

        Returns ``claim_results`` (per-claim ``is_grounded``, ``best_entailment_probability``,
        ``best_edge``, and ``is_isolated``), ``groundedness_score``, ``scored_edges``, and
        ``isolated_claims`` (the hallucination signature).
        """
        if not claims:
            return {"claim_results": [], "groundedness_score": 1.0,
                    "scored_edges": [], "isolated_claims": []}

        matrix = self.matrix_builder.build(claims, documents)
        semantic_candidates = self.semantic_filter.filter_pairs(matrix)
        scored_edges = self.nli_checker.score_edges(semantic_candidates)

        claim_results: list[dict] = []
        grounded_count = 0
        isolated_claims: list[str] = []

        for claim_index, claim in enumerate(claims):
            related = [e for e in scored_edges if e["claim_index"] == claim_index]
            if related:
                best_edge = max(related, key=lambda x: float(x["entailment_probability"]))
                best_probability = float(best_edge["entailment_probability"])
                is_grounded = bool(best_edge["is_entailing"])
                if is_grounded:
                    grounded_count += 1
            else:
                best_edge = None
                best_probability = 0.0
                is_grounded = False

            is_isolated = not is_grounded
            if is_isolated:
                isolated_claims.append(claim)
            claim_results.append({
                "claim_index": claim_index,
                "claim": claim,
                "is_grounded": is_grounded,
                "is_isolated": is_isolated,
                "best_entailment_probability": best_probability,
                "best_edge": best_edge,
            })

        return {
            "claim_results": claim_results,
            "groundedness_score": grounded_count / len(claims),
            "scored_edges": scored_edges,
            "isolated_claims": isolated_claims,
        }


# ── C1 factories — the config decides the model or the offline stand-in ──────

def get_semantic_filter(cfg) -> SemanticSimilarityFilter:
    """Build the C1 pre-filter from config (stub encoder under ``use_stub_nli``)."""
    encoder = _StubEncoder() if cfg.use_stub_nli else None
    return SemanticSimilarityFilter(
        similarity_threshold=cfg.guard_similarity_threshold,
        model_name=cfg.guard_similarity_model,
        encoder=encoder,
    )


def get_nli_checker(cfg) -> NLIEntailmentChecker:
    """Build the C1 NLI checker from config (stub cross-encoder under ``use_stub_nli``)."""
    model = _StubCrossEncoder() if cfg.use_stub_nli else None
    return NLIEntailmentChecker(
        entailment_threshold=cfg.guard_nli_threshold,
        model_name=cfg.guard_nli_model,
        model=model,
    )


def get_groundedness_evaluator(cfg) -> GroundednessEvaluator:
    """The wired C1 graph: matrix builder + similarity filter + NLI checker."""
    return GroundednessEvaluator(
        ClaimDocumentMatrixBuilder(), get_semantic_filter(cfg), get_nli_checker(cfg)
    )


def evaluate_groundedness(answer: str, evidence_texts, cfg, extractor=None) -> dict:
    """The C1 entry point: extract the answer's claims, then ground them against the evidence.

    ``evidence_texts`` is an iterable of passage strings (already the retrieved set). Claims and
    evidence are capped by ``guard_max_claims`` / ``guard_max_evidence`` — the cost is
    O(claims × evidence) NLI reads, so the cap is the budget knob.
    """
    claims = (extractor or ClaimExtractor(cfg)).extract(answer)
    claims = [c for c in claims if c.strip()][: cfg.guard_max_claims]
    documents = [str(d) for d in (evidence_texts or []) if str(d).strip()][: cfg.guard_max_evidence]
    return get_groundedness_evaluator(cfg).evaluate(claims, documents)


# ══════════════════════════════════════════════════════════════════════════════
# C4 — CITATION FAITHFULNESS (ALCE)
#
# The lab's grounding graph is re-read at the CITATION level: for every statement in the answer,
# its cited pages are the evidence; the same NLI checker decides whether each cited page ENTAILS
# the statement. Two numbers, both the ALCE definitions (Gao et al., 2023):
#   * **citation recall**  = fraction of statements (all statements, cited or not) that at least
#     one cited page entails — an uncited statement scores 0, because nothing supports it;
#   * **citation precision** = fraction of CITATIONS (statement, page) pairs that entail — a
#     citation to a page that does not support its statement is the "footnote that does not hold".
# ⚠️ Both return **None** when the answer cites nothing: "no citations" and "every citation
# faithful" are different facts (the §I115 lesson — a vacuous 1.000 is worse than an em-dash).
# ══════════════════════════════════════════════════════════════════════════════

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def answer_statements(answer: str) -> list[str]:
    """Split an answer into non-empty statements (sentences) for the ALCE denominators."""
    return [s.strip() for s in _SENTENCE_SPLIT.split((answer or "").strip()) if s.strip()]


@dataclass
class CitationFaithfulness:
    citation_recall: float | None
    citation_precision: float | None
    n_statements: int
    n_citations: int


def compute_citation_faithfulness(answer: str, evidence_by_page, nli_checker) -> CitationFaithfulness:
    """C4 — ALCE citation recall and precision, read from the same NLI graph.

    ``evidence_by_page`` maps a page number to that page's evidence text (str). Statements with
    no cited page — or whose cited page has no evidence text — contribute 0 to recall; a citation
    to a page outside the evidence map is counted in the precision denominator as unfaithful
    (it cannot entail). Both metrics are None when the answer cites nothing at all.
    """
    statements = answer_statements(answer)
    pairs: list[tuple[int, int]] = []  # (statement_index, page)
    for i, stmt in enumerate(statements):
        for page in cited_pages(stmt):
            pairs.append((i, page))

    if not pairs:
        return CitationFaithfulness(None, None, len(statements), 0)

    evidence = {int(p): str(t) for p, t in (evidence_by_page or {}).items()}
    scorable = [(si, p) for si, p in pairs if p in evidence and evidence[p].strip()]
    scorable_set = set(scorable)

    # The NLI premise/hypothesis is the ASSERTION, not its citation markers: strip `[Page N]`
    # from the statement text so the entailment read is about content (ALCE scores the statement).
    def _assertion(text: str) -> str:
        return _CITATION_RE.sub(" ", text).strip()

    entailing: set[tuple[int, int]] = set()
    if scorable:
        edges = [{"claim_index": si, "document_index": p,
                  "claim": _assertion(statements[si]), "document": evidence[p]}
                 for si, p in scorable]
        for edge in nli_checker.score_edges(edges):
            if edge["is_entailing"]:
                entailing.add((edge["claim_index"], edge["document_index"]))

    # Recall — over ALL statements; a statement is covered if ≥1 of ITS citations entails it.
    covered = {si for si, p in entailing}
    recall = len(covered) / len(statements) if statements else None
    # Precision — over ALL citations; a citation outside the evidence map cannot entail.
    precision = len(entailing) / len(pairs)
    assert scorable_set <= set(pairs)
    return CitationFaithfulness(
        citation_recall=round(recall, 4) if recall is not None else None,
        citation_precision=round(precision, 4),
        n_statements=len(statements),
        n_citations=len(pairs),
    )


def evidence_by_page(chunks) -> dict[int, str]:
    """Build the page → evidence-text map C4 needs from retrieved chunks (page_number + text)."""
    pages: dict[int, list[str]] = {}
    for chunk in chunks or []:
        page = chunk.get("page_number")
        text = chunk.get("text")
        if page is None or not text:
            continue
        pages.setdefault(int(page), []).append(str(text))
    return {p: "\n".join(texts) for p, texts in pages.items()}
