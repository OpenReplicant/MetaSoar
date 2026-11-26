"""E-04b: a learned front for the cascade, against d1-2B's own confidence (docs/experiments.md).

A logistic model predicts "d1-2B is wrong" from what is known before escalating. Trained on the `fit` half of every
case d1-2B read (not only Inkling's sample: the label needs d1-2B and the gold answer, nothing else); measured on
`eval`. Two fronts:
  outputs only   d1-2B's probabilities in both orders (scaled confidence, margin, normalised entropy, whether the
                 answer flips with the order, how far the two orders disagree), the number of options, prompt length
  + type         the same, plus the question's type (its slice: in use, the kind of question asked)
Against: 1 - d1-2B's scaled confidence (the threshold of cascade.py), and the oracle.

Measures, on `eval`: AUROC for d1-2B's errors (all of d1-2B's eval cases); and the cascade's accuracy on the cases
Inkling read, at matched escalation rates (the top 30%, 40%, 50% by each score go to Inkling), with a 95% interval
of the difference from the confidence, resampling families.

Usage: python3 -I learned_front.py   (writes results/summary-front.md)
"""
from __future__ import annotations

import json, math, os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import half, load_ours, norm, scale, fit_t  # noqa: E402

RATES = [0.3, 0.4, 0.5]
L2 = 1.0


def top(p):
    return max(p, key=p.get)


def reads(path):
    """case_id -> {order: record}, for cases read in both orders."""
    by = defaultdict(dict)
    for r in map(json.loads, open(path)):
        if "error" not in r:
            by[r["case_id"]][r["order"]] = r
    return {c: d for c, d in by.items() if "given" in d and "reversed" in d}


def solve(a, b):
    """Gaussian elimination with partial pivoting: a x = b."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        for r in range(i + 1, n):
            f = m[r][i] / m[i][i]
            for k in range(i, n + 1):
                m[r][k] -= f * m[i][k]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (m[i][n] - sum(m[i][k] * x[k] for k in range(i + 1, n))) / m[i][i]
    return x


def fit_logistic(X, y, iters=25):
    """L2-penalised logistic regression by Newton's method (the intercept, column 0, unpenalised)."""
    d = len(X[0])
    w = [0.0] * d
    for _ in range(iters):
        g = [L2 * w[j] if j else 0.0 for j in range(d)]
        H = [[(L2 if (i == j and i) else 0.0) for j in range(d)] for i in range(d)]
        for x, t in zip(X, y):
            z = sum(wi * xi for wi, xi in zip(w, x))
            p = 1 / (1 + math.exp(-max(min(z, 30), -30)))
            for i in range(d):
                g[i] += (p - t) * x[i]
                s = p * (1 - p) * x[i]
                for j in range(i, d):
                    H[i][j] += s * x[j]
        for i in range(d):
            for j in range(i):
                H[i][j] = H[j][i]
        step = solve(H, g)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return w


