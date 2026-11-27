"""E-04a follow-up: a cascade, d1-2B first and Inkling when d1-2B is unsure.

Offline, on the reads already in results/ (no model is run). Only cases read by both models are used: Inkling's
sample of 1,400 cases, split into `fit` and `eval` by family as in score.py. Every choice (temperatures, thresholds,
which slices skip d1-2B) is made on `fit`; everything reported is measured on `eval`.

Both models are read debiased (the mean of the two option orders), so a decision costs two reads of each model it
reaches. Cost is the measured wall time of those reads, per case.

Policies:
  d1-2B alone, Inkling alone       the two ends
  threshold                        escalate when d1-2B's confidence (temperature-scaled per slice) is below t;
                                   t is the lowest escalation rate whose `fit` accuracy is within 1 point of Inkling's
  routed + threshold               as above, but a slice goes straight to Inkling when d1-2B's `fit` accuracy there is
                                   more than 10 points below Inkling's
  oracle                           escalate exactly when d1-2B is wrong (an upper bound, not a policy)

Usage: python3 -I cascade.py   (writes results/summary-cascade.md)
"""
from __future__ import annotations

import os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import half, load_ours, scale, fit_t, load_ref  # noqa: E402

TOL = 0.01      # how far below Inkling's fit accuracy a threshold may land
ROUTE_GAP = 0.10  # d1-2B this far below Inkling on a slice's fit half: skip d1-2B there


def top(p):
    return max(p, key=p.get)


