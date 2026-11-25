"""E-04a scorer: our readouts against Jev, djev and Laya on the same cases.

Families are split in two by a hash of the family id: `fit` (temperature and threshold chosen there) and `eval`
(everything reported is measured there). Our model is scored three ways:
  raw       options in the case's order, as read
  debiased  the mean of the two reads (case's order and reversed), mapped back to option keys
  scaled    debiased, then one temperature per slice fitted on `fit` by log-loss
The reference systems are scored as shipped. Coverage at 5% risk: the confidence threshold is the lowest one whose
error rate on `fit` is at most 5%; coverage and realised risk are then measured on `eval`.

Usage: python3 -I score.py results/lfm3.jsonl [results/inkling.jsonl ...]  (writes results/summary.md)
"""
from __future__ import annotations

import hashlib, json, math, os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PRED = os.path.join(HERE, "..", "data", "jevbench-ed50fe0", "predictions")
REFS = {"Jev 1.13": "jev-1.13.0", "djev 0.1": "djev-0.1", "Laya 421M": "laya-421m-en"}


def half(family_id: str) -> str:
    return "fit" if int(hashlib.sha256(family_id.encode()).hexdigest()[:8], 16) % 2 == 0 else "eval"


def norm(p):
    z = sum(p.values())
    return {k: v / z for k, v in p.items()} if z > 0 else {k: 1 / len(p) for k in p}


def scale(p, t):
    lg = {k: math.log(max(v, 1e-12)) / t for k, v in p.items()}
    m = max(lg.values())
    return norm({k: math.exp(v - m) for k, v in lg.items()})


def load_ours(path):
    """case_id -> {raw, debiased, gold, slice, family, flip, letter_mass}"""
    by = defaultdict(dict)
    meta = {}
    for r in map(json.loads, open(path)):
        if "error" in r:
            continue
        by[r["case_id"]][r["order"]] = r
        meta[r["case_id"]] = r
    out = {}
    for cid, d in by.items():
        if "given" not in d or "reversed" not in d:
            continue
        g, v = d["given"]["probs"], d["reversed"]["probs"]
        deb = norm({k: (g[k] + v[k]) / 2 for k in g})
        m = meta[cid]
        out[cid] = {"raw": g, "debiased": deb, "gold": m["gold"], "slice": m["slice"], "family": m["family_id"],
                    "flip": max(g, key=g.get) != max(v, key=v.get),
                    "letter_mass": (d["given"]["letter_mass"] + d["reversed"]["letter_mass"]) / 2,
                    "ms": (d["given"]["ms"] + d["reversed"]["ms"]) / 2}
    return out


def load_ref(name):
    out = {}
    for r in map(json.loads, open(os.path.join(PRED, name, "predictions.jsonl"))):
        if r.get("error"):
            continue
        if r["task_type"] == "noul":
            p = {"true": r["p_true"], "false": 1 - r["p_true"]}
            gold = str(r["gold"]).lower()
        else:
            p, gold = r["probabilities"], r["gold"]
        out[r["case_id"]] = {"p": norm(p), "gold": gold}
    return out


def metrics(items, thr=None):
    """items: [(probs, gold)] -> accuracy, brier, ece, nll"""
    n = len(items)
    if n == 0:
        return {}
    acc = brier = nll = 0.0
    bins = defaultdict(lambda: [0, 0.0, 0.0])
    for p, gold in items:
        top = max(p, key=p.get)
        c = p[top]
        ok = top == gold
        acc += ok
        brier += sum((v - (k == gold)) ** 2 for k, v in p.items())
        nll += -math.log(max(p.get(gold, 0), 1e-12))
        b = bins[min(int(c * 10), 9)]
        b[0] += 1; b[1] += ok; b[2] += c
    ece = sum(abs(b[1] - b[2]) for b in bins.values()) / n
    return {"n": n, "acc": acc / n, "brier": brier / n, "ece": ece, "nll": nll / n}


def threshold(items, risk=0.05):
    """Lowest confidence threshold whose error among accepted items is <= risk (on fit)."""
    s = sorted(((max(p.values()), max(p, key=p.get) == g) for p, g in items), reverse=True)
    best, err = None, 0
    for i, (c, ok) in enumerate(s, 1):
        err += not ok
        if err / i <= risk:
            best = c
    return best if best is not None else 1.01


def coverage(items, thr):
    acc = [(max(p, key=p.get) == g) for p, g in items if max(p.values()) >= thr]
    return (len(acc) / len(items) if items else 0, (1 - sum(acc) / len(acc)) if acc else None)


