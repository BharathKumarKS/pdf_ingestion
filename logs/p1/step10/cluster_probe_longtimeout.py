"""Single long-timeout probe — distinguishes a HANG from a SLOW COLD LOAD.
If sparse answers within 150 s it was loading; if it times out at 150 s after
already being hit (warm-up attempts above), it is hung, not cold.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

URL = "http://10.0.10.70:8123/embed-text/v1/sparse-embeddings"
PAYLOAD = {"model": "prithivida/Splade_PP_en_v1", "input": ["Newton's first law"]}

t0 = time.monotonic()
try:
    req = urllib.request.Request(URL, data=json.dumps(PAYLOAD).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=150) as r:
        print(f"ANSWERED status={r.status} after {time.monotonic() - t0:.1f}s")
except Exception as e:
    print(f"NO ANSWER after {time.monotonic() - t0:.1f}s -> {type(e).__name__}: {e}")
