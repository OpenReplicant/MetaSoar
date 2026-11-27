"""E-18 first step: the large model alone on WikiTableQuestions (dev1k), for accuracy and speed (docs/experiments.md).

As smoke.py, with WTQ's data and scorer (`wtq.correct`), and an answer line that says how to write a list. E-18 runs
only if accuracy here is 50% or more (the owner's stop rule). Time is measured, not capped.
Usage: python3 -I smoke_wtq.py [N] [DATA_DIR]   (default 40 cases of ../data/wtq-84dd647-problems; writes results/smoke-wtq.jsonl)
"""
from __future__ import annotations

import json, os, statistics, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import smoke  # noqa: E402
import wtq  # noqa: E402

ANSWER_LINE = "Work it out briefly, then end with one line: Answer: <the answer only>"
LIST_LINE = ("Work it out briefly, then end with one line: Answer: <the answer only; if there are several, all of "
             "them on that line, separated by commas>")


def prompt(p):
    text = smoke.prompt(p)
    assert text.endswith(ANSWER_LINE)
    return text[: -len(ANSWER_LINE)] + LIST_LINE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    data = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "data", "wtq-84dd647-problems")
    probs = json.load(open(os.path.join(data, "problems_dev1k.json")))
    ids = sorted(probs)[:n]
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    out = os.path.join(HERE, "results", "smoke-wtq.jsonl")
    ok, secs = 0, []
    with open(out, "w") as f:
        for i, pid in enumerate(ids):
            p = probs[pid]
            t = time.perf_counter()
            text, usage = smoke.ask(prompt(p), 1500)
            s = time.perf_counter() - t
            pred = smoke.extract(text)
            c = bool(pred is not None and wtq.correct(pred, p))
            ok += c
            secs.append(s)
            f.write(json.dumps({"pid": pid, "pred": pred, "gold": p["answer"], "ok": c, "s": s,
                                "out_tokens": usage.get("completion_tokens"), "prompt_tokens": usage.get("prompt_tokens"),
                                "text": text}) + "\n")
            f.flush()
            print(f"{i + 1}/{n} ok={c} {s:.1f}s pred={pred!r} gold={p['answer']!r}", flush=True)
    print(f"accuracy {ok}/{n} = {ok / n:.1%}; median {statistics.median(secs):.1f} s, mean {statistics.mean(secs):.1f} s a case")


if __name__ == "__main__":
    main()
