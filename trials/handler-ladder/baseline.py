"""E-17 baseline: the large model alone on the cases among the last 150 of the stream that a cheaper rung answered.

Reads results/stream.jsonl; writes results/baseline.jsonl (resumable: cases already there are skipped).
Usage: python3 -I baseline.py [--last 150]    (needs the large model on :8081; flags as in stream.py)
"""
from __future__ import annotations

import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import smoke  # noqa: E402
import stream  # noqa: E402
import summarize  # noqa: E402


def run(data_dir, out_dir, large_fn, n=300, last=150, log=print):
    """-> number of cases newly answered."""
    cases = {c["id"]: c for c in stream.load_cases(data_dir, n)}
    recs = summarize.jsonl(os.path.join(out_dir, "stream.jsonl"))
    tail = {r["id"] for r in recs[-last:] if r["rung"] != "large"} if len(recs) >= n else None
    if tail is None:
        raise SystemExit("the stream is not complete; run all chunks first")
    path = os.path.join(out_dir, "baseline.jsonl")
    have = {r["id"] for r in summarize.jsonl(path)}
    large, k = stream.Meter(large_fn), 0
    with open(path, "a") as f:
        for r in recs:
            if r["id"] in tail and r["id"] not in have:
                before = large.snap()
                text = large.ask(smoke.prompt(cases[r["id"]]))
                raw = smoke.extract(text)
                ans = stream.check(raw, cases[r["id"]]) or raw or ""
                f.write(json.dumps({"id": r["id"], "answer": ans, "text": text,
                                    "large": stream.delta(before, large.snap())}) + "\n")
                f.flush()
                k += 1
                log(f"baseline {k}/{len(tail - have)} {r['id']} {ans!r}")
    return k


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--last", type=int, default=150)
    stream.add_model_flags(ap)
    a = ap.parse_args()
    run(a.data, a.out, stream.build_models(a)[0], a.n, a.last)


if __name__ == "__main__":
    main()
