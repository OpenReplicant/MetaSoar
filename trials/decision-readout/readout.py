"""E-04a: read a local model as a decision model on JevBench cases.

For each case, the model gets the question's instructions, the state, and the options labelled A, B, C...,
with `Answer:` prefilled in its reply and thinking off. One token is generated; its top log-probabilities are
renormalised over the option letters. Every case is read twice: options in the case's order and reversed, so
order bias can be measured and averaged out. Output: one JSON line per (case, order), resumable.

Usage: python3 -I readout.py --model fast --port 8082 --out results/lfm3.jsonl [--families 100]
"""
from __future__ import annotations

import argparse, hashlib, json, math, os, string, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "jevbench-ed50fe0", "cases")
SLICES = ["aegis2", "aegis2_response", "atbench500", "jailbreak_classification", "prompt_injections",
          "medmcqa", "medqa_usmle", "mmlu_pro", "pubmedqa", "scienceqa_text"]  # sst5: text withheld; banking77: later
LETTERS = string.ascii_uppercase


def h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:12], 16)


def sample(families_per_slice: int):
    """Deterministic sample: the families with the smallest hash of their id, all their cases."""
    out = []
    for s in SLICES:
        rows = [json.loads(l) for l in open(os.path.join(DATA, f"{s}.jsonl"))]
        fams = sorted({r["family_id"] for r in rows}, key=h)[:families_per_slice]
        keep = set(fams)
        out += [r for r in rows if r["family_id"] in keep]
    return out


def options(case):
    """[(key, text)] in the case's order. noul criteria are {'true':..., 'false':...}."""
    c = case["question"]["criteria"]
    return list(c.items())


def prompt(case, opts):
    q = case["question"]
    lines = [q["instructions"], "", "State:", json.dumps(case["state"], ensure_ascii=False, indent=1), "",
             "Options:"]
    lines += [f"{LETTERS[i]}) {text}" for i, (_, text) in enumerate(opts)]
    lines += ["", "Reply with the letter of one option only."]
    return "\n".join(lines)


def post(port, body, timeout=900):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def read(case, opts, model, port, thinking_off):
    body = {"model": model, "max_tokens": 1, "temperature": 0, "logprobs": True, "top_logprobs": 50,
            "messages": [{"role": "user", "content": prompt(case, opts)},
                         {"role": "assistant", "content": "Answer:"}], **thinking_off}
    t = time.perf_counter()
    d = post(port, body)
    ms = (time.perf_counter() - t) * 1000
    top = d["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
    n = len(opts)
    mass = [0.0] * n
    for x in top:
        tok = x["token"].strip().rstrip(")").rstrip(".")
        if len(tok) == 1 and tok.upper() in LETTERS[:n] and tok.isupper():
            mass[LETTERS.index(tok)] += math.exp(x["logprob"])
    letter_mass = sum(mass)
    floor = math.exp(min(x["logprob"] for x in top)) / 2  # an option outside the top list gets half the smallest
    missing = sum(1 for m in mass if m == 0)
    mass = [m if m > 0 else floor for m in mass]
    z = sum(mass)
    probs = {opts[i][0]: mass[i] / z for i in range(n)}
    return {"probs": probs, "letter_mass": letter_mass, "missing_options": missing,
            "top_token": top[0]["token"], "ms": ms, "prompt_tokens": d.get("usage", {}).get("prompt_tokens")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--families", type=int, default=100)
    ap.add_argument("--thinking-off", default='{"chat_template_kwargs": {"enable_thinking": false}}',
                    help="JSON merged into each request to turn thinking off")
    a = ap.parse_args()
    off = json.loads(a.thinking_off)
    done = set()
    if os.path.exists(a.out):
        done = {(r["case_id"], r["order"]) for r in map(json.loads, open(a.out))}
    cases = sample(a.families)
    todo = [(c, o) for c in cases for o in ("given", "reversed") if (c["case_id"], o) not in done]
    print(f"{len(cases)} cases, {len(todo)} reads to do", flush=True)
    with open(a.out, "a") as f:
        for i, (c, order) in enumerate(todo):
            opts = options(c)
            if order == "reversed":
                opts = opts[::-1]
            try:
                r = read(c, opts, a.model, a.port, off)
            except Exception as e:  # keep going; the scorer counts errors
                r = {"error": repr(e)[:300]}
            r.update({"case_id": c["case_id"], "family_id": c["family_id"], "slice": c["slice"],
                      "task_type": c["task_type"], "perturbation": c["perturbation"], "order": order,
                      "gold": str(c["gold"]).lower() if c["task_type"] == "noul" else c["gold"]})
            f.write(json.dumps(r) + "\n")
            f.flush()
            if i % 100 == 0:
                print(f"{i}/{len(todo)} {c['slice']} {r.get('ms', 0):.0f} ms letter_mass={r.get('letter_mass', 0):.2f}",
                      flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    sys.exit(main())
