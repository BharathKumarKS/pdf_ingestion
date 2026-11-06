"""Synapse — NiceGUI frontend (P1 skeleton + P2 Ask-a-Question).

⚠️ ADDITIONAL frontend, not a replacement. The Streamlit app (`streamlit_app.py`) remains the
primary/supported frontend and is untouched by this module. See
`logs/p1/step10/nicegui_migration_plan.md` and
`.hermes/plans/2026-11-02-p1-nicegui-and-visual-lane-SESSIONS.md`.

P2 scope (plan §6): the **Ask a Question** tab only. Input → ``run.io_bound(run_ask, ...)`` →
a markdown answer + a source table. The retrieval path is BLOCKING (cluster HTTP, 60–90 s per
query), so it must not run on the asyncio event loop — ``run.io_bound`` moves it to a worker
thread. A spinner is shown before the await and cleared after; a timeout and an error banner
replace a silent hang.

⚠️ Deviation from the plan's literal wording, stated rather than hidden: the brief names
``scripts/evaluate_rag.py::run_retrieval`` as the call target, but that is the **eval-harness**
path — it takes ``query_type`` as an INPUT (it never classifies intent), it never calls the
RAPTOR lane, and it always uses ``fetch_k=cfg.reranker_fetch_k``. It therefore cannot reproduce
the Streamlit app's cited pages, which is exactly P2's acceptance criterion. ``run_ask`` below
instead MIRRORS the Streamlit "Ask a Question" path using the same product symbols, the same
prompts and the same search parameters, so the cited pages are comparable by construction. The
backend (`src/pdf_ingestion/*`, `src/core/*`, `scripts/evaluate_rag.py`) is NOT modified.

Run:
    .venv/bin/python src/frontend/nicegui_app.py
Health:
    curl -s http://localhost:8504/healthz
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nicegui import app, run, ui  # noqa: E402

from src.core.config import get_settings  # noqa: E402

PORT = 8504  # 8503 is the Streamlit app; 8501/8502 belong to the other repo

# Student path mirrors the Streamlit default (no auth; single-user mode). See HANDOFF scope note.
DEMO_TENANT = "demo_user"

# The retrieval call is 60–90 s on the cluster (runbook §3). Bound it so a dead cluster shows a
# banner rather than hanging the request forever (the full error-banner UX is P6).
RETRIEVAL_TIMEOUT_S = 300.0

# The fields whose resolved value must match the exported env (plan §5).
ECHO_FIELDS = (
    "qdrant_host",
    "qdrant_collection",
    "dense_model",
    "dense_dim",
    "dense_dim_low",
    "document_prefix",
    "query_instruction",
    "da_enabled",
)

# KaTeX: NiceGUI's `ui.markdown` renders via markdown2 and does NOT typeset maths on its own.
# Pull KaTeX in and auto-render `$...$` / `$$...$$` so the answer's equations render as they do
# in Streamlit. If the CDN is unreachable the page still works — the delimiters just show through.
_KATEX_HEAD = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],throwOnError:false});"></script>
"""


# ── Text hygiene (copied from streamlit_app.py / the skill's text_hygiene template) ──
# Streamlit's markdown renderer does not hide HTML comments and needs KaTeX `$` delimiters, so the
# same conversions are applied at this render boundary. Kept local rather than imported from
# `streamlit_app` — importing that module would execute its module-level `st.*` calls (a side
# effect on the primary frontend, which this workstream must not touch).

