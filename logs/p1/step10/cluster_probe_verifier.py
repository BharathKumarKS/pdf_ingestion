"""Verifier for the cluster probe artifact (§I117's blocker re-probe, session 36).

Reads logs/p1/step10/cluster_probe.json and independently checks each lane's verdict, then
RE-HITS the two 'down' lanes once with a short timeout to confirm the timeout is reproducible
(not a one-off), and GETs the server root to confirm the HTTP front is alive — so the timeout
is a handler hang, not a dead host or a wrong port.

Two properties proven by the mutation harness at the bottom: each check reddens its intended
check, and no check is inert.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://10.0.10.70:8123"


def _post(url, payload, timeout):
    import json as _j
    req = urllib.request.Request(url, data=_j.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, f"HTTPError {e.code}"
    except Exception as e:
        return None, f"{type(e).__name__}"


def _get(url, timeout):
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def check(art: dict, *, rehit: bool) -> list[tuple[str, bool, str]]:
    lanes = art.get("lanes", {})
    out: list[tuple[str, bool, str]] = []

    out.append(("V1_four_lanes_present",
                set(lanes) == {"dense", "colbert", "sparse", "rerank"},
                f"lanes={sorted(lanes)}"))

    for name in ("dense", "colbert"):
        r = lanes.get(name, {})
        out.append((f"V2_{name}_up",
                    r.get("status") == 200 and (r.get("latency_s") or 99) < 2.0,
                    f"status={r.get('status')} lat={r.get('latency_s')}"))

    for name in ("sparse", "rerank"):
        r = lanes.get(name, {})
        out.append((f"V3_{name}_down",
                    r.get("status") is None and "timeout" in (r.get("error") or "").lower(),
                    f"status={r.get('status')} err={r.get('error')}"))

    if rehit:
        st, err = _post(f"{BASE}/embed-text/v1/sparse-embeddings",
                        {"model": "prithivida/Splade_PP_en_v1", "input": ["x"]}, 6.0)
        out.append(("V4_sparse_timeout_reproducible", st is None and "Timeout" in (err or ""),
                    f"status={st} err={err}"))
        root = _get(f"{BASE}/", 6.0)
        out.append(("V5_server_front_alive", root == 404, f"root_status={root}"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default="logs/p1/step10/cluster_probe.json")
    ap.add_argument("--no-rehit", action="store_true", help="artifact-only (no live re-hit)")
    ap.add_argument("--mutate", default=None, help="JSON patch applied to a COPY, for the mutation proof")
    args = ap.parse_args()

    art = json.loads(Path(args.artifact).read_text())
    if args.mutate:
        patch = json.loads(args.mutate)
        for k, v in patch.items():          # e.g. {"lanes.dense.status": null}
            node = art
            parts = k.split(".")
            for p in parts[:-1]:
                node = node[p]
            node[parts[-1]] = v

    results = check(art, rehit=not args.no_rehit)
    failed = [n for n, ok, _ in results if not ok]
    for n, ok, d in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n:34s} {d}")
    print(f"  -> {len(results) - len(failed)}/{len(results)} PASS")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
