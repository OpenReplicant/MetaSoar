"""E-17 first step: the large model alone on TabMWP, for accuracy and speed (docs/experiments.md).

Inkling (`../decision-readout/serve.sh slow`, :8081) is asked to work the problem briefly and end with
"Answer: <answer>". Scored with TabMWP's own normalisation in spirit: numbers compared as numbers (commas, $ and
units stripped), text compared case-folded; for multiple choice, the answer must be one of the choices.

Usage: python3 -I smoke.py [N] [SPLIT]   (default 20 cases of dev1k; writes results/smoke-<split>.jsonl)
"""
from __future__ import annotations

import json, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "tabmwp-5a1a522")
PORT = 8081


def prompt(p):
    lines = []
    if p.get("table_title"):
        lines.append(f"Table: {p['table_title']}")
    lines += [p["table"], "", p["question"]]
    if p.get("choices"):
        lines.append("Choices: " + "; ".join(p["choices"]))
    if p.get("unit"):
        lines.append(f"(Unit: {p['unit']})")
    lines += ["", "Work it out briefly, then end with one line: Answer: <the answer only>"]
    return "\n".join(lines)


def ask(text, max_tokens=700):
    body = {"model": "slow", "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens,
            "temperature": 0, "reasoning_effort": "none"}
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"] or "", d.get("usage", {})


def number(s):
    s = s.replace(",", "").replace("$", "").strip()
    m = re.search(r"-?\d+(\.\d+)?(/\d+)?", s)
    if not m:
        return None
    t = m.group(0)
    if "/" in t:
        a, b = t.split("/")
        return float(a) / float(b) if float(b) else None
    return float(t)


def correct(pred, p):
    if pred is None:
        return False
    gold = str(p["answer"]).strip()
    if p["ans_type"] in ("integer_number", "decimal_number"):
        a, b = number(pred), number(gold)
        return a is not None and b is not None and abs(a - b) < 1e-6 * max(1, abs(b)) + 1e-9
    return pred.strip().strip(".").lower() == gold.lower()


def extract(text):
    m = re.findall(r"Answer:\s*(.+)", text)
    return m[-1].strip().strip("*").strip() if m else None


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    split = sys.argv[2] if len(sys.argv) > 2 else "dev1k"
    probs = json.load(open(os.path.join(DATA, f"problems_{split}.json")))
    ids = sorted(probs)[:n]
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    out = os.path.join(HERE, "results", f"smoke-{split}.jsonl")
    ok = 0
    with open(out, "w") as f:
        for i, pid in enumerate(ids):
            p = probs[pid]
            t = time.perf_counter()
            text, usage = ask(prompt(p))
            s = time.perf_counter() - t
            pred = extract(text)
            c = correct(pred, p)
            ok += c
            f.write(json.dumps({"pid": pid, "pred": pred, "gold": p["answer"], "ok": c, "s": s,
                                "out_tokens": usage.get("completion_tokens"), "ans_type": p["ans_type"],
                                "text": text}) + "\n")
            f.flush()
            print(f"{i + 1}/{n} ok={c} {s:.1f}s tokens={usage.get('completion_tokens')} pred={pred!r} gold={p['answer']!r}",
                  flush=True)
    print(f"accuracy {ok}/{n}")


if __name__ == "__main__":
    main()