def _clean_text(text: str) -> str:
    """Strip parser artefacts ("Formula not decoded", `<!-- ... -->`) before display."""
    import re
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.S)
    text = re.sub(r'(?i)\bformula\s+not\s+decoded\b', ' ', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _latex_delims_to_dollars(text: str) -> str:
    """Convert LaTeX's `\\[...\\]` / `\\(...\\)` into KaTeX's `$$...$$` / `$...$`."""
    import re
    text = re.sub(r'\\\[(.+?)\\\]', lambda m: f'$${m.group(1).strip()}$$', text, flags=re.S)
    text = re.sub(r'\\\((.+?)\\\)', lambda m: f'${m.group(1).strip()}$', text, flags=re.S)
    return text


def _convert_braces_to_math(text: str) -> str:
    """Turn bare `{expr}` / `(expr)` wrappers into inline maths, skipping existing maths spans."""
    import re
    text = re.sub(r'\(([^()]*\\[^()]*)\)', r'$\1$', text)
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == '$':
            if text.startswith('$$', i):
                close = text.find('$$', i + 2)
                end = len(text) if close == -1 else close + 2
            else:
                close = text.find('$', i + 1)
                end = len(text) if close == -1 else close + 1
            out.append(text[i:end])
            i = end
        elif text[i] == '{':
            depth, j = 1, i + 1
            while j < len(text) and depth > 0:
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                j += 1
            inner = text[i + 1:j - 1]
            out.append(f'${inner}$' if any(c in inner for c in ('\\', '^', '_')) else text[i:j])
            i = j
        else:
            out.append(text[i])
            i += 1
    return ''.join(out)


def _render_generated(text: str) -> str:
    """Full pipeline for model-generated prose: clean artefacts, then normalise maths delimiters."""
    return _convert_braces_to_math(_latex_delims_to_dollars(_clean_text(text)))


def _cited_pages(answer: str) -> set[int]:
    """Page numbers the ANSWER actually cites: ``[Page 846]``, ``【Page 846】`` or ``(page 846)``.

    ⚠️ The CJK bracket and the narrow/no-break spaces the model emits (U+202F / U+00A0) are
    matched on purpose — the generator uses all three, and matching only ``[Page`` made the app
    show "Sources retrieved" (all pages) for every answer it could not parse (§I115).
    """
    import re
    return {int(n) for n in re.findall(r'[\[【(]\s*[Pp]age\s*(\d+)', answer or '')}


def _relevance(score: float) -> str:
    """Convert a cosine similarity to a human-readable indicator."""
    if score >= 0.65:
        return "●●●●●  Very relevant"
    if score >= 0.55:
        return "●●●●○  Highly relevant"
    if score >= 0.45:
        return "●●●○○  Relevant"
    if score >= 0.35:
        return "●●○○○  Somewhat relevant"
    return "●○○○○  Loosely related"


def resolved_config() -> dict:
    cfg = get_settings()
    return {k: getattr(cfg, k, None) for k in ECHO_FIELDS}


# ── The retrieval + synthesis path (BLOCKING — call only via run.io_bound) ─────────────────────

def run_ask(query: str, cfg, tenant_id: str = DEMO_TENANT) -> dict:
    """Mirror of the Streamlit "Ask a Question" path (streamlit_app.py:504–687).

    Blocking: embeds, searches the cluster, calls the LLM for HyDE and for synthesis. Returns a
    plain dict so the caller can render it without holding backend objects:

        answer          the synthesised prose ("" if the LLM was unavailable)
        cited_pages     sorted pages the answer cites
        retrieved_pages sorted pages of the retrieved chunks
        chunks          the reranked chunk hits (page/text/score/source_type/title)
        n_raptor        RAPTOR summary candidates used
        n_graph         concept-linked candidates used
        intent          the intent-router label (None if the router is off)
    """
    import numpy as np

    from src.core.llm import call_llm
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    from src.pdf_ingestion.store import DocumentStore

    embedder = get_cluster_embedder(cfg)
    q_vec = embedder.embed_query(query)
    store = DocumentStore(cfg)

    # ── Intent router: classify before search so HyDE + lane gating can use it ──
    intent = None
    also_raptor = True
    also_graph = True
    if cfg.intent_router_enabled:
        from src.core.intent_router import ROUTE_MAP, get_intent_router
        intent = get_intent_router(cfg).classify(q_vec)
        route = ROUTE_MAP[intent]
        also_raptor = route.use_raptor
        also_graph = route.use_graph

    # ── HyDE: hypothetical passage for factual + overview ──
    search_vec = q_vec
    raptor_vec = q_vec
    rerank_query = query
    if cfg.hyde_enabled and intent in ("factual", "overview"):
        try:
            hyp = call_llm(
                prompt=(
                    f"Write 2-3 sentences of physics textbook content "
                    f"that directly answers: {query}"
                ),
                system=(
                    "You are a physics textbook author. Write factual content only. "
                    "No preamble, no 'Here is...', just the content itself."
                ),
                settings=cfg,
            )
            if hyp:
                search_vec = np.array(embedder.embed_query(hyp), dtype=np.float32)
                raptor_vec = search_vec
                # ⚠️ PER-TYPE rerank-query policy (§I97 / T4): the hypothetical is the better CE
                # query for OVERVIEW but a harm for FACTUAL — feed the CE the raw question there.
                rerank_query = hyp if intent == "overview" else query
        except Exception:
            pass  # fall back to the raw query vector

    chunk_results = store.search_with_das(
        query_vector=search_vec,
        query_text=query,
        tenant_id=tenant_id,
        fetch_k=cfg.reranker_fetch_k if cfg.reranker_enabled else cfg.reranker_top_k,
        source_type=None,
    )

    if cfg.reranker_enabled and chunk_results:
        from src.pdf_ingestion.reranker import get_reranker
        chunk_results = get_reranker(cfg).rerank(
            query=rerank_query, chunks=chunk_results, top_k=cfg.reranker_top_k
        )

    raptor_results: list[dict] = []
    if also_raptor:
        try:
            raptor_results = store.search_raptor(
                query_vector=raptor_vec, tenant_id=tenant_id, source_type_filter=None, limit=2
            )
        except Exception:
            raptor_results = []

    graph_results: list[dict] = []
    if also_graph:
        try:
            from src.pdf_ingestion.graph_builder import get_graph_builder
            graph_results = get_graph_builder(cfg).graph_search(
                query_text=query, tenant_id=tenant_id, query_vector=q_vec, limit=3
            )
        except Exception:
            graph_results = []

    # ── Build passages for the LLM context ──
    all_passages: list[str] = []
    for r in chunk_results:
        pg = r.get("page_number")
        all_passages.append(f"[Page {pg}] {r.get('text', '')}" if pg else r.get("text", ""))
    for r in raptor_results:
        all_passages.append(f"[Summary] {r.get('text', '')}")
    for r in graph_results:
        all_passages.append(f"[Concept-linked] {r.get('text_preview', '')}")

    # ── LLM synthesis (same prompt + preamble strip as Streamlit) ──
    synthesis = None
    if all_passages:
        try:
            context = "\n\n".join(all_passages)
            synthesis = call_llm(
                prompt=(
                    f"Question: {query}\n\n"
                    f"Textbook passages:\n{context}\n\n"
                    f"Write a single flowing answer to the question above. "
                    f"Use only the passages provided. "
                    f"Cite page numbers like (page 42) after each claim. "
                    f"If the passages do not contain a direct answer, say so briefly."
                ),
                system=(
                    "You are a physics tutor. Answer in clear prose — "
                    "never as a numbered list, never as Q&A pairs, never invent questions. "
                    "One cohesive answer only. Never fabricate facts. "
                    "Never cite a page number not shown as [Page N] in the passages. "
                    "Use $...$ for inline math and $$...$$ for display equations."
                ),
                settings=cfg,
            )
            if synthesis:
                for prefix in (
                    "I'll follow the instructions to provide an accurate response.",
                    "I will follow the instructions to provide an accurate response.",
                    "Based on the provided passages,",
                    f"Question: {query}",
                    "Student question:",
                ):
                    if synthesis.lstrip().startswith(prefix):
                        synthesis = synthesis.lstrip()[len(prefix):].lstrip(" \n.,")
        except Exception:
            pass  # LLM unavailable — show passages only

    answer = synthesis or ""
    retrieved_pages = sorted({r.get("page_number") for r in chunk_results if r.get("page_number")})
    return {
        "answer": answer,
        "cited_pages": sorted(_cited_pages(answer)),
        "retrieved_pages": retrieved_pages,
        "chunks": chunk_results,
        "n_raptor": len(raptor_results),
        "n_graph": len(graph_results),
        "intent": intent,
    }


# ── HTTP + UI ─────────────────────────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "app": "synapse-nicegui", "phase": "P4-visual-graph"}


def _render_result(container: ui.column, out: dict) -> None:
    """Render one ask result: the answer, its cited pages, and the retrieved-passage table."""
    with container:
        if out.get("intent"):
            ui.label(f"Intent router: {out['intent']}").classes("text-caption")

        if out["answer"]:
            ui.label("💡 Answer").classes("text-subtitle1")
            ui.markdown(_render_generated(out["answer"]))
        else:
            ui.label("No synthesised answer — showing retrieved passages only.").classes(
                "text-caption"
            )

        cited = out["cited_pages"]
        shown = cited or out["retrieved_pages"]
        if shown:
            prefix = "Sources cited" if cited else "Sources retrieved"
            ui.label(f"📄 {prefix}: " + ", ".join(f"p. {p}" for p in shown)).classes("text-caption")

        rows = [
            {
                "n": i,
                "page": r.get("page_number", ""),
                "source": r.get("source_type", "?"),
                "score": round(float(r.get("score", 0.0)), 3),
                "relevance": _relevance(float(r.get("score", 0.0))),
                "preview": _clean_text(r.get("text", ""))[:200],
            }
            for i, r in enumerate(out["chunks"], 1)
        ]
        n_total = len(out["chunks"]) + out["n_raptor"] + out["n_graph"]
        with ui.expansion(f"📄 Source passages ({len(out['chunks'])} chunks"
                          + (f", {out['n_raptor']} summaries" if out["n_raptor"] else "")
                          + (f", {out['n_graph']} concept-linked" if out["n_graph"] else "")
                          + f")  —  {n_total} total", value=False).classes("w-full"):
            ui.table(
                columns=[
                    {"name": "n", "label": "#", "field": "n", "align": "left"},
                    {"name": "page", "label": "Page", "field": "page", "align": "left"},
                    {"name": "source", "label": "Source", "field": "source", "align": "left"},
                    {"name": "score", "label": "Score", "field": "score", "align": "left"},
                    {"name": "relevance", "label": "Relevance", "field": "relevance",
                     "align": "left"},
                    {"name": "preview", "label": "Preview", "field": "preview", "align": "left"},
                ],
                rows=rows,
                row_key="n",
            ).classes("w-full")


def _ask_panel() -> None:
    """The Ask-a-Question tab (plan §6, P2)."""
    ui.label(
        "Ask anything about your course. Synapse searches the textbook to find the most relevant "
        "passages."
    ).classes("text-caption")
    question = ui.input(
        placeholder="e.g. What is Newton's second law and how does it apply to everyday motion?"
    ).props("outlined").classes("w-full").mark("ask-input")
    result = ui.column().classes("w-full")

    async def do_search(_=None) -> None:
        q = (question.value or "").strip()
        if not q:
            ui.notify("Type a question first", type="warning")
            return
        result.clear()
        with result:
            ui.spinner(size="lg")
            ui.label("Finding the best answers… (the retrieval call takes 60–90 s)").classes(
                "text-caption"
            )
        try:
            cfg = get_settings()
            # ⚠️ BLOCKING call → worker thread. Calling run_ask directly here would freeze the
            # event loop (and every other client) for the whole retrieval.
            out = await asyncio.wait_for(run.io_bound(run_ask, q, cfg), timeout=RETRIEVAL_TIMEOUT_S)
        except TimeoutError:
            result.clear()
            with result:
                ui.label(
                    f"⏱️ Timed out after {RETRIEVAL_TIMEOUT_S:.0f} s — the cluster may be down. "
                    "Try again."
                ).classes("text-negative")
            return
        except Exception as exc:
            result.clear()
            with result:
                ui.label(f"Search error: {exc}").classes("text-negative")
            return
        result.clear()
        _render_result(result, out)

    question.on("keydown.enter", do_search)
    ui.button("Search", on_click=do_search).props("color=primary").mark("ask-button")


# ── Read-only data loaders (BLOCKING SQLite reads — call only via run.io_bound) ────────────────

CARDS_PER_TYPE = 8  # max cards rendered per type (keeps the panel light)

CARD_ICONS = {
    "summary": "📋", "definition": "📖", "example": "🔬", "misconception": "⚠️",
    "question": "❓", "objective": "🎯", "formula": "🧮", "factoid": "💡",
}
# Student-facing card types — mirrors streamlit_app.py's _STUDENT_CARD_TYPES.
STUDENT_CARD_TYPES = ["formula", "definition", "question", "misconception", "example"]


def _dedup_cards(cards: list) -> list:
    """Drop duplicates by the first 200 chars of content (mirrors streamlit_app._dedup_cards)."""
    seen: set = set()
    unique = []
    for c in cards:
        key = c.content.strip().lower()[:200]
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique


def load_documents(cfg) -> list[dict]:
    """The document list with the two flags the Cards / RAPTOR tab selectors need."""
    from src.pdf_ingestion.store import DocumentStore
    store = DocumentStore(cfg)
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "source_type": d.source_type,
            "has_cards": bool(store.get_cards(d.id, card_type="summary")
                              or store.get_cards(d.id, card_type="definition")),
            "has_raptor": bool(store.get_raptor_tree(d.id)),
        }
        for d in store.list_documents()
    ]


