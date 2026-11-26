"""E-04c: embed each question Inkling read, for the escalation gate (docs/experiments.md).

The text is the question as the models saw it (readout.py's prompt, options in the case's order). A long state
keeps its head and tail. Qwen3-Embedding is instruction-aware, so the text is given as a query with one fixed
instruction. Served by `serve.sh embed` on :8084.

Usage: python3 -I embed.py   (writes results/embed-qwen3-0.6b.jsonl; resumes)
"""
from __future__ import annotations

import json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from readout import DATA, SLICES, options, prompt  # noqa: E402

OUT = os.path.join(HERE, "results", "embed-qwen3-0.6b.jsonl")
INSTRUCT = "Given a decision question, represent what kind of question it is and what it takes to answer it"
HEAD, TAIL = 8000, 12000  # characters kept from a long text (about 6k tokens in all, under the server's 8k)


def text(case):
    t = prompt(case, options(case))
    if len(t) > HEAD + TAIL:
        t = t[:HEAD] + "\n...\n" + t[-TAIL:]
    return f"Instruct: {INSTRUCT}\nQuery:{t}"


def embed(texts, port=8084):
    body = json.dumps({"input": texts, "model": "embed"}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/embeddings", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return [d["embedding"] for d in sorted(json.load(r)["data"], key=lambda d: d["index"])]


def main():
    want = {json.loads(l)["case_id"] for l in open(os.path.join(HERE, "results", "inkling.jsonl"))}
    done = {json.loads(l)["case_id"] for l in open(OUT)} if os.path.exists(OUT) else set()
    cases = [r for s in SLICES for r in map(json.loads, open(os.path.join(DATA, f"{s}.jsonl")))
             if r["case_id"] in want and r["case_id"] not in done]
    print(f"{len(cases)} to embed", flush=True)
    with open(OUT, "a") as f:
        for i in range(0, len(cases), 8):
            batch = cases[i:i + 8]
            for c, v in zip(batch, embed([text(c) for c in batch])):
                f.write(json.dumps({"case_id": c["case_id"], "v": [round(x, 5) for x in v]}) + "\n")
            f.flush()
            if i % 200 == 0:
                print(i, flush=True)


if __name__ == "__main__":
    main()
