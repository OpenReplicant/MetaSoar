"""E-17 follow-up, offline: d1-2B as the intent elaborator, against LFM3's keys from the stream.

The 300 stream questions are replayed in order. Each is matched to the known intents: a shortlist of the K nearest
by embedding (Qwen3-Embedding-0.6B, the largest cosine to any earlier question of the intent), then d1-2B chooses
among the shortlist and "none of these" (a typed question on llama.cpp's /v1/systemone; each option is the intent's
first question). "None", or a top probability under t, starts a new intent. Naming is not tested, only grouping.

Reference grouping (a proxy; TabMWP does not label its templates): the operation the question asks for, by the
ordered rules in RULES, written from the stream's own question sentences. Measures, against it: number of groups, groups seen once, purity (the share of cases in
their group's majority reference intent: 1 - misroutes), inverse purity (the share of each reference intent in its
largest group: 1 - fragmentation), and pairwise F1 (pairs of cases grouped together in both).

Serving: `../decision-readout/serve.sh embed` (:8084) and `serve.sh d1 d1-2B-GGUF/d1-2B-Q8_0.gguf` (:8083).
Usage: python3 -I d1_intent.py   (writes results/summary-d1-intent.md)
"""
from __future__ import annotations

import json, math, os, re, sys, urllib.request
from collections import Counter, defaultdict
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stream  # noqa: E402

K = 6
THRESHOLDS = [0.3, 0.5, 0.7]
INSTRUCT = "Given a math word problem about a table, represent the kind of computation it asks for"
D1_INSTRUCTIONS = ("The state holds a math word problem about a table. Which option's example problem asks for the same "
                   "kind of computation (the same operation on a table), whatever its topic, names or numbers? Choose "
                   "\"none\" if no option asks for the same kind of computation.")


def post(port, path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def embed(texts):
    d = post(8084, "/v1/embeddings", {"input": [f"Instruct: {INSTRUCT}\nQuery:{t}" for t in texts], "model": "embed"})
    return [x["embedding"] for x in sorted(d["data"], key=lambda x: x["index"])]


def d1_choose(question, options):
    """options: {key: example question}; -> {key: probability}, 'none' among the keys."""
    crit = dict(options, none="None of these: a different kind of computation")
    d = post(8083, "/v1/systemone", {"state": {"question": question},
                                     "questions": {"q": {"type": "choice", "instructions": D1_INSTRUCTIONS,
                                                         "criteria": crit}}})
    return {k: float(v) for k, v in d["answers"]["q"]["probabilities"].items()}


RULES = [  # the operation a question asks for, first match wins; written from the stream's question sentences
    ("rate_of_change", r"rate of change"), ("mean", r"\bmean of\b"), ("median", r"\bmedian of\b"),
    ("mode", r"\bmode of\b"), ("range", r"\brange of\b"), ("function", r"linear or nonlinear|relation a function"),
    ("shortage_surplus", r"shortage or a surplus"), ("fraction", r"fraction|simplify your answer|probability"),
    ("enough_money", r"have enough"), ("money_left", r"have left"),
    ("price_difference", r"how much more does .* cost than|charges more"),
    ("money_needed", r"need to buy|would it cost to buy|total cost for"),
    ("total_spent", r"did (she|he|they) spend|\btotal cost\b"),
    ("count_condition", r"how many .*(at least|fewer than|more than|exactly|less than|greater than) ?\d"),
    ("difference_counts", r"how many (more|fewer)\b.* than|how much more\b.* than"),
    ("extreme_value", r"is the (largest|smallest|highest|lowest|greatest|least) "),
    ("extreme_item", r"\b(most|fewest|lowest|highest|least|largest|smallest)\b"),
    ("schedule", r"when does|what time|how long does it take|does the .* (begin|end|depart|leave|arrive)"),
    ("lookup", r"how much did .* cost in|per capita|per square mile|how much money was raised|how many .* in stock"),
    ("multiply_groups", r"how many .* are (on|in) \d+ "),
    ("total", r"in all\b|how many .* did .* and .*\?|gross income|how much money did .* make"),
]


def reference(q):
    t = q.lower()
    return next((name for name, rx in RULES if re.search(rx, t)), "other")

def scores(groups, ref):
    """groups, ref: case id -> label."""
    ids = list(groups)
    by_g, by_r = defaultdict(list), defaultdict(list)
    for i in ids:
        by_g[groups[i]].append(i); by_r[ref[i]].append(i)
    purity = sum(Counter(ref[i] for i in m).most_common(1)[0][1] for m in by_g.values()) / len(ids)
    inverse = sum(Counter(groups[i] for i in m).most_common(1)[0][1] for m in by_r.values()) / len(ids)
    same_g = {p for m in by_g.values() for p in combinations(sorted(m), 2)}
    same_r = {p for m in by_r.values() for p in combinations(sorted(m), 2)}
    tp = len(same_g & same_r)
    prec, rec = tp / max(1, len(same_g)), tp / max(1, len(same_r))
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    return {"groups": len(by_g), "singletons": sum(len(m) == 1 for m in by_g.values()), "purity": purity,
            "inverse purity": inverse, "pairwise F1": f1}


def main():
    cases = stream.load_cases()
    st = json.load(open(os.path.join(HERE, "results", "state.json")))
    lfm3 = {r["id"]: r["intent"] for r in st["cases"]}
    ref = {c["id"]: reference(c["question"]) for c in cases}
    vec = {}
    for i in range(0, len(cases), 16):
        b = cases[i:i + 16]
        for c, v in zip(b, embed([c["question"] for c in b])):
            vec[c["id"]] = v
    cos = lambda a, b: sum(x * y for x, y in zip(a, b))  # the embeddings are unit vectors

    # d1-2B's probabilities depend only on the shortlist, which depends on earlier groupings, so each threshold
    # is its own replay
    runs = {}
    for t in THRESHOLDS:
        groups, members, first = {}, defaultdict(list), {}
        for c in cases:
            near = sorted(members, key=lambda g: -max(cos(vec[c["id"]], vec[m]) for m in members[g]))[:K]
            g = None
            if near:
                p = d1_choose(c["question"], {f"o{j}": first[gg] for j, gg in enumerate(near)})
                best = max(p, key=p.get)
                if best != "none" and p[best] >= t:
                    g = near[int(best[1:])]
            if g is None:
                g = f"g{len(members)}"
                first[g] = c["question"]
            groups[c["id"]] = g
            members[g].append(c["id"])
        runs[t] = groups
        print(t, scores(groups, ref), flush=True)

    rows = [("reference (operation rules)", scores(ref, ref)), ("LFM3 keys (the stream)", scores(lfm3, ref))]
    rows += [(f"embedding shortlist + d1-2B, t = {t}", scores(g, ref)) for t, g in runs.items()]
    out = ["# d1-2B as the intent elaborator (offline, the E-17 stream's 300 questions)", "",
           "| Grouping | Groups | Seen once | Purity (1 - misroutes) | Inverse purity (1 - fragmentation) | Pairwise F1 |",
           "|---|---|---|---|---|---|"]
    for name, s in rows:
        out.append(f"| {name} | {s['groups']} | {s['singletons']} | {s['purity']:.3f} | {s['inverse purity']:.3f} | "
                   f"{s['pairwise F1']:.3f} |")
    text = "\n".join(out) + "\n"
    open(os.path.join(HERE, "results", "summary-d1-intent.md"), "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