def load_status(cfg) -> dict:
    """Document-level status — mirrors the SQLite half of the Streamlit Status tab.

    Every count is a direct call on the store (``list_documents`` / ``get_cards`` /
    ``get_raptor_tree`` / ``get_page_images``), so the tab shows what those return.
    """
    from src.pdf_ingestion.store import DocumentStore
    store = DocumentStore(cfg)
    docs = store.list_documents()
    rows = []
    for d in docs:
        rows.append({
            "id": d.id,
            "doc_id": d.id[:8],
            "filename": d.filename,
            "tenant": d.tenant_id,
            "type": d.source_type,
            "pages": d.page_count,
            "chunks": d.chunk_count,
            "cards": len(store.get_cards(d.id)),
            "raptor": len(store.get_raptor_tree(d.id)),
            "visual": len(store.get_page_images(d.id)),
            "embedding": d.embedding_version,
            "colpali": d.colpali_status,
            "created": str(d.created_at)[:19],
        })
    return {
        "n_base": sum(1 for d in docs if d.source_type == "base_textbook"),
        "n_user": sum(1 for d in docs if d.source_type == "user_upload"),
        "total_chunks": sum(d.chunk_count for d in docs),
        "total_cards": sum(r["cards"] for r in rows),
        "total_raptor": sum(r["raptor"] for r in rows),
        "total_visual": sum(r["visual"] for r in rows),
        "rows": rows,
    }


