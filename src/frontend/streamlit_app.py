"""Streamlit frontend — Phase 1 + Phase 2 + Phase 3.

URL param ?admin=true unlocks the Teacher/Admin view.
Default (no param) shows the Student view.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from src.core.config import get_settings
from src.pdf_ingestion.store import (
    DocumentStore,
    generate_phase2_artifacts,
    generate_phase3_artifacts,
    ingest_pdf,
)

# ── Page config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Synapse Learning",
    page_icon="🧠",
    layout="wide",
)

cfg = get_settings()
cfg.ensure_dirs()

# ── Role detection via URL param ──────────────────────────────────────────
is_admin = st.query_params.get("admin", "false").lower() == "true"

# ── Helpers ───────────────────────────────────────────────────────────────

CARD_ICONS = {
    "summary":       "📋",
    "definition":    "📖",
    "example":       "🔬",
    "misconception": "⚠️",
    "question":      "❓",
    "objective":     "🎯",
    "formula":       "🧮",
}

def _relevance(score: float) -> str:
    """Convert cosine similarity to a human-readable indicator."""
    if score >= 0.65:  return "●●●●●  Very relevant"
    if score >= 0.55:  return "●●●●○  Highly relevant"
    if score >= 0.45:  return "●●●○○  Relevant"
    if score >= 0.35:  return "●●○○○  Somewhat relevant"
    return              "●○○○○  Loosely related"

def _source_label(r: dict) -> str:
    """Human-readable provenance for a search result."""
    title = r.get("title") or "Knowledge base"
    page  = r.get("page_number")
    page_str = f" · page {page}" if page else ""
    return f"*{title}*{page_str}"

def _colpali_status_badge(status: str) -> str:
    return {
        "ready":      "✅ Visual ready",
        "processing": "⏳ Visual processing…",
        "failed":     "❌ Visual failed",
        "pending":    "🕐 Visual pending",
    }.get(status, status)


# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧠 Synapse Learning")
    st.caption("Adaptive learning platform")
    st.divider()

    if is_admin:
        st.caption("🔧 **Admin mode** — [exit admin](/?)")

    st.subheader("Your Profile")
    tenant_id = st.text_input("User ID", value="demo_user")

    # ── Source toggle ─────────────────────────────────────────────────────
    st.subheader("Study mode")
    try:
        store      = DocumentStore(cfg)
        user_docs  = store.list_documents(tenant_id=tenant_id)
        has_upload = len(user_docs) > 0
    except Exception:
        has_upload = False

    if has_upload:
        source_choice = st.radio(
            "Where should answers come from?",
            ["Textbook + My Notes  (recommended)", "My Notes only"],
            index=0,
            label_visibility="collapsed",
        )
        source_type_filter = None if "Textbook" in source_choice else "user_upload"
    else:
        source_type_filter = None
        st.caption("Upload your notes in **Upload PDF** to enable personalised study mode.")

    st.divider()

    # ── KB status ─────────────────────────────────────────────────────────
    st.subheader("Knowledge base")
    try:
        global_docs = store.list_documents(tenant_id=cfg.global_tenant_id)
        if global_docs:
            doc = global_docs[0]
            st.success("Ready")
            if is_admin:
                cards  = store.get_cards(doc.id)
                nodes  = store.get_raptor_tree(doc.id)
                c1, c2 = st.columns(2)
                c1.metric("Cards",        len(cards))
                c2.metric("RAPTOR nodes", len(nodes))
                st.caption(_colpali_status_badge(doc.colpali_status))
                if not cards:
                    if st.button("⚡ Generate Phase 2 artifacts", use_container_width=True):
                        with st.spinner("Running…"):
                            generate_phase2_artifacts(doc.id, cfg)
                        st.rerun()
            else:
                st.caption(f"📚 {doc.filename} loaded")
        else:
            st.warning("No textbook loaded yet.")
    except Exception as e:
        st.error(f"DB error: {e}")


# ── Build tab list depending on role ──────────────────────────────────────
if is_admin:
    (tab_upload, tab_search, tab_cards,
     tab_raptor, tab_visual, tab_graph, tab_status) = st.tabs([
        "📄 Upload PDF",
        "🔍 Ask a Question",
        "🃏 Learning Cards",
        "🌲 RAPTOR Tree",
        "🖼️ Visual Search",
        "🕸️ Concept Graph",
        "📊 Admin Status",
    ])
else:
    tab_upload, tab_search, tab_cards, tab_visual, tab_graph = st.tabs([
        "📄 Upload PDF",
        "🔍 Ask a Question",
        "🃏 Learning Cards",
        "🖼️ Visual Search",
        "🕸️ Concept Graph",
    ])
    tab_raptor = None
    tab_status = None


# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — Upload PDF
# ══════════════════════════════════════════════════════════════════════════
with tab_upload:
    if is_admin:
        st.header("Upload PDF")
        source_type_up = st.radio(
            "Upload as", ["User upload", "Base textbook (global)"],
            horizontal=True,
        )
        upload_as_base = source_type_up == "Base textbook (global)"
    else:
        st.header("Upload your study notes")
        st.caption(
            "Upload a PDF of your lecture notes, a paper, or any supplementary reading. "
            "Synapse will learn from it alongside the course textbook."
        )
        upload_as_base = False

    uploaded = st.file_uploader("Choose a PDF", type=["pdf"])

    if not is_admin:
        col1, col2 = st.columns(2)
        with col1:
            subject = st.text_input("Topic (optional)", placeholder="e.g. Quantum mechanics")
        with col2:
            difficulty = st.slider("Difficulty", 1, 10, 5)
    else:
        subject, difficulty = None, None

    if uploaded and st.button("Upload & Ingest", type="primary", use_container_width=True):
        effective_tenant = cfg.global_tenant_id if upload_as_base else tenant_id
        effective_src    = "base_textbook" if upload_as_base else "user_upload"

        tmp = Path(cfg.upload_dir) / effective_tenant / uploaded.name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(uploaded.read())

        with st.spinner("Ingesting…"):
            try:
                result = ingest_pdf(
                    pdf_path=str(tmp),
                    tenant_id=effective_tenant,
                    source_type=effective_src,
                    is_global_baseline=upload_as_base,
                    extra_meta={"subject": subject, "difficulty": difficulty},
                    settings=cfg,
                )
                doc_id   = result["document_id"]
                pdf_path = str(tmp)

                if is_admin:
                    st.success(
                        f"✅ Ingested — {result['chunk_count']} chunks, "
                        f"{result['page_count']} pages"
                    )
                    st.json(result)
                else:
                    st.success(
                        f"✅ **{uploaded.name}** is ready!  "
                        f"We processed {result['page_count']} pages into "
                        f"{result['chunk_count']} searchable sections."
                    )
                    st.info(
                        "Visual search and concept graph are being prepared in the background. "
                        "Text search is available right now!",
                        icon="💡",
                    )

                if is_admin:
                    with st.spinner("Generating learning cards & RAPTOR summaries…"):
                        p2 = generate_phase2_artifacts(doc_id, cfg)
                        st.success(
                            f"⚡ {p2['cards_generated']} cards, "
                            f"{p2['raptor_nodes']} RAPTOR nodes (levels {p2['raptor_levels']})"
                        )

                # ── Phase 3: fire background thread ───────────────────────
                # For base textbooks run_phase3.py is the preferred path;
                # for user uploads we kick off async so upload returns fast.
                thread = threading.Thread(
                    target=generate_phase3_artifacts,
                    kwargs={"document_id": doc_id, "pdf_path": pdf_path, "settings": cfg},
                    daemon=True,
                )
                thread.start()
                st.info("🔄 Visual embeddings + concept graph are being built in the background.", icon="🖼️")

            except Exception as e:
                st.error(f"Failed: {e}")


# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — Ask a Question
# ══════════════════════════════════════════════════════════════════════════
with tab_search:
    if is_admin:
        st.header("Search (admin view)")
    else:
        st.header("Ask a question")
        st.caption(
            "Ask anything about your course. Synapse searches the textbook "
            + ("and your notes " if has_upload else "")
            + "to find the most relevant passages."
        )

    if is_admin:
        col_a, col_b = st.columns(2)
        also_raptor = col_a.checkbox("Include RAPTOR summaries", value=True)
        also_graph  = col_b.checkbox("Include Concept Graph (GraphRAG)", value=True)
    else:
        also_raptor = True
        also_graph  = True

    query = st.text_area(
        "Your question",
        height=80,
        placeholder="e.g. What is Newton's second law and how does it apply to everyday motion?",
        label_visibility="collapsed" if not is_admin else "visible",
    )

    if st.button("Search", type="primary", use_container_width=True) and query.strip():
        with st.spinner("Finding the best answers…"):
            try:
                from src.pdf_ingestion.embedder import get_embedder
                embedder = get_embedder(cfg)
                q_vec    = embedder.embed_query(query)
                s        = DocumentStore(cfg)

                chunk_results = s.search(
                    query_vector=q_vec,
                    tenant_id=tenant_id,
                    source_type=source_type_filter,
                    limit=6,
                )

                raptor_results = []
                if also_raptor:
                    from qdrant_client.models import FieldCondition, Filter, MatchValue
                    rr = s._qdrant.query_points(
                        collection_name=cfg.qdrant_collection,
                        query=q_vec.tolist(),
                        query_filter=Filter(must=[
                            FieldCondition(key="source_type",
                                          match=MatchValue(value="raptor_summary")),
                        ]),
                        limit=2,
                        with_payload=True,
                    )
                    raptor_results = [{"score": h.score, **h.payload} for h in rr.points]

                graph_results = []
                if also_graph:
                    try:
                        from src.pdf_ingestion.graph_builder import get_graph_builder
                        graph = get_graph_builder(cfg)
                        graph_results = graph.graph_search(
                            query_text=query,
                            tenant_id=tenant_id,
                            limit=3,
                        )
                    except Exception:
                        graph_results = []

                if not chunk_results and not raptor_results and not graph_results:
                    st.info("No results found — try rephrasing your question.")
                else:
                    # ── RAPTOR summaries ─────────────────────────────────
                    if raptor_results:
                        st.subheader("📝 Topic Overview")
                        for r in raptor_results:
                            with st.container(border=True):
                                st.markdown(r.get("text", ""))
                                if is_admin:
                                    st.caption(
                                        f"RAPTOR L{r.get('raptor_level','?')} · "
                                        f"score={r['score']:.3f} · "
                                        f"cluster {r.get('cluster_id','?')}"
                                    )
                        st.divider()

                    # ── GraphRAG results ──────────────────────────────────
                    if graph_results:
                        st.subheader("🕸️ Concept-Connected Passages")
                        for gr in graph_results:
                            with st.container(border=True):
                                concepts = " → ".join(gr.get("concept_path", []))
                                st.caption(f"Concepts: {concepts}  |  hops: {gr.get('hop_distance', '?')}")
                                st.markdown(gr.get("text_preview", ""))
                        st.divider()

                    # ── Chunk results ─────────────────────────────────────
                    st.subheader("📄 Relevant Passages")
                    for i, r in enumerate(chunk_results, 1):
                        relevance = _relevance(r["score"])
                        source    = _source_label(r)

                        if is_admin:
                            label = (
                                f"#{i}  {relevance}  |  "
                                f"{r.get('source_type','?')}  |  "
                                f"score={r['score']:.3f}  |  "
                                f"page {r.get('page_number','?')}"
                            )
                        else:
                            label = f"#{i}  {source}  ·  {relevance}"

                        with st.expander(label, expanded=(i == 1)):
                            st.markdown(r.get("text", ""))
                            if is_admin:
                                st.caption(
                                    f"tenant={r.get('tenant_id','')}  "
                                    f"model={r.get('embedding_version','')}  "
                                    f"chars={r.get('char_start','?')}–{r.get('char_end','?')}"
                                )

            except Exception as e:
                st.error(f"Search error: {e}")


# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — Learning Cards
# ══════════════════════════════════════════════════════════════════════════
with tab_cards:
    if is_admin:
        st.header("🃏 Learning Cards — Admin Review")
        st.caption("All 7 card types per chunk, generated by Llama 3.2.")
    else:
        st.header("🃏 Study Cards")
        st.caption("Flashcards generated from your course material. Use them to review and self-test.")

    try:
        store    = DocumentStore(cfg)
        all_docs = store.list_documents()
        docs_with_cards = [(d, store.get_cards(d.id)) for d in all_docs if store.get_cards(d.id)]

        if not docs_with_cards:
            st.info(
                "No study cards yet."
                + (" Cards are generated automatically after PDF ingestion."
                   if not is_admin else " Run Phase 2 from the sidebar."),
                icon="💡",
            )
        else:
            doc_labels = {d.id: d.filename for d, _ in docs_with_cards}
            sel_doc_id = st.selectbox(
                "Material",
                options=list(doc_labels.keys()),
                format_func=lambda x: doc_labels[x],
                label_visibility="collapsed" if not is_admin else "visible",
            )

            sel_types = st.multiselect(
                "Card types" if is_admin else "Show me",
                options=list(CARD_ICONS.keys()),
                default=list(CARD_ICONS.keys()),
                format_func=lambda x: f"{CARD_ICONS[x]} {x.capitalize()}",
            )

            cards    = store.get_cards(sel_doc_id)
            filtered = [c for c in cards if c.card_type in sel_types]

            if is_admin:
                st.markdown(f"**{len(filtered)} cards** from `{doc_labels[sel_doc_id]}`")

            st.divider()

            for ct in sel_types:
                type_cards = [c for c in filtered if c.card_type == ct]
                if not type_cards:
                    continue
                icon = CARD_ICONS.get(ct, "📌")
                with st.expander(
                    f"{icon} {ct.capitalize()}s  ({len(type_cards)})",
                    expanded=(ct in ("summary", "question", "objective")),
                ):
                    for card in type_cards:
                        with st.container(border=True):
                            st.markdown(f"**{card.title}**")
                            st.markdown(card.content)
                            if ct == "question" and card.answer:
                                with st.expander("Reveal answer"):
                                    st.success(card.answer)
                            if is_admin:
                                st.caption(
                                    f"chunk `{card.chunk_id[:8]}…`  "
                                    f"v{card.version}  "
                                    f"{'✅ active' if card.is_active else '❌ inactive'}"
                                )

    except Exception as e:
        st.error(f"Cards error: {e}")


# ══════════════════════════════════════════════════════════════════════════
# TAB 4 — RAPTOR Tree  (admin only)
# ══════════════════════════════════════════════════════════════════════════
if tab_raptor is not None:
    with tab_raptor:
        st.header("🌲 RAPTOR Hierarchical Summaries")
        st.caption(
            "Recursive Abstractive Processing for Tree-Organized Retrieval.  "
            "Chunks → cluster summaries (L1) → meta-summary (L2)."
        )
        try:
            store    = DocumentStore(cfg)
            all_docs = store.list_documents()
            docs_with_raptor = [
                (d, store.get_raptor_tree(d.id))
                for d in all_docs if store.get_raptor_tree(d.id)
            ]
            if not docs_with_raptor:
                st.info("No RAPTOR nodes yet. Run Phase 2 from the sidebar.", icon="💡")
            else:
                doc_labels = {d.id: d.filename for d, _ in docs_with_raptor}
                sel = st.selectbox(
                    "Document",
                    options=list(doc_labels.keys()),
                    format_func=lambda x: doc_labels[x],
                )
                nodes = store.get_raptor_tree(sel)
                l1    = [n for n in nodes if n.level == 1]
                l2    = [n for n in nodes if n.level == 2]

                c1, c2, c3 = st.columns(3)
                c1.metric("Level-1 (cluster)",  len(l1))
                c2.metric("Level-2 (root)",     len(l2))
                c3.metric("Total nodes",         len(nodes))
                st.divider()

                if l2:
                    st.subheader("Level 2 — Root meta-summary")
                    for n in l2:
                        with st.container(border=True):
                            st.markdown(n.summary)
                            import json as _json
                            child_count = len(_json.loads(n.child_ids_json))
                            st.caption(
                                f"Cluster {n.cluster_id} · "
                                f"summarises {child_count} level-1 nodes · "
                                f"v{n.version}"
                            )

                st.subheader("Level 1 — Cluster summaries")
                import json as _json
                for n in l1:
                    child_ids = _json.loads(n.child_ids_json)
                    with st.expander(
                        f"Cluster {n.cluster_id}  ({len(child_ids)} source chunks)",
                        expanded=False,
                    ):
                        st.markdown(n.summary)
                        st.caption(
                            f"Qdrant: `{n.qdrant_point_id[:12]}…`  "
                            f"parent: `{(n.parent_id or 'none')[:12]}…`  "
                            f"v{n.version}"
                        )
                        with st.expander("Source chunk IDs"):
                            for cid in child_ids:
                                st.code(cid, language=None)

        except Exception as e:
            st.error(f"RAPTOR error: {e}")


# ══════════════════════════════════════════════════════════════════════════
# TAB 5 — Visual Search (Phase 3)
# ══════════════════════════════════════════════════════════════════════════
with tab_visual:
    st.header("🖼️ Visual Search")
    st.caption(
        "Upload an image (a diagram, figure, or photo of a page) to find the most "
        "similar pages in the knowledge base using ColPali late-interaction search."
    )

    # Check if any documents have visual embeddings ready
    try:
        store    = DocumentStore(cfg)
        all_docs = store.list_documents()
        ready_docs   = [d for d in all_docs if d.colpali_status == "ready"]
        pending_docs = [d for d in all_docs if d.colpali_status in ("processing", "pending")]
    except Exception:
        ready_docs = []
        pending_docs = []

    if pending_docs:
        st.info(
            f"⏳ Visual embeddings are being generated for "
            f"{len(pending_docs)} document(s). Text search is available now — "
            "come back shortly for visual search.",
            icon="🔄",
        )

    if not ready_docs:
        st.warning(
            "No documents have visual embeddings yet. "
            "Run `scripts/run_phase3.py --tenant global` for the base textbook, "
            "or upload a PDF — visual embeddings will be generated automatically.",
            icon="💡",
        )
    else:
        query_image_file = st.file_uploader(
            "Upload a query image (PNG, JPG)",
            type=["png", "jpg", "jpeg"],
            key="visual_query",
        )
        n_results = st.slider("Results to show", 1, 10, 5)

        if query_image_file and st.button("Search by Image", type="primary"):
            with st.spinner("Embedding query image and searching…"):
                try:
                    from PIL import Image
                    import io
                    from src.pdf_ingestion.colpali_embedder import get_colpali_embedder
                    from src.pdf_ingestion.image_store import get_image_store

                    query_image = Image.open(io.BytesIO(query_image_file.read()))
                    colpali     = get_colpali_embedder(cfg)
                    q_patches   = colpali.embed_query_image(query_image)

                    s       = DocumentStore(cfg)
                    results = s.visual_search(
                        query_patches=q_patches,
                        tenant_id=tenant_id,
                        limit=n_results,
                    )

                    if not results:
                        st.info("No visual matches found.")
                    else:
                        image_store = get_image_store(cfg)
                        st.subheader(f"Top {len(results)} matching pages")
                        cols = st.columns(min(3, len(results)))
                        for i, r in enumerate(results):
                            col = cols[i % 3]
                            with col:
                                try:
                                    img_bytes = image_store.get(r["image_key"])
                                    col.image(img_bytes, use_container_width=True)
                                except Exception:
                                    col.info("Image unavailable")
                                col.caption(
                                    f"Page {r.get('page_number', '?')}  ·  "
                                    f"score {r['score']:.3f}"
                                )
                                if is_admin:
                                    col.caption(
                                        f"doc: `{r.get('document_id','?')[:12]}…`  "
                                        f"key: `{r.get('image_key','?')}`"
                                    )

                except Exception as e:
                    st.error(f"Visual search error: {e}")

        st.divider()
        st.caption(
            f"**{len(ready_docs)}** document(s) indexed for visual search.  "
            "ColPali encodes visual structure, layout, diagrams, and equations."
        )


# ══════════════════════════════════════════════════════════════════════════
# TAB 6 — Concept Graph / GraphRAG (Phase 3)
# ══════════════════════════════════════════════════════════════════════════
with tab_graph:
    st.header("🕸️ Concept Graph Search")
    st.caption(
        "GraphRAG finds passages connected through concept relationships — "
        "multi-hop reasoning that vector search alone misses. "
        "Requires Memgraph (`docker compose --profile phase3 up`)."
    )

    graph_query = st.text_input(
        "Ask a concept-reasoning question",
        placeholder="e.g. Why does a satellite stay in orbit?",
    )

    if is_admin:
        hop_limit = st.slider("Max concept hops", 1, 3, 2)
        show_concepts = st.checkbox("Show concept paths", value=True)
    else:
        hop_limit = 2
        show_concepts = False

    if st.button("Graph Search", type="primary") and graph_query.strip():
        with st.spinner("Traversing concept graph…"):
            try:
                from src.pdf_ingestion.graph_builder import get_graph_builder
                from src.pdf_ingestion.store import DocumentStore as DS
                graph = get_graph_builder(cfg)
                results = graph.graph_search(
                    query_text=graph_query,
                    tenant_id=tenant_id,
                    limit=6,
                )

                if not results:
                    st.info(
                        "No concept-graph results found. This may mean:\n"
                        "- Memgraph is not running (`docker compose --profile phase3 up`)\n"
                        "- Phase 3 graph hasn't been built yet for this document\n"
                        "- The query concepts don't match extracted concept nodes"
                    )
                else:
                    st.subheader(f"Found {len(results)} concept-connected passage(s)")
                    for i, r in enumerate(results, 1):
                        with st.container(border=True):
                            if show_concepts or not is_admin:
                                concepts = " → ".join(r.get("concept_path", []))
                                st.caption(f"🔗 Concept path: **{concepts}**  |  hops: {r.get('hop_distance', '?')}")
                            st.markdown(r.get("text_preview", ""))
                            if is_admin:
                                st.caption(f"chunk_id: `{r.get('chunk_id','?')}`")

            except Exception as e:
                st.error(f"Graph search error: {e}")

    with st.expander("💡 Example questions that benefit from GraphRAG"):
        st.markdown("""
