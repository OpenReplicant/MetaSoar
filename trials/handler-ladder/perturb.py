"""E-17c: are the ladder's answers robust to changes that keep the answer? (docs/experiments.md)

On the cases among E-17b's 150 fresh ones (stream positions 301 to 450) that a template or handler answered, three
answer-preserving variants of each, routed through the ladder as it stands at the end of E-17b, read-only (a copy of
its state; nothing is learned or saved):
- shuffle: the table's rows in another order
- rename: the first column's labels permuted among themselves, everywhere they occur (table, question, choices,
  and the gold answer when it is one of them), so the problem is the same up to names
- paraphrase: the question reworded by the small model, kept only if every number and every table label it had is
  still there
Each variant is elaborated (its intent), then answered by the cheapest active policy, with the large model on a failed
check, as in the stream. Scored against gold here (gold mapped for renames); the routing never sees gold.

Usage: python3 -I perturb.py [--out results-e17b]   (models as in stream.py; writes perturb.jsonl, summary-e17c.md)
"""
from __future__ import annotations

import argparse, copy, json, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import smoke  # noqa: E402
import stream  # noqa: E402
import summarize  # noqa: E402

KINDS = ("shuffle", "rename", "paraphrase")
PARAPHRASE = ("Reword the problem below so that it asks exactly the same thing in different words. Keep every name "
              "and every number exactly as written. Output only the reworded problem.\n\nProblem: {q}")
NUM = re.compile(r"\d+(?:\.\d+)?")


def split_table(case):
    """-> (header lines, row lines) of the text table, or None if its rows do not line up with table_for_pd."""
    cols = case["table_for_pd"]
    n = len(next(iter(cols.values())))
    lines = case["table"].split("\n")
    if n < 2 or len(lines) - n not in (0, 1):
        return None
    return lines[:len(lines) - n], lines[len(lines) - n:]


def shuffle(case, rng):
    parts = split_table(case)
    if not parts:
        return None
    head, rows = parts
    order = list(range(len(rows)))
    while order == sorted(order):
        rng.shuffle(order)
    v = copy.deepcopy(case)
    v["table"] = "\n".join(head + [rows[i] for i in order])
    v["table_for_pd"] = {k: [col[i] for i in order] for k, col in case["table_for_pd"].items()}
    return v, None


def rename(case, rng):
    """-> (variant, mapping) with the first column's labels permuted (no label kept), or None."""
    parts = split_table(case)
    first = next(iter(case["table_for_pd"]))
    labels = [x.strip() for x in case["table_for_pd"][first]]
    if not parts or len(set(labels)) != len(labels) or any(re.search(r"\d", x) or len(x) < 3 for x in labels):
        return None
    perm = labels[:]
    while any(a == b for a, b in zip(labels, perm)):
        rng.shuffle(perm)
    m = dict(zip(labels, perm))
    rx = re.compile(r"(?<!\w)(" + "|".join(re.escape(x) for x in sorted(labels, key=len, reverse=True)) + r")(?!\w)")
    sub = lambda s: rx.sub(lambda g: m[g.group(1)], s) if s else s
    v = copy.deepcopy(case)
    head, rows = parts
    v["table"] = "\n".join(head + [sub(r.split("|", 1)[0]) + ("|" + r.split("|", 1)[1] if "|" in r else "") for r in rows])
    v["table_for_pd"][first] = [m[x.strip()] for x in case["table_for_pd"][first]]
    v["question"] = sub(case["question"])
    v["choices"] = [sub(c) for c in case["choices"]] if case.get("choices") else case.get("choices")
    return v, m


def paraphrase(case, small):
    text = small.ask(PARAPHRASE.format(q=case["question"]), 300)
    q = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.S).strip().strip('"').strip()
    q = re.sub(r"^(Reworded problem|Problem):\s*", "", q, flags=re.I)
    first = next(iter(case["table_for_pd"]))
    kept = [x.strip() for x in case["table_for_pd"][first] if x.strip() and x.strip() in case["question"]]
    if (not q or q == case["question"] or sorted(NUM.findall(q)) != sorted(NUM.findall(case["question"]))
            or any(x not in q for x in kept)):
        return None
    v = copy.deepcopy(case)
    v["question"] = q
    return v, None


def gold_for(answer, mapping):
    return mapping.get(str(answer).strip(), answer) if mapping else answer


def route(s, case):
    """The ladder on one case, read-only: -> (intent, rung, answer, fallback_from, large calls)."""
    before = s.large.calls
    intent = s.elaborate(case)
    it = s.state["intents"].get(intent)
    if it is None:  # an unknown intent goes to the large model, as in the stream
        text = s.large.ask(smoke.prompt(case), stream.LARGE_TOKENS)
        raw = smoke.extract(text)
        return intent, "large", stream.check(raw, case) or raw or "", None, s.large.calls - before
    rung, answer, fb, _ = s.decide_apply(case, it)
    return intent, rung, answer, fb, s.large.calls - before