def load_cards(cfg, doc_id: str, card_types: list[str]) -> dict:
    """Per-type card counts + a capped sample, for one document."""
    from src.pdf_ingestion.store import DocumentStore
    store = DocumentStore(cfg)
    by_type: dict[str, dict] = {}
    for ct in card_types:
        cards = _dedup_cards(store.get_cards(doc_id, card_type=ct))
        by_type[ct] = {
            "total": len(cards),
            "shown": [{"title": c.title, "content": c.content} for c in cards[:CARDS_PER_TYPE]],
        }
    return {"by_type": by_type}


def load_raptor(cfg, doc_id: str) -> dict:
    """RAPTOR node counts + the root/L1 summaries, for one document."""
    import json as _json

    from src.pdf_ingestion.store import DocumentStore
    nodes = DocumentStore(cfg).get_raptor_tree(doc_id)

    def _pack(n) -> dict:
        try:
            children = len(_json.loads(n.child_ids_json))
        except Exception:
            children = 0
        return {"level": n.level, "cluster_id": n.cluster_id, "summary": n.summary,
                "children": children, "version": n.version}

    l1 = [n for n in nodes if n.level == 1]
    l2 = [n for n in nodes if n.level == 2]
    l3 = [n for n in nodes if n.level == 3]
    return {
        "n_l1": len(l1), "n_l2": len(l2), "n_l3": len(l3), "total": len(nodes),
        "root": [_pack(n) for n in (l3 or l2)],
        "l1": [_pack(n) for n in l1],
    }