def auroc(scores, labels):
    """Probability that a random positive (d1-2B wrong) scores above a random negative; ties count half."""
    pairs = sorted(zip(scores, labels))
    pos = sum(labels)
    neg = len(labels) - pos
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg = (i + j + 1) / 2
        rank_sum += avg * sum(l for _, l in pairs[i:j])
        i = j
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def main():
    raw = reads(os.path.join(HERE, "results", "d1-2b.jsonl"))
    d1 = load_ours(os.path.join(HERE, "results", "d1-2b.jsonl"))
    ink = load_ours(os.path.join(HERE, "results", "inkling.jsonl"))
    ids = sorted(d1)
    slices = sorted({d1[c]["slice"] for c in ids})
    temps = {s: fit_t([(o["debiased"], o["gold"]) for o in d1.values()
                       if o["slice"] == s and half(o["family"]) == "fit"]) for s in slices}

    wrong, conf, feats = {}, {}, {}
    for c in ids:
        o = d1[c]
        g, v = raw[c]["given"]["probs"], raw[c]["reversed"]["probs"]
        sp = scale(o["debiased"], temps[o["slice"]])
        ps = sorted(sp.values(), reverse=True)
        k = len(sp)
        ent = -sum(p * math.log(max(p, 1e-12)) for p in sp.values()) / math.log(k)
        t = top(o["debiased"])
        wrong[c] = int(t != o["gold"])
        conf[c] = ps[0]
        feats[c] = [ps[0], ps[0] - ps[1], ent, float(o["flip"]), abs(norm(g)[t] - norm(v)[t]),
                    math.log(k), math.log(raw[c]["given"]["prompt_tokens"])]

    fit = [c for c in ids if half(d1[c]["family"]) == "fit"]
    ev = [c for c in ids if half(d1[c]["family"]) == "eval"]
    nnum = len(feats[ids[0]])
    mu = [sum(feats[c][j] for c in fit) / len(fit) for j in range(nnum)]
    sd = [math.sqrt(sum((feats[c][j] - mu[j]) ** 2 for c in fit) / len(fit)) or 1.0 for j in range(nnum)]

    def row(c, typed):
        x = [1.0] + [(feats[c][j] - mu[j]) / sd[j] for j in range(nnum)]
        if typed:
            x += [float(d1[c]["slice"] == s) for s in slices[1:]]
        return x

    def front(typed):
        w = fit_logistic([row(c, typed) for c in fit], [wrong[c] for c in fit])
        return {c: 1 / (1 + math.exp(-sum(a * b for a, b in zip(w, row(c, typed))))) for c in ids}

    scores = {"d1-2B confidence": {c: 1 - conf[c] for c in ids},
              "front, outputs only": front(False),
              "front, + type": front(True)}

    out = ["# E-04b: a learned front for the cascade", "",
           f"Trained on the `fit` half of d1-2B's reads ({len(fit)} cases), measured on `eval` ({len(ev)} cases; "
           f"d1-2B wrong on {sum(wrong[c] for c in ev) / len(ev):.0%}).", "",
           "| Score | AUROC for d1-2B's errors on `eval` | on `fit` |", "|---|---|---|"]
    for name, sc in scores.items():
        out.append(f"| {name} | {auroc([sc[c] for c in ev], [wrong[c] for c in ev]):.3f} | "
                   f"{auroc([sc[c] for c in fit], [wrong[c] for c in fit]):.3f} |")

    # the cascade, on the eval cases Inkling read
    cas = [c for c in ev if c in ink]
    ok1 = {c: 1 - wrong[c] for c in cas}
    ok2 = {c: int(top(ink[c]["debiased"]) == ink[c]["gold"]) for c in cas}
    secs = {c: (2 * d1[c]["ms"], 2 * ink[c]["ms"]) for c in cas}
    fams = defaultdict(list)
    for c in cas:
        fams[d1[c]["family"]].append(c)
    keys = sorted(fams)

    def escalated(sc, rate):
        ranked = sorted(cas, key=lambda c: sc[c], reverse=True)
        return set(ranked[:round(rate * len(cas))])

    def acc(esc, cs):
        return sum(ok2[c] if c in esc else ok1[c] for c in cs) / len(cs)

    def diff_ci(esc_a, esc_b, reps=2000):
        rnd = random.Random(0)
        ds = []
        for _ in range(reps):
            cs = [c for k in rnd.choices(keys, k=len(keys)) for c in fams[k]]
            ds.append(acc(esc_a, cs) - acc(esc_b, cs))
        ds.sort()
        return ds[int(0.025 * reps)], ds[int(0.975 * reps) - 1]

    ink_acc = sum(ok2.values()) / len(cas)
    out += ["", f"The cascade on the {len(cas)} `eval` cases Inkling read (Inkling alone {ink_acc:.3f}, d1-2B alone "
            f"{sum(ok1.values()) / len(cas):.3f}). The top share by each score goes to Inkling.", "",
            "| Sent to Inkling | Score | Accuracy | Against the confidence [95% CI] | Mean s per decision |",
            "|---|---|---|---|---|"]
    oracle = {c: float(not ok1[c]) for c in cas}
    for rate in RATES:
        base = escalated(scores["d1-2B confidence"], rate)
        for name, sc in list(scores.items()) + [("oracle", oracle)]:
            esc = escalated(sc, rate)
            lo, hi = diff_ci(esc, base)
            s = sum(secs[c][0] + (secs[c][1] if c in esc else 0) for c in cas) / len(cas) / 1000
            d = "" if name == "d1-2B confidence" else f"{acc(esc, cas) - acc(base, cas):+.3f} [{lo:+.3f}, {hi:+.3f}]"
            out.append(f"| {rate:.0%} | {name} | {acc(esc, cas):.3f} | {d} | {s:.2f} |")

    # Exploratory, not registered: rank by expected gain, P(Inkling right | type) - d1-2B's confidence, with
    # P(Inkling right | type) from the fit cases Inkling read (Laplace-smoothed). A gate should send what escalation
    # helps, not only what the first stage gets wrong.
    fit_ink = [c for c in fit if c in ink]
    pink = {}
    for s in slices:
        cs = [c for c in fit_ink if d1[c]["slice"] == s]
        pink[s] = (sum(top(ink[c]["debiased"]) == ink[c]["gold"] for c in cs) + 1) / (len(cs) + 2)
    gain = {c: pink[d1[c]["slice"]] - conf[c] for c in cas}
    out += ["", "Exploratory (not registered): ranked by expected gain, P(Inkling right | type) from `fit` minus "
            "d1-2B's confidence.", "",
            "| Sent to Inkling | By confidence | By expected gain | Against the confidence [95% CI] |",
            "|---|---|---|---|"]
    for rate in RATES + [0.6]:
        base, esc = escalated(scores["d1-2B confidence"], rate), escalated(gain, rate)
        lo, hi = diff_ci(esc, base)
        out.append(f"| {rate:.0%} | {acc(base, cas):.3f} | {acc(esc, cas):.3f} | "
                   f"{acc(esc, cas) - acc(base, cas):+.3f} [{lo:+.3f}, {hi:+.3f}] |")
    pos = {c for c in cas if gain[c] > 0}
    lo, hi = diff_ci(pos, set(cas))
    out.append(f"| {len(pos) / len(cas):.0%} (where expected gain > 0) | | {acc(pos, cas):.3f} | "
               f"against Inkling alone {acc(pos, cas) - ink_acc:+.3f} [{lo:+.3f}, {hi:+.3f}] |")

    text = "\n".join(out) + "\n"
    open(os.path.join(HERE, "results", "summary-front.md"), "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
