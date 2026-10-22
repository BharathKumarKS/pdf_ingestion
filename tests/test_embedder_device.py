"""Tests for the Nomic embedder's device selection (``src/pdf_ingestion/embedder.py``).

§I23(d): the selection was ``"cuda" if use_gpu else "cpu"`` — **no availability check**, unlike
``parser.py``. Measured on the author's Mac (``torch 2.8.0``, arm64): **cuda False / mps True**, so
``USE_GPU=true`` there asked sentence-transformers for a `cuda` device that does not exist.

What has to be true:

1. ``USE_GPU=false`` is still plain CPU — no torch import, no device probing, no behaviour change.
2. ``USE_GPU=true`` resolves to the best device that is **actually available**: CUDA first, then
   Apple MPS, then CPU.
3. It never *raises* — an absent torch, or a torch with no `backends.mps`, degrades to CPU.
4. The resolved device is what gets passed to sentence-transformers, and the log line cannot
   disagree with it.

Offline throughout: `torch` is a stand-in module in ``sys.modules``, so no model loads and no
accelerator is touched.
"""
from __future__ import annotations

import sys
import types

import pytest

from src.pdf_ingestion.embedder import NomicEmbedder, resolve_device


class _FakeCuda:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class _FakeMps:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


def _fake_torch(*, cuda: bool, mps: bool | None) -> types.SimpleNamespace:
    """A torch stand-in. `mps=None` means a build with no `torch.backends.mps` at all."""
    backends = types.SimpleNamespace() if mps is None else types.SimpleNamespace(mps=_FakeMps(mps))
    return types.SimpleNamespace(cuda=_FakeCuda(cuda), backends=backends)


@pytest.fixture
def fake_torch(monkeypatch):
    """Install a torch stand-in; `resolve_device` imports torch at call time, so this works."""
    def _install(**kwargs):
        monkeypatch.setitem(sys.modules, "torch", _fake_torch(**kwargs))
    return _install


class TestResolveDevice:
    def test_use_gpu_false_is_cpu_and_touches_nothing(self, monkeypatch):
        """The default path must not even import torch — that is the point of the early return."""
        monkeypatch.setitem(sys.modules, "torch", None)   # `import torch` would raise on this
        assert resolve_device(False) == "cpu"

    def test_cuda_wins_when_available(self, fake_torch):
        fake_torch(cuda=True, mps=True)
        assert resolve_device(True) == "cuda"

    def test_mps_is_used_when_cuda_is_absent(self, fake_torch):
        """The measured Mac case: cuda False / mps True (§I23(d))."""
        fake_torch(cuda=False, mps=True)
        assert resolve_device(True) == "mps"

    def test_cpu_when_neither_is_available(self, fake_torch):
        fake_torch(cuda=False, mps=False)
        assert resolve_device(True) == "cpu"

    def test_torch_without_mps_backend_does_not_raise(self, fake_torch):
        """A torch build predating `backends.mps` must degrade, not AttributeError."""
        fake_torch(cuda=False, mps=None)
        assert resolve_device(True) == "cpu"

    def test_absent_torch_degrades_to_cpu(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "torch", None)
        assert resolve_device(True) == "cpu"


class TestDeviceIsActuallyPassed:
    """The selection is only worth anything if sentence-transformers is told about it."""

    def _capture_st_kwargs(self, monkeypatch, device: str) -> dict:
        """Load `NomicEmbedder` with a fake SentenceTransformer and return the kwargs it got."""
        import src.pdf_ingestion.embedder as emb

        seen: dict = {}

        class _FakeST:
            def __init__(self, name, **kwargs):
                seen.update(kwargs)
                seen["_model_name"] = name

            def eval(self):
                pass

        monkeypatch.setattr(emb, "resolve_device", lambda use_gpu: device)
        monkeypatch.setitem(sys.modules, "sentence_transformers",
                            types.SimpleNamespace(SentenceTransformer=_FakeST))

        class _Cfg:
            use_gpu = True
            embedding_model = "nomic-ai/nomic-embed-text-v1.5"
            embedding_dim = 768
            embedding_dim_low = 64
            embedding_batch_size = 8
            model_cache_dir = "/tmp"

        NomicEmbedder(settings=_Cfg())._load()  # type: ignore[arg-type]  # a settings double
        return seen

    def test_mps_is_passed_through(self, monkeypatch):
        assert self._capture_st_kwargs(monkeypatch, "mps")["device"] == "mps"

    def test_cuda_is_passed_through(self, monkeypatch):
        assert self._capture_st_kwargs(monkeypatch, "cuda")["device"] == "cuda"