def _metric(label: str, value) -> None:
    with ui.column().classes("items-center"):
        ui.label(str(value)).classes("text-h6")
        ui.label(label).classes("text-caption")


async def _refresh(box: ui.column, loader, render, *args) -> None:
    """Show a spinner, run the (blocking) loader off the loop, then render — or show an error."""
    box.clear()
    with box:
        ui.spinner(size="lg")
    try:
        data = await run.io_bound(loader, *args)
    except Exception as exc:
        box.clear()
        with box:
            ui.label(f"Error: {exc}").classes("text-negative")
        return
    box.clear()
    with box:
        render(data)


def _render_status(data: dict) -> None:
    with ui.row().classes("gap-6"):
        _metric("Base textbooks", data["n_base"])
        _metric("User PDFs", data["n_user"])
        _metric("Total chunks", f"{data['total_chunks']:,}")
        _metric("Cards (Ph.2)", f"{data['total_cards']:,}")
        _metric("RAPTOR nodes", f"{data['total_raptor']:,}")
        _metric("Visual pages", f"{data['total_visual']:,}")
    ui.table(
        columns=[
            {"name": "doc_id", "label": "Doc ID", "field": "doc_id", "align": "left"},
            {"name": "filename", "label": "Filename", "field": "filename", "align": "left"},
            {"name": "tenant", "label": "Tenant", "field": "tenant", "align": "left"},
            {"name": "type", "label": "Type", "field": "type", "align": "left"},
            {"name": "pages", "label": "Pages", "field": "pages", "align": "left"},
            {"name": "chunks", "label": "Chunks", "field": "chunks", "align": "left"},
            {"name": "cards", "label": "Cards", "field": "cards", "align": "left"},
            {"name": "raptor", "label": "RAPTOR", "field": "raptor", "align": "left"},
            {"name": "visual", "label": "Visual", "field": "visual", "align": "left"},
            {"name": "embedding", "label": "Embedding", "field": "embedding", "align": "left"},
            {"name": "colpali", "label": "ColPali", "field": "colpali", "align": "left"},
            {"name": "created", "label": "Created", "field": "created", "align": "left"},
        ],
        rows=data["rows"],
    ).classes("w-full")


def _status_panel() -> None:
    """Status tab (plan §6, P3) — read-only. The Streamlit tab's delete section is omitted:
    a destructive admin action is not part of a read-only phase."""
    ui.label("Corpus / index status (SQLite). Counts are direct store calls.").classes(
        "text-caption"
    )
    box = ui.column().classes("w-full")
    ui.button(
        "Refresh", on_click=lambda: _refresh(box, load_status, _render_status, get_settings())
    )
    ui.timer(0.1, lambda: _refresh(box, load_status, _render_status, get_settings()), once=True)