- *Why does a satellite stay in orbit?* — needs Newton's 2nd law → centripetal force → orbital mechanics chain
- *What should I know before studying Maxwell's equations?* — prerequisite concept traversal
- *How is simple harmonic motion related to wave propagation?* — RELATES_TO multi-hop
- *How do conservation laws appear across different areas of physics?* — cross-chapter concept linking
        """)


# ══════════════════════════════════════════════════════════════════════════
# TAB 7 — Admin Status  (admin only)
# ══════════════════════════════════════════════════════════════════════════
if tab_status is not None:
    with tab_status:
        st.header("📊 System Status")
        if st.button("Refresh"):
            st.rerun()
        try:
            store    = DocumentStore(cfg)
            all_docs = store.list_documents()
            base_d   = [d for d in all_docs if d.source_type == "base_textbook"]
            user_d   = [d for d in all_docs if d.source_type == "user_upload"]
            t_chunks = sum(d.chunk_count for d in all_docs)
            t_cards  = sum(len(store.get_cards(d.id)) for d in all_docs)
            t_raptor = sum(len(store.get_raptor_tree(d.id)) for d in all_docs)
            t_visual = sum(len(store.get_page_images(d.id)) for d in all_docs)
            visual_ready = sum(1 for d in all_docs if d.colpali_status == "ready")

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Base textbooks",  len(base_d))
            c2.metric("User PDFs",       len(user_d))
            c3.metric("Total chunks",    f"{t_chunks:,}")
            c4.metric("Cards (Ph.2)",    f"{t_cards:,}")
            c5.metric("RAPTOR nodes",    f"{t_raptor:,}")
            c6.metric("Visual pages",    f"{t_visual:,}")

            st.divider()
            if all_docs:
                import pandas as pd
                rows = []
                for d in all_docs:
                    n_cards  = len(store.get_cards(d.id))
                    n_raptor = len(store.get_raptor_tree(d.id))
                    n_visual = len(store.get_page_images(d.id))
                    rows.append({
                        "Filename":        d.filename,
                        "Tenant":          d.tenant_id,
                        "Type":            d.source_type,
                        "Pages":           d.page_count,
                        "Chunks":          d.chunk_count,
                        "Cards":           n_cards,
                        "RAPTOR":          n_raptor,
                        "Phase 2":         "✅" if n_cards > 0 else "⏳",
                        "Visual Pages":    n_visual,
                        "Visual Status":   _colpali_status_badge(d.colpali_status),
                        "Embedding":       d.embedding_version,
                        "Created":         str(d.created_at)[:19],
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True)
            else:
                st.info("No documents.")
        except Exception as e:
            st.error(f"Status error: {e}")

# ── Footer ────────────────────────────────────────────────────────────────
st.divider()
if not is_admin:
    st.caption(
        "Synapse Learning · Powered by Hybrid RAG  "
        "· [Admin access](/?admin=true)"
    )
else:
    st.caption(
        "Synapse Learning · Admin mode  "
        "· [Student view](?)"
    )
