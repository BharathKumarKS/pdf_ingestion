#!/usr/bin/env python
"""Is the GATED `google/embeddinggemma-300m` readable with the configured HF credential?

Why this exists: Stage C (the gemma re-embed) cannot run until the gemma **tokenizer** is available
locally — the late-chunk path gets per-token vectors from the cluster, but the character offsets that
define each child's span come from a LOCAL tokenization. The repo is gated, so this is a credential
question, and it has **two independent conditions**:

  1. the token must be permitted to reach **public gated repositories**
     (a fine-grained token needs that permission; a **classic read token** has it by default), and
  2. the **Gemma licence** must be accepted at https://huggingface.co/google/embeddinggemma-300m

⚠️ **The reason this script reads the status with an explicit auth header instead of trusting
`transformers`:** `transformers`/`huggingface_hub` report the 403 from condition (1) as
``LocalEntryNotFoundError: We couldn't connect to 'https://huggingface.co' … check your internet
connection``, with ``status=None``. **The text blames the network; the cause is a permission.** So the
raw status is the only trustworthy reading.

Exit codes: 0 = readable (both conditions satisfied); 3 = not yet; 2 = no credential configured.

Run:
    unset PYTHONPATH
    uv run python -u logs/p1/step10/check_hf_gated_access.py
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

GATED = "https://huggingface.co/google/embeddinggemma-300m/resolve/main/config.json"
CONTROL = "https://huggingface.co/bert-base-uncased/resolve/main/config.json"


def probe(label: str, url: str, token: str | None) -> int | None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            n = len(r.read())
            print(f"  {label:46} -> {r.status}  ({n} bytes)")
            return r.status
    except urllib.error.HTTPError as e:
        detail = e.read()[:220].decode("utf-8", "replace").replace("\n", " ")
        print(f"  {label:46} -> HTTP {e.code}  {detail}")
        return e.code
    except Exception as e:
        print(f"  {label:46} -> {type(e).__name__}: {str(e)[:140]}")
        return None


def main() -> int:
    from huggingface_hub import get_token

    tok = get_token()
    tf = Path.home() / ".cache" / "huggingface" / "token"
    print("credential:")
    print(f"  token file {tf}: exists={tf.exists()}"
          + (f" chars={len(tf.read_text().strip())}" if tf.exists() else ""))
    print(f"  get_token(): {'a token is configured' if tok else 'None'}")
    if not tok:
        print("\nNO CREDENTIAL — run `huggingface-cli login` first (exit 2)")
        return 2

    try:
        from huggingface_hub import HfApi
        who = HfApi().whoami(token=tok)
        print(f"  whoami: {who.get('name')} (type={who.get('type')})")
    except Exception as exc:
        print(f"  whoami FAILED: {type(exc).__name__}: {str(exc)[:140]}")

    print("\nrequests:")
    probe("huggingface.co (no auth)", "https://huggingface.co", None)
    probe("ungated control (no auth)", CONTROL, None)
    probe("GATED, no auth", GATED, None)
    status = probe("GATED, with auth  <-- the answer", GATED, tok)

    print("\nverdict:")
    if status == 200:
        print("  ✅ READABLE — the token reaches gated repos AND the licence is accepted.")
        print("     Stage C0 can run: uv run python -u logs/p1/step10/c0_late_chunk_timing.py")
        return 0
    if status == 403:
        print("  ❌ 403 — read the server's message above. If it names 'public gated repositories'")
        print("     / 'fine-grained token settings', fix the TOKEN:")
        print("       https://huggingface.co/settings/tokens  (or create a CLASSIC read token)")
        print("     If it names the licence/terms, accept them at:")
        print("       https://huggingface.co/google/embeddinggemma-300m")
        return 3
    if status == 401:
        print("  ❌ 401 — the stored token is not accepted. Re-run `huggingface-cli login`.")
        return 3
    print(f"  ⚠️ INCONCLUSIVE (status={status}) — the request never reached an access decision.")
    print("     A null here means a real connectivity problem; 200/401/403 mean it is permissions.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