def _cards_panel() -> None:
    """Cards tab (plan §6, P3) — read-only browse by document and card type."""
    ui.label("Learning cards generated from the course material.").classes("text-caption")
    box = ui.column().classes("w-full")

    async def reload(_=None) -> None:
        box.clear()
        with box:
            ui.spinner(size="lg")
        try:
            docs = await run.io_bound(load_documents, get_settings())
        except Exception as exc:
            box.clear()
            with box:
                ui.label(f"Cards error: {exc}").classes("text-negative")
            return
        docs_with_cards = [d for d in docs if d["has_cards"]]
        box.clear()
        with box:
            if not docs_with_cards:
                ui.label("No study cards yet.").classes("text-caption")
                return
            labels = {d["id"]: d["filename"] for d in docs_with_cards}
            sel = ui.select(
                labels, value=docs_with_cards[0]["id"], label="Material"
            ).classes("w-full")
            types = ui.select(STUDENT_CARD_TYPES, value=list(STUDENT_CARD_TYPES), multiple=True,
                              label="Show me").classes("w-full")
            out = ui.column().classes("w-full")

            async def show(_=None) -> None:
                await _refresh(out, load_cards, _render_cards, get_settings(),
                               sel.value, types.value or [])

            sel.on_value_change(show)
            types.on_value_change(show)
            await show()

    ui.timer(0.1, reload, once=True)


def _render_cards(data: dict) -> None:
    by_type = data["by_type"]
    if not any(v["total"] for v in by_type.values()):
        ui.label("No cards of the selected types.").classes("text-caption")
        return
    for ct, group in by_type.items():
        if not group["total"]:
            continue
        icon = CARD_ICONS.get(ct, "📌")
        with ui.expansion(
            f"{icon} {ct.capitalize()}s  ({group['total']})", value=False
        ).classes("w-full"):
            if group["total"] > CARDS_PER_TYPE:
                ui.label(f"Showing {CARDS_PER_TYPE} of {group['total']} unique cards.").classes(
                    "text-caption"
                )
            for card in group["shown"]:
                with ui.card().classes("w-full"):
                    if card["title"]:
                        ui.label(card["title"]).classes("text-subtitle2")
                    ui.markdown(_render_generated(card["content"]))


def _raptor_panel() -> None:
    """RAPTOR tab (plan §6, P3) — read-only browse of the summary tree."""
    ui.label(
        "Recursive Abstractive Processing for Tree-Organized Retrieval. Chunks → cluster "
        "summaries (L1) → meta-summary (L2)."
    ).classes("text-caption")
    box = ui.column().classes("w-full")

    async def reload(_=None) -> None:
        box.clear()
        with box:
            ui.spinner(size="lg")
        try:
            docs = await run.io_bound(load_documents, get_settings())
        except Exception as exc:
            box.clear()
            with box:
                ui.label(f"RAPTOR error: {exc}").classes("text-negative")
            return
        docs_with_raptor = [d for d in docs if d["has_raptor"]]
        box.clear()
        with box:
            if not docs_with_raptor:
                ui.label("No RAPTOR nodes yet.").classes("text-caption")
                return
            labels = {d["id"]: d["filename"] for d in docs_with_raptor}
            sel = ui.select(
                labels, value=docs_with_raptor[0]["id"], label="Document"
            ).classes("w-full")
            out = ui.column().classes("w-full")
            sel.on_value_change(
                lambda: _refresh(out, load_raptor, _render_raptor, get_settings(), sel.value)
            )
            await _refresh(out, load_raptor, _render_raptor, get_settings(), sel.value)

    ui.timer(0.1, reload, once=True)


def _render_raptor(data: dict) -> None:
    with ui.row().classes("gap-6"):
        _metric("Cluster summaries (L1)", data["n_l1"])
        _metric("Upper summaries (L2+)", data["n_l2"] + data["n_l3"])
        _metric("Total nodes", data["total"])
    if data["root"]:
        ui.label("Root summaries").classes("text-subtitle1")
        for n in data["root"]:
            with ui.card().classes("w-full"):
                ui.markdown(_render_generated(n["summary"]))
                ui.label(
                    f"Level {n['level']} · cluster {n['cluster_id']} · summarises "
                    f"{n['children']} child nodes · v{n['version']}"
                ).classes("text-caption")
    ui.label("Level 1 — Cluster summaries").classes("text-subtitle1")
    for n in data["l1"]:
        with ui.expansion(
            f"Cluster {n['cluster_id']}  ({n['children']} source chunks)", value=False
        ).classes("w-full"):
            ui.markdown(_render_generated(n["summary"]))


# ── NG-P4: Visual + Graph loaders (BLOCKING — call only via run.io_bound) ──────────────────────

