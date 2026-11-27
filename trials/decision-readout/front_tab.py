"""E-04c: a tabular foundation model as the escalation gate, with and without question embeddings
(docs/experiments.md).

The gate ranks cases by expected gain, P(Inkling right | x) - P(d1-2B right | x). Each learner fits two binary models
on the `fit` cases both models read; everything is measured on the `eval` cases both read. Learners:
  logistic    scikit-learn's L2 logistic regression, features standardised on `fit` (the registered baseline)
  TabICL      in-context, untuned (soda-inria/tabicl, BSD-3), on the CPU
Features:
  F           E-04b's: d1-2B's scaled confidence, margin, entropy, order flip, order disagreement, log options,
              log prompt tokens; plus the question's type (its slice), one-hot
  F + E       the same, plus 32 principal components of the question's embedding (Qwen3-Embedding-0.6B,
              `embed.py`), the components fitted on `fit`
Reported against the logistic gate on the same features, at matched escalation rates and at "escalate where the
expected gain is positive", with a 95% interval resampling families.

Usage: <venv>/bin/python -I front_tab.py   (needs numpy, scikit-learn, tabicl; writes results/summary-tab.md)
"""
from __future__ import annotations

import json, os, random, sys, time
from collections import defaultdict

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from learned_front import data, top  # noqa: E402

RATES = [0.5, 0.6, 0.63]
NPC = 32


def main():
    D = data()
    d1, ink, slices, conf, feats = D["d1"], D["ink"], D["slices"], D["conf"], D["feats"]
    emb = {r["case_id"]: r["v"] for r in map(json.loads, open(os.path.join(HERE, "results", "embed-qwen3-0.6b.jsonl")))}
    fit = [c for c in D["fit"] if c in ink and c in emb]
    ev = [c for c in D["ev"] if c in ink and c in emb]
    ok1 = {c: int(top(d1[c]["debiased"]) == d1[c]["gold"]) for c in fit + ev}
    ok2 = {c: int(top(ink[c]["debiased"]) == ink[c]["gold"]) for c in fit + ev}

    def F(cs):
        return np.array([feats[c] + [float(d1[c]["slice"] == s) for s in slices] for c in cs])

    pca = PCA(n_components=NPC, random_state=0).fit(np.array([emb[c] for c in fit]))

    def FE(cs):
        return np.hstack([F(cs), pca.transform(np.array([emb[c] for c in cs]))])

    def logistic(Xf, y, Xe):
        sc = StandardScaler().fit(Xf)
        m = LogisticRegression(C=1.0, max_iter=5000).fit(sc.transform(Xf), y)
        return m.predict_proba(sc.transform(Xe))[:, 1]

    def tabicl(Xf, y, Xe):
        from tabicl import TabICLClassifier
        m = TabICLClassifier(device="cpu", random_state=0).fit(Xf, y)
        return m.predict_proba(Xe)[:, list(m.classes_).index(1)]

    yi = np.array([ok2[c] for c in fit])
    yd = np.array([ok1[c] for c in fit])
    gains, secs = {}, {}
    for fname, fx in (("F", F), ("F + E", FE)):
        Xf, Xe = fx(fit), fx(ev)
        for lname, learn in (("logistic", logistic), ("TabICL", tabicl)):
            t = time.perf_counter()
            g = learn(Xf, yi, Xe) - learn(Xf, yd, Xe)
            secs[(lname, fname)] = time.perf_counter() - t
            gains[(lname, fname)] = dict(zip(ev, g))
    # E-04b's exploratory gate, for reference: Inkling's fit record by type minus d1-2B's confidence
    pink = {s: (sum(ok2[c] for c in fit if d1[c]["slice"] == s) + 1) / (sum(d1[c]["slice"] == s for c in fit) + 2)
            for s in slices}
    gains[("table by type", "-")] = {c: pink[d1[c]["slice"]] - conf[c] for c in ev}
    gains[("confidence", "-")] = {c: -conf[c] for c in ev}

    fams = defaultdict(list)
    for c in ev:
        fams[d1[c]["family"]].append(c)
    keys = sorted(fams)

    def acc(esc, cs):
        return sum(ok2[c] if c in esc else ok1[c] for c in cs) / len(cs)

    def ci(esc_a, esc_b, reps=2000):
        rnd = random.Random(0)
        ds = sorted(acc(esc_a, cs) - acc(esc_b, cs)
                    for cs in ([c for k in rnd.choices(keys, k=len(keys)) for c in fams[k]] for _ in range(reps)))
        return ds[int(0.025 * reps)], ds[int(0.975 * reps) - 1]

    def at_rate(g, rate):
        return set(sorted(ev, key=lambda c: g[c], reverse=True)[:round(rate * len(ev))])

    ink_acc = sum(ok2[c] for c in ev) / len(ev)
    out = ["# E-04c: a tabular foundation model as the escalation gate", "",
           f"Gate: rank by P(Inkling right) - P(d1-2B right). Fitted on {len(fit)} `fit` cases, measured on "
           f"{len(ev)} `eval` cases (Inkling alone {ink_acc:.3f}, d1-2B alone "
           f"{sum(ok1[c] for c in ev) / len(ev):.3f}). Differences are against the logistic gate on the same "
           "features, with 95% intervals resampling families.", "",
           "| Gate | Features | " + " | ".join(f"{r:.0%} sent" for r in RATES) +
           " | Where gain > 0: sent, accuracy, against Inkling alone | Fit and predict s |",
           "|---|---|" + "---|" * len(RATES) + "---|---|"]
    for (lname, fname), g in gains.items():
        ref = gains.get(("logistic", fname)) if lname == "TabICL" else None
        cells = []
        for r in RATES:
            e = at_rate(g, r)
            s = f"{acc(e, ev):.3f}"
            if ref is not None:
                lo, hi = ci(e, at_rate(ref, r))
                s += f" ({acc(e, ev) - acc(at_rate(ref, r), ev):+.3f} [{lo:+.3f}, {hi:+.3f}])"
            cells.append(s)
        if lname == "confidence":
            pos = ""
        else:
            e = {c for c in ev if g[c] > 0}
            lo, hi = ci(e, set(ev))
            pos = f"{len(e) / len(ev):.0%}, {acc(e, ev):.3f}, {acc(e, ev) - ink_acc:+.3f} [{lo:+.3f}, {hi:+.3f}]"
        out.append(f"| {lname} | {fname} | " + " | ".join(cells) + f" | {pos} | "
                   f"{secs.get((lname, fname), 0):.1f} |")
    out += ["", f"Embedding: Qwen3-Embedding-0.6B Q8_0 (revision 370f27d), {NPC} components explain "
            f"{pca.explained_variance_ratio_.sum():.0%} of its variance on `fit`."]
    from importlib.metadata import version
    out.append(f"TabICL {version('tabicl')} (checkpoint tabicl-classifier-v2-20260212, jingang/TabICL, BSD-3), "
               f"scikit-learn {version('scikit-learn')}, random_state 0, CPU.")
    text = "\n".join(out) + "\n"
    open(os.path.join(HERE, "results", "summary-tab.md"), "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