def run(out_dir, data_dir, large_fn, small_fn, n=450, start=300, log=print):
    s = stream.Stream(data_dir, out_dir, large_fn, small_fn, n=n, log=lambda *_: None)
    s.save = lambda: None
    s.state = copy.deepcopy(s.state)
    gold = summarize.load(os.path.join(data_dir, "problems_test1k.json"))
    recs = {r["id"]: r for r in s.state["cases"]}
    targets = [c for c in s.cases[start:] if recs[c["id"]]["rung"] != "large"]
    path = os.path.join(out_dir, "perturb.jsonl")
    have = {(r["id"], r["kind"]) for r in summarize.jsonl(path)}
    with open(path, "a") as f:
        for c in targets:
            rng = random.Random(f"{c['id']}")
            for kind in KINDS:
                if (c["id"], kind) in have:
                    continue
                made = {"shuffle": lambda: shuffle(c, rng), "rename": lambda: rename(c, rng),
                        "paraphrase": lambda: paraphrase(c, s.small)}[kind]()
                rec = {"id": c["id"], "kind": kind, "orig_intent": recs[c["id"]]["intent"],
                       "orig_rung": recs[c["id"]]["rung"], "orig_answer": recs[c["id"]]["answer"],
                       "orig_ok": bool(smoke.correct(recs[c["id"]]["answer"], gold[c["id"]]))}
                if made is None:
                    rec["skipped"] = True
                else:
                    v, mapping = made
                    intent, rung, ans, fb, calls = route(s, v)
                    g = dict(gold[c["id"]], answer=gold_for(gold[c["id"]]["answer"], mapping))
                    rec.update(skipped=False, question=v["question"], intent=intent, rung=rung, answer=ans,
                               fallback_from=fb, large_calls=calls, gold=g["answer"], ok=bool(smoke.correct(ans, g)))
                f.write(json.dumps(rec) + "\n")
                f.flush()
                log(f"{c['id']} {kind} {'skipped' if rec['skipped'] else (rec['intent'], rec['rung'], rec['answer'], rec['ok'])}")


def summary(out_dir):
    recs = [r for r in summarize.jsonl(os.path.join(out_dir, "perturb.jsonl")) if not r["skipped"]]
    pct = lambda x: f"{100 * x:.1f}%"
    L = ["# E-17c: answer-preserving perturbations of E-17b's cheaper-rung cases", "",
         "| perturbation | variants | accuracy, original | accuracy, variant | paired difference [95% interval] | same intent | still template or handler | fallbacks |",
         "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    met = []
    for kind in KINDS:
        rs = [r for r in recs if r["kind"] == kind]
        if not rs:
            L.append(f"| {kind} | 0 | | | | | | |")
            continue
        d = [r["ok"] - r["orig_ok"] for r in rs]
        mean, lo, hi = summarize.bootstrap(d)
        met.append(hi < -0.03)
        L.append(f"| {kind} | {len(rs)} | {pct(sum(r['orig_ok'] for r in rs) / len(rs))} | {pct(sum(r['ok'] for r in rs) / len(rs))} | "
                 f"{100 * mean:+.1f} [{100 * lo:+.1f}, {100 * hi:+.1f}] | {pct(sum(r['intent'] == r['orig_intent'] for r in rs) / len(rs))} | "
                 f"{pct(sum(r['rung'] != 'large' for r in rs) / len(rs))} | {sum(bool(r['fallback_from']) for r in rs)} |")
    skipped = [r for r in summarize.jsonl(os.path.join(out_dir, "perturb.jsonl")) if r["skipped"]]
    L += ["", f"Skipped (the perturbation did not apply, or a paraphrase lost a number or label): "
          + ", ".join(f"{k} {sum(r['kind'] == k for r in skipped)}" for k in KINDS), "",
          "## E-17c verdict line", "",
          "- refutation condition met (any perturbation's interval upper end below -3 points): "
          + ("YES" if any(met) else "NO" if len(met) == len(KINDS) else "incomplete"),
          "", "## Wrong on a variant, right on the original", ""]
    L += [f"- {r['id']} {r['kind']}: {r['orig_intent']} -> {r['intent']} by {r['rung']}, {r['answer']!r} (gold {r['gold']!r})"
          for r in recs if r["orig_ok"] and not r["ok"]]
    text = "\n".join(L) + "\n"
    with open(os.path.join(out_dir, "summary-e17c.md"), "w") as f:
        f.write(text)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    stream.add_model_flags(ap)
    ap.set_defaults(out=os.path.join(HERE, "results-e17b"), n=450)
    ap.add_argument("--summary-only", action="store_true")
    a = ap.parse_args()
    if not a.summary_only:
        large, small = stream.build_models(a)
        run(a.out, a.data, large, small, a.n)
    print(summary(a.out))


if __name__ == "__main__":
    main()
