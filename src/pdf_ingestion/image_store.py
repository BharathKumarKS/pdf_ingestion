"""
Image storage abstraction — Phase 3.

Stores rasterized page PNGs behind a simple save/get interface so the rest
of the pipeline never depends on a specific backend.

Backends
--------
local  (default) — files on disk under cfg.page_images_dir
minio            — S3-compatible MinIO (docker-compose --profile phase3)

Switch backend via IMAGE_STORE_BACKEND env var or Settings.image_store_backend.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger

from src.core.config import Settings, get_settings


class ImageStore(ABC):
    @abstractmethod
    def save(self, doc_id: str, page_number: int, image_bytes: bytes) -> str:
        """Persist image bytes and return a key that can be passed to get()."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Return the raw image bytes for a previously saved key."""


# -- Local disk ----------------------------------------------------------------

class LocalImageStore(ImageStore):
    """Stores PNGs under <page_images_dir>/<doc_id>/page_<N>.png."""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def save(self, doc_id: str, page_number: int, image_bytes: bytes) -> str:
        doc_dir = self._base / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        rel_key = f"{doc_id}/page_{page_number:04d}.png"
        (self._base / rel_key).write_bytes(image_bytes)
        return rel_key

    def get(self, key: str) -> bytes:
        return (self._base / key).read_bytes()


# -- MinIO ---------------------------------------------------------------------

class MinIOImageStore(ImageStore):
    """Stores PNGs as objects in a MinIO bucket."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        from minio import Minio
        self._client = Minio(
            endpoint.replace("http://", "").replace("https://", ""),
            access_key=access_key,
            secret_key=secret_key,
            secure=endpoint.startswith("https://"),
        )
        self._bucket = bucket
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)
            logger.info("MinIO: created bucket '{}'", bucket)

    def save(self, doc_id: str, page_number: int, image_bytes: bytes) -> str:
        import io
        key = f"{doc_id}/page_{page_number:04d}.png"
        self._client.put_object(
            self._bucket, key,
            data=io.BytesIO(image_bytes),
            length=len(image_bytes),
            content_type="image/png",
        )
        return key

    def get(self, key: str) -> bytes:
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


# -- Factory -------------------------------------------------------------------

def get_image_store(settings: Settings | None = None) -> ImageStore:
    cfg = settings or get_settings()
    if cfg.image_store_backend == "minio":
        return MinIOImageStore(
            endpoint=cfg.minio_endpoint,
            access_key=cfg.minio_access_key,
            secret_key=cfg.minio_secret_key,
            bucket=cfg.minio_bucket,
        )
    return LocalImageStore(base_dir=cfg.page_images_dir)