def main():
    d1 = load_ours(os.path.join(HERE, "results", "d1-2b.jsonl"))
    ink = load_ours(os.path.join(HERE, "results", "inkling.jsonl"))
    jev = load_ref("jev-1.13.0")
    ids = sorted(c for c in ink if c in d1)
    fit = [c for c in ids if half(ink[c]["family"]) == "fit"]
    ev = [c for c in ids if half(ink[c]["family"]) == "eval"]
    slices = sorted({ink[c]["slice"] for c in ids})

    # d1-2B temperature per slice, fitted on fit (on all of d1-2B's fit cases in the slice, not only Inkling's)
    temps = {s: fit_t([(o["debiased"], o["gold"]) for o in d1.values()
                       if o["slice"] == s and half(o["family"]) == "fit"]) for s in slices}
    conf = {c: max(scale(d1[c]["debiased"], temps[d1[c]["slice"]]).values()) for c in ids}
    ok1 = {c: top(d1[c]["debiased"]) == d1[c]["gold"] for c in ids}
    ok2 = {c: top(ink[c]["debiased"]) == ink[c]["gold"] for c in ids}
    cost1 = {c: 2 * d1[c]["ms"] / 1000 for c in ids}
    cost2 = {c: 2 * ink[c]["ms"] / 1000 for c in ids}

    def run(cases, esc):
        """esc: case -> bool. Returns accuracy, escalation rate, mean and median seconds per decision."""
        oks, secs = [], []
        for c in cases:
            e = esc(c)
            to_ink = e is None or e
            oks.append(ok2[c] if to_ink else ok1[c])
            secs.append((0 if e is None else cost1[c]) + (cost2[c] if to_ink else 0))
        secs_sorted = sorted(secs)
        n = len(cases)
        return {"acc": sum(oks) / n, "esc": sum(esc(c) is None or bool(esc(c)) for c in cases) / n,
                "mean_s": sum(secs) / n, "median_s": secs_sorted[n // 2]}

    # e(c) is True (escalate after d1-2B), False (stop at d1-2B) or None (straight to Inkling, d1-2B not run)
    ink_fit = run(fit, lambda c: None)["acc"]
    grid = sorted({round(x, 4) for x in [conf[c] for c in fit]} | {0.0, 1.01})

    def pick(route):
        def esc_for(t):
            return lambda c: None if ink[c]["slice"] in route else conf[c] < t
        best = None
        for t in grid:
            r = run(fit, esc_for(t))
            if r["acc"] >= ink_fit - TOL and (best is None or r["esc"] < best[1]["esc"]):
                best = (t, r)
        return best[0], esc_for(best[0])

    acc_by = lambda cases, ok: sum(ok[c] for c in cases) / max(len(cases), 1)
    route = {s for s in slices if acc_by([c for c in fit if ink[c]["slice"] == s], ok1)
             < acc_by([c for c in fit if ink[c]["slice"] == s], ok2) - ROUTE_GAP}
    t_thr, esc_thr = pick(set())
    t_rt, esc_rt = pick(route)

    policies = [
        ("d1-2B alone", lambda c: False),
        ("Inkling alone", lambda c: None),
        (f"threshold (t = {t_thr:.3f})", esc_thr),
        (f"routed + threshold (t = {t_rt:.3f})", esc_rt),
        ("oracle", lambda c: not ok1[c]),
    ]

    fams = defaultdict(list)
    for c in ev:
        fams[ink[c]["family"]].append(c)
    keys = sorted(fams)

    def diff_ci(esc, reps=2000):
        """95% interval of (policy accuracy - Inkling accuracy) on eval, resampling families."""
        rnd = random.Random(0)
        ds = []
        for _ in range(reps):
            cs = [c for k in rnd.choices(keys, k=len(keys)) for c in fams[k]]
            ds.append(sum((ok2[c] if (esc(c) is None or esc(c)) else ok1[c]) - ok2[c] for c in cs) / len(cs))
        ds.sort()
        return ds[int(0.025 * reps)], ds[int(0.975 * reps) - 1]

    jev_ev = [c for c in ev if c in jev]
    jev_acc = sum(top(jev[c]["p"]) == jev[c]["gold"] for c in jev_ev) / len(jev_ev)

    out = ["# E-04a cascade: d1-2B first, Inkling when unsure", "",
           f"Offline, on the {len(ids)} cases both models read; choices made on `fit` ({len(fit)} cases), "
           f"measured on `eval` ({len(ev)} cases).",
           f"Slices routed straight to Inkling (d1-2B more than {ROUTE_GAP:.0%} below it on `fit`): "
           f"{', '.join(sorted(route)) or 'none'}.", "",
           "| Policy | Accuracy | Against Inkling alone [95% CI] | Sent to Inkling | Mean s per decision | Median s |",
           "|---|---|---|---|---|---|"]
    for name, esc in policies:
        r = run(ev, esc)
        lo, hi = diff_ci(esc)
        out.append(f"| {name} | {r['acc']:.3f} | {r['acc'] - run(ev, lambda c: None)['acc']:+.3f} "
                   f"[{lo:+.3f}, {hi:+.3f}] | {r['esc']:.0%} | {r['mean_s']:.2f} | {r['median_s']:.2f} |")
    out.append(f"| Jev 1.13 (reference) | {jev_acc:.3f} | | | | |")

    out += ["", "Threshold sweep on `eval` (no routing), for the shape of the trade-off:", "",
            "| t | Sent to Inkling | Accuracy | Mean s per decision |", "|---|---|---|---|"]
    for t in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]:
        r = run(ev, lambda c: conf[c] < t)
        out.append(f"| {t} | {r['esc']:.0%} | {r['acc']:.3f} | {r['mean_s']:.2f} |")

    out += ["", "Per slice on `eval`, routed + threshold policy:", "",
            "| slice | n | d1-2B | Inkling | cascade | sent to Inkling |", "|---|---|---|---|---|---|"]
    for s in slices:
        cs = [c for c in ev if ink[c]["slice"] == s]
        r = run(cs, esc_rt)
        out.append(f"| {s} | {len(cs)} | {acc_by(cs, ok1):.3f} | {acc_by(cs, ok2):.3f} | {r['acc']:.3f} | "
                   f"{r['esc']:.0%} |")

    text = "\n".join(out) + "\n"
    open(os.path.join(HERE, "results", "summary-cascade.md"), "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
