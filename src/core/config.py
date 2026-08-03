from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "Synapse Learning Worlds"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    sqlite_url: str = "sqlite:///./data/synapse.db"

    # Qdrant — local or remote
    # Remote (Support Vectors / Qdrant Cloud) takes priority over local path when set.
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "knowledge_base"
    qdrant_in_memory: bool = False        # True -> in-process RAM (tests only)
    qdrant_local_path: str = "./data/qdrant"  # file-based persistence (no Docker)
    qdrant_url: str = ""                  # e.g. https://xxxx.cloud.qdrant.io
    qdrant_api_key: str = ""              # cluster API key (support vectors)

    # Embedding — Jina v3
    embedding_model: str = "jinaai/jina-embeddings-v3"
    embedding_dim: int = 1024
    embedding_batch_size: int = 8        # 8 on CPU; set 32-64 with GPU
    max_context_tokens: int = 8192       # max tokens per late-chunking window
    use_gpu: bool = False                # set True on GPU VM (CUDA)
    use_stub_embedder: bool = False      # random vectors for unit tests

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64
    min_chunk_tokens: int = 32

    # Multi-tenancy
    global_tenant_id: str = "global"

    # Paths
    model_cache_dir: str = "./data/models"
    upload_dir: str = "./data/user_uploads"
    base_textbook_dir: str = "./data/base_textbooks"

    # LLM — Ollama (default) or OpenAI-compatible cluster
    # Set LLM_BACKEND="openai" to use any OpenAI-compatible API instead of Ollama.
    # All card generation, RAPTOR summaries, and concept extraction use this.
    llm_backend: str = "ollama"            # "ollama" | "openai"

    # Ollama settings (used when llm_backend="ollama")
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout: int = 120            # seconds per generation call

    # OpenAI-compatible settings (used when llm_backend="openai")
    # Works with vLLM, LiteLLM, Together AI, Anyscale, Azure OpenAI, etc.
    openai_api_base: str = "http://localhost:8000"   # cluster endpoint
    openai_api_key: str = "none"                      # "none" if no auth required
    openai_model: str = "meta-llama/Llama-3.2-8B-Instruct"

    use_stub_llm: bool = False           # True -> skip all LLM calls in unit tests

    # Card generation parallelism
    card_gen_workers: int = 4            # parallel Ollama threads for card generation

    # RAPTOR
    raptor_max_levels: int = 3
    raptor_min_cluster_size: int = 2     # minimum chunks per cluster

    # Phase 3 — ColPali visual embeddings
    colpali_model: str = "vidore/colpali-v1.2"
    colpali_collection: str = "visual_knowledge_base"
    colpali_patch_dim: int = 128
    use_stub_colpali: bool = False
    page_images_dir: str = "./data/page_images"
    image_store_backend: str = "local"   # "local" | "minio"

    # Phase 3 — MinIO (active when image_store_backend="minio")
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "synapse"
    minio_secret_key: str = "synapse123"
    minio_bucket: str = "page-images"

    # Phase 3 — Memgraph
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    memgraph_user: str = "memgraph"
    memgraph_password: str = "synapse"
    use_stub_graph: bool = False
    concept_gen_workers: int = 4         # parallel Ollama threads for concept extraction

    api_port: int = 8000

    def ensure_dirs(self) -> None:
        """Create all required local directories on startup."""
        for path_str in (
            self.model_cache_dir,
            self.upload_dir,
            self.base_textbook_dir,
            self.page_images_dir,
            "data",
        ):
            Path(path_str).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
