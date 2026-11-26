"""E-04a: Liquid's open d1 decision models on JevBench, through llama.cpp's native `/v1/systemone` endpoint.

The JevBench question (`type`, `instructions`, `criteria`) is d1's own format, so each case is sent as it is, with
its state. Each case is read twice, with the options in the case's order and reversed, as `readout.py` does, and
written in the same record format, so `score.py` compares d1 with our readouts and with Jev on the same cases.

Usage: python3 -I readout_d1.py --port 8083 --out results/d1-2b.jsonl [--families 1000]
"""
from __future__ import annotations

import argparse, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from readout import sample  # noqa: E402  the same deterministic sample of cases


def post(port, body, timeout=900):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/systemone", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def question(case, reverse):
    q = dict(case["question"])
    c = q.get("criteria")
    if isinstance(c, dict) and reverse:
        q["criteria"] = dict(reversed(list(c.items())))
    return q


def read(case, port, reverse):
    t = time.perf_counter()
    d = post(port, {"state": case["state"], "questions": {"q": question(case, reverse)}})
    ms = (time.perf_counter() - t) * 1000
    a = d["answers"]["q"]
    if case["task_type"] == "noul":
        p = float(a["noul"])
        probs = {"true": p, "false": 1 - p}
    else:
        probs = {k: float(v) for k, v in a["probabilities"].items()}
    return {"probs": probs, "letter_mass": 1.0, "missing_options": 0, "top_token": "", "ms": ms,
            "prompt_tokens": d.get("usage", {}).get("input_tokens")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--families", type=int, default=1000)
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.out):
        done = {(r["case_id"], r["order"]) for r in map(json.loads, open(a.out))}
    cases = sample(a.families)
    todo = [(c, o) for c in cases for o in ("given", "reversed") if (c["case_id"], o) not in done]
    print(f"{len(cases)} cases, {len(todo)} reads to do", flush=True)
    with open(a.out, "a") as f:
        for i, (c, order) in enumerate(todo):
            try:
                r = read(c, a.port, order == "reversed")
            except Exception as e:
                r = {"error": repr(e)[:300]}
            r.update({"case_id": c["case_id"], "family_id": c["family_id"], "slice": c["slice"],
                      "task_type": c["task_type"], "perturbation": c["perturbation"], "order": order,
                      "gold": str(c["gold"]).lower() if c["task_type"] == "noul" else c["gold"]})
            f.write(json.dumps(r) + "\n")
            f.flush()
            if i % 500 == 0:
                print(f"{i}/{len(todo)} {c['slice']} {r.get('ms', 0):.0f} ms {r.get('error', '')}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    sys.exit(main())