def fit_t(items):
    best = (1e9, 1.0)
    for t in [x / 20 for x in range(4, 101)] + [x / 2 for x in range(11, 61)]:
        l = sum(-math.log(max(scale(p, t).get(g, 0), 1e-12)) for p, g in items)
        best = min(best, (l, t))
    return best[1]


def main(paths):
    refs = {k: load_ref(v) for k, v in REFS.items()}
    rows = []
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        ours = load_ours(path)
        slices = sorted({o["slice"] for o in ours.values()})
        for s in slices + ["ALL"]:
            ids = [c for c, o in ours.items() if s in ("ALL", o["slice"])]
            fit = [c for c in ids if half(ours[c]["family"]) == "fit"]
            ev = [c for c in ids if half(ours[c]["family"]) == "eval"]

            def report(label, get, fit_ids, ev_ids):
                fi = [get(c) for c in fit_ids]
                ei = [get(c) for c in ev_ids]
                m = metrics(ei)
                thr = threshold(fi)
                cov, risk = coverage(ei, thr)
                m.update({"cov5": cov, "risk": risk, "acc_ci": boot_acc(ev_ids, get)})
                rows.append((name, s, label, m))

            def boot_acc(ev_ids, get, reps=1000):
                """95% interval of accuracy, resampling families (cases of one family move together)."""
                fams = defaultdict(list)
                for c in ev_ids:
                    fams[ours[c]["family"]].append(c)
                keys = list(fams)
                if not keys:
                    return None
                rnd = random.Random(0)
                accs = []
                for _ in range(reps):
                    ids = [c for k in rnd.choices(keys, k=len(keys)) for c in fams[k]]
                    accs.append(sum(max(get(c)[0], key=get(c)[0].get) == get(c)[1] for c in ids) / len(ids))
                accs.sort()
                return accs[int(0.025 * reps)], accs[int(0.975 * reps) - 1]

            report("raw", lambda c: (ours[c]["raw"], ours[c]["gold"]), fit, ev)
            report("debiased", lambda c: (ours[c]["debiased"], ours[c]["gold"]), fit, ev)
            # one temperature per slice (for ALL: per slice too, then pooled)
            temps = {}
            for sl in ({ours[c]["slice"] for c in ids}):
                temps[sl] = fit_t([(ours[c]["debiased"], ours[c]["gold"]) for c in fit if ours[c]["slice"] == sl])
            report("scaled", lambda c: (scale(ours[c]["debiased"], temps[ours[c]["slice"]]), ours[c]["gold"]), fit, ev)
            for rn, ref in refs.items():
                ok = [c for c in ev if c in ref]
                okf = [c for c in fit if c in ref]
                report(rn, lambda c: (ref[c]["p"], ref[c]["gold"]), okf, ok)
            flips = sum(ours[c]["flip"] for c in ev) / max(len(ev), 1)
            mass = sum(ours[c]["letter_mass"] for c in ev) / max(len(ev), 1)
            ms = sorted(ours[c]["ms"] for c in ev)
            rows.append((name, s, "_diag", {"flip": flips, "letter_mass": mass,
                                            "median_ms": ms[len(ms) // 2] if ms else None,
                                            "temps": temps if s != "ALL" else None}))
    out = ["# E-04a results", "",
           "Measured on the `eval` half of families; temperature and the 5%-risk threshold chosen on `fit`.",
           "Reference systems (Jev, djev, Laya) as shipped in the Leanmcp JevBench predictions, on the same cases.", ""]
    for name in dict.fromkeys(r[0] for r in rows):
        out += [f"## {name}", "", "| slice | system | n | acc [95% CI] | Brier | ECE | coverage at 5% (risk) |", "|---|---|---|---|---|---|---|"]
        for n_, s, label, m in rows:
            if n_ != name or label == "_diag":
                continue
            risk = f"{m['risk']:.3f}" if m.get("risk") is not None else "-"
            ci = m.get("acc_ci")
            cis = f" [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else ""
            out.append(f"| {s} | {label} | {m.get('n', 0)} | {m.get('acc', 0):.3f}{cis} | {m.get('brier', 0):.3f} | "
                       f"{m.get('ece', 0):.3f} | {m.get('cov5', 0):.2f} ({risk}) |")
        out += ["", "| slice | order-flip rate | letter mass | median ms per read | temperature |", "|---|---|---|---|---|"]
        for n_, s, label, m in rows:
            if n_ == name and label == "_diag":
                t = m["temps"][s] if m.get("temps") else "-"
                out.append(f"| {s} | {m['flip']:.3f} | {m['letter_mass']:.2f} | {m['median_ms'] or 0:.0f} | {t} |")
        out.append("")
    text = "\n".join(out)
    dest = os.path.join(os.path.dirname(paths[0]), "summary.md")
    open(dest, "w").write(text)
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