# The same Cypher `logs/p1/step10/verify_graph.py` counts with (an independent, pre-existing
# read-only counter), so the tab's stats are comparable to a recorded oracle.
GRAPH_STATS_CYPHER = {
    "documents": "MATCH (n:Document) RETURN count(n) AS c",
    "chunks": "MATCH (n:Chunk) RETURN count(n) AS c",
    "pages": "MATCH (n:Page) RETURN count(n) AS c",
    "concepts": "MATCH (n:Concept) RETURN count(n) AS c",
    "edges": "MATCH ()-[r]->() RETURN count(r) AS c",
}


def load_visual(cfg, query_text: str, n_results: int = 3) -> dict:
    """Text-query ColPali search + the matching page images resolved to bytes.

    An empty query returns just the index size (the panel's landing state). ``score_threshold=0.0``
    keeps every page — the text-query scale differs from the image threshold (streamlit_app's own
    note), so filtering here would drop everything.
    """
    from src.pdf_ingestion.colpali_embedder import get_colpali_embedder
    from src.pdf_ingestion.image_store import get_image_store
    from src.pdf_ingestion.store import DocumentStore

    store = DocumentStore(cfg)
    n_vectors = store.count_visual_vectors([DEMO_TENANT, cfg.global_tenant_id])
    if not query_text.strip():
        return {"n_vectors": n_vectors, "results": []}

    patches = get_colpali_embedder(cfg).embed_query_text(query_text)
    hits = store.visual_search(
        query_patches=patches, tenant_id=DEMO_TENANT, limit=int(n_results), score_threshold=0.0
    )
    image_store = get_image_store(cfg)
    results = []
    for h in hits:
        key = h.get("image_key")
        entry = {"page_number": h.get("page_number"), "score_cosine": h.get("score_cosine"),
                 "document_id": h.get("document_id"), "image_key": key, "png": None, "error": None}
        try:
            entry["png"] = image_store.get(key) if key else None
            if entry["png"] is None:
                entry["error"] = "no image_key on the point"
        except Exception as exc:
            entry["error"] = str(exc)
        results.append(entry)
    return {"n_vectors": n_vectors, "results": results}


def load_graph_stats(cfg) -> dict:
    """Node/edge counts read straight from Memgraph with the builder's own connection settings."""
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=(cfg.memgraph_user, cfg.memgraph_password),
    )
    try:
        out: dict[str, int] = {}
        with driver.session() as session:
            for name, cypher in GRAPH_STATS_CYPHER.items():
                rec = session.run(cypher).single()
                out[name] = int(rec["c"]) if rec else 0
        return out
    finally:
        driver.close()


def load_graph_search(cfg, query_text: str, limit: int = 6) -> dict:
    """Concept-graph search through `get_graph_builder(cfg)` — the same lane Streamlit uses."""
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    from src.pdf_ingestion.graph_builder import get_graph_builder

    q_vec = get_cluster_embedder(cfg).embed_query(query_text)
    hits = get_graph_builder(cfg).graph_search(
        query_text=query_text, tenant_id=DEMO_TENANT, query_vector=q_vec, limit=limit
    )
    return {"n_results": len(hits), "results": [
        {"chunk_id": h.get("chunk_id"),
         "page_number": (h.get("page_num") if h.get("page_num") is not None
                         else h.get("page_number")),
         "text_preview": h.get("text_preview", ""),
         "concept_path": list(h.get("concept_path", [])),
         "matched_concepts": h.get("matched_concepts", len(h.get("concept_path", [])))}
        for h in hits
    ]}


def _render_visual(data: dict) -> None:
    ui.label(f"{data['n_vectors']:,} visual vectors indexed (ColPali)").classes("text-caption")
    if not data["results"]:
        ui.label("Describe a figure to search the pages.").classes("text-caption")
        return
    with ui.row().classes("w-full items-start"):
        for r in data["results"]:
            with ui.card().classes("w-72"):
                if r["png"]:
                    import io

                    from PIL import Image
                    try:
                        ui.image(Image.open(io.BytesIO(r["png"]))).classes("w-full")
                    except Exception as exc:  # pragma: no cover - render-time guard
                        ui.label(f"⚠️ could not decode page image: {exc}").classes("text-negative")
                else:
                    ui.label(f"⚠️ page image unavailable: {r['error']}").classes("text-negative")
                ui.label(f"Page {r['page_number']}  ·  cosine {r['score_cosine']}").classes(
                    "text-caption"
                )


def _render_graph_stats(stats: dict) -> None:
    with ui.row().classes("gap-6"):
        _metric("Documents", stats.get("documents", 0))
        _metric("Chunks", f"{stats.get('chunks', 0):,}")
        _metric("Pages", f"{stats.get('pages', 0):,}")
        _metric("Concepts", f"{stats.get('concepts', 0):,}")
        _metric("Edges", f"{stats.get('edges', 0):,}")


def _render_graph_search(data: dict) -> None:
    if not data["n_results"]:
        ui.label("No concept-graph results.").classes("text-caption")
        return
    ui.label(f"Found {data['n_results']} concept-connected passage(s)").classes("text-subtitle2")
    for r in data["results"]:
        with ui.card().classes("w-full"):
            concepts = ", ".join(r["concept_path"])
            ui.label(f"🔗 {r['matched_concepts']} concept(s) matched: {concepts}").classes(
                "text-caption"
            )
            ui.markdown(_render_generated(r["text_preview"])[:1500])
            ui.label(f"chunk_id: {r['chunk_id']}").classes("text-caption")


def _visual_panel() -> None:
    """Visual tab (plan §6, P4) — text-query ColPali search; page images render in cards."""
    ui.label(
        "Describe a figure and Synapse finds the matching pages (ColPali late interaction)."
    ).classes(
        "text-caption"
    )
    with ui.row().classes("w-full items-end"):
        query = ui.input(placeholder="e.g. the diagram of a pendulum").props("outlined").classes(
            "grow"
        ).mark("visual-input")
        n_results = ui.number("Pages", value=3, min=1, max=5).classes("w-24")
    box = ui.column().classes("w-full")

    async def run(_=None) -> None:
        q = (query.value or "").strip()
        if not q:
            ui.notify("Describe a figure first", type="warning")
            return
        await _refresh(box, load_visual, _render_visual, get_settings(), q,
                       int(n_results.value or 3))

    query.on("keydown.enter", run)
    ui.button("Find the page", on_click=run).props("color=primary").mark("visual-button")
    ui.timer(0.1, lambda: _refresh(box, load_visual, _render_visual, get_settings(), "", 0),
             once=True)


def _graph_panel() -> None:
    """Graph tab (plan §6, P4) — live Memgraph counts + a single-hop concept search."""
    ui.label(
        "Concept graph search: finds passages that mention the concepts your question matches. "
        "Requires Memgraph (`docker compose --profile phase3 up`)."
    ).classes("text-caption")
    stats_box = ui.column().classes("w-full")
    ui.timer(
        0.1, lambda: _refresh(stats_box, load_graph_stats, _render_graph_stats, get_settings()),
        once=True,
    )
    ui.separator()
    with ui.row().classes("w-full items-end"):
        query = ui.input(placeholder="e.g. Why does a satellite stay in orbit?").props(
            "outlined"
        ).classes("grow").mark("graph-input")
    out = ui.column().classes("w-full")

    async def run(_=None) -> None:
        q = (query.value or "").strip()
        if not q:
            ui.notify("Ask a concept question first", type="warning")
            return
        await _refresh(out, load_graph_search, _render_graph_search, get_settings(), q)

    query.on("keydown.enter", run)
    ui.button("Graph Search", on_click=run).props("color=primary").mark("graph-button")


@ui.page("/")
def index() -> None:
    ui.add_head_html(_KATEX_HEAD)
    ui.label("Synapse — NiceGUI frontend").classes("text-h5")
    ui.label(
        "P3 — Ask a Question + read-only Status / Cards / RAPTOR. Streamlit remains primary."
    ).classes(
        "text-caption"
    )

    with ui.tabs().classes("w-full") as tabs:
        ask_tab = ui.tab("🔍 Ask a Question")
        status_tab = ui.tab("📊 Status")
        cards_tab = ui.tab("🃏 Cards")
        raptor_tab = ui.tab("🌲 RAPTOR")
        visual_tab = ui.tab("🖼️ Visual")
        graph_tab = ui.tab("🕸️ Graph")
    with ui.tab_panels(tabs, value=ask_tab).classes("w-full"):
        with ui.tab_panel(ask_tab):
            _ask_panel()
        with ui.tab_panel(status_tab):
            _status_panel()
        with ui.tab_panel(cards_tab):
            _cards_panel()
        with ui.tab_panel(raptor_tab):
            _raptor_panel()
        with ui.tab_panel(visual_tab):
            _visual_panel()
        with ui.tab_panel(graph_tab):
            _graph_panel()

    with ui.card().classes("w-full"):
        ui.label("Resolved config (must match the exported env)").classes("text-subtitle1")
        for k, v in resolved_config().items():
            ui.label(f"{k} = {v!r}")
    ui.label(f"health: http://localhost:{PORT}/healthz").classes("text-caption")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        host="0.0.0.0",
        port=PORT,
        title="Synapse (NiceGUI)",
        storage_secret="synapse-demo-secret",
        reload=False,
        show=False,
    )
