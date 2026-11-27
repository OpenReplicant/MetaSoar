"""E-18 baseline and summary (docs/experiments.md, E-18). Gold is read here, in `summary` only.

    python3 -I e18_report.py baseline --data DIR --out DIR   (Inkling alone, WTQ prompt, on the last 150's cheaper-rung cases)
    python3 -I e18_report.py summary --data DIR --out DIR    (writes summary-e18.md)
"""
from __future__ import annotations

import argparse, json, os, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import smoke  # noqa: E402
import smoke_wtq  # noqa: E402
import stream  # noqa: E402
import summarize  # noqa: E402
import wtq  # noqa: E402

CHEAP = ("fine_handler", "class_handler", "template")


def fmt(c):
    return "none" if not c else f"{c['agree']}/{c['n']} {c['status']} v{c['version']}"


def baseline(data_dir, out_dir, large_fn, n=450, last=150, log=print):
    cases = {c["id"]: c for c in stream.load_cases(data_dir, n)}
    recs = summarize.jsonl(os.path.join(out_dir, "stream.jsonl"))
    if len(recs) < n:
        raise SystemExit("the stream is not complete")
    tail = [r["id"] for r in recs[-last:] if r["rung"] in CHEAP]
    path = os.path.join(out_dir, "baseline.jsonl")
    have = {r["id"] for r in summarize.jsonl(path)}
    large, k = stream.Meter(large_fn), 0
    with open(path, "a") as f:
        for pid in tail:
            if pid in have:
                continue
            before = large.snap()
            text = large.ask(smoke_wtq.prompt(cases[pid]), stream.LARGE_TOKENS)
            raw = smoke.extract(text)
            f.write(json.dumps({"id": pid, "answer": raw or "", "text": text, "large": stream.delta(before, large.snap())}) + "\n")
            f.flush()
            k += 1
            log(f"baseline {k} {pid} {raw!r}")
    return k


def summary(out_dir, data_dir, chunk_size=50, last=150, total=450):
    recs = summarize.jsonl(os.path.join(out_dir, "stream.jsonl"))
    base = {r["id"]: r for r in summarize.jsonl(os.path.join(out_dir, "baseline.jsonl"))}
    gold = summarize.load(os.path.join(data_dir, "problems_test1k.json"))
    ok = lambda pid, a: bool(a) and wtq.correct(a, gold[pid])
    pct = lambda x: f"{100 * x:.1f}%"
    L = ["# E-18 summary", "", f"{len(recs)} cases, chunks of {chunk_size}.", "", "## Per chunk", "",
         "| chunk | n | fine handler | class handler | template | large | fallback | accuracy | Inkling calls/case | Inkling s/case | small s/case |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for ch in sorted({r["chunk"] for r in recs}):
        rs = [r for r in recs if r["chunk"] == ch]
        n = len(rs)
        sh = lambda k: pct(sum(r["rung"] == k for r in rs) / n)
        L.append(f"| {ch} | {n} | {sh('fine_handler')} | {sh('class_handler')} | {sh('template')} | {sh('large')} | "
                 f"{pct(sum(r['fallback'] for r in rs) / n)} | {pct(sum(ok(r['id'], r['answer']) for r in rs) / n)} | "
                 f"{sum(r['large']['calls'] for r in rs) / n:.2f} | {sum(r['large']['seconds'] for r in rs) / n:.1f} | "
                 f"{sum(r['small']['seconds'] for r in rs) / n:.1f} |")
    tail = recs[-last:] if len(recs) >= total else []
    cheap = [r for r in tail if r["rung"] in CHEAP]
    L += ["", f"## Cases {total - last + 1} to {total}", ""]
    if not tail:
        L.append(f"- withheld: the stream is incomplete ({len(recs)} of {total} cases)")
    else:
        cover = len(cheap) / len(tail)
        acc = sum(ok(r["id"], r["answer"]) for r in tail) / len(tail)
        L += [f"- coverage by templates and handlers: {pct(cover)}", f"- accuracy of the stream: {pct(acc)}"]
        missing = [r["id"] for r in cheap if r["id"] not in base]
        diff = None
        if missing:
            L.append(f"- paired difference: withheld, {len(missing)} baseline answers missing")
        else:
            d = [ok(r["id"], r["answer"]) - ok(r["id"], base[r["id"]]["answer"] if r["rung"] in CHEAP else r["answer"]) for r in tail]
            mean, lo, hi = summarize.bootstrap(d)
            L += [f"- Inkling alone on the same cases: {pct(acc - mean)}",
                  f"- paired difference, stream minus Inkling alone: {100 * mean:+.1f} points [{100 * lo:+.1f}, {100 * hi:+.1f}]"]
            diff = hi < -0.02
        ex = [r for r in cheap if r["exact_admit"]]
        lo_only = [r for r in cheap if not r["exact_admit"]]
        for name, rs in (("cheap answers the exact shape would have admitted", ex), ("cheap answers only the loose shape admitted", lo_only)):
            L.append(f"- {name}: {len(rs)}, accuracy {pct(sum(ok(r['id'], r['answer']) for r in rs) / len(rs)) if rs else 'n/a'}")
        cls300 = Counter(r["class"] for r in recs[:300])
        ni = []
        if sum(v >= 9 for k, v in cls300.items() if k != "other") < 5:
            ni.append("fewer than 5 classes have 9 or more cases in the first 300")
        share = sum(r["class"] in ("lookup", "other") for r in recs) / len(recs)
        if share > 0.30:
            ni.append(f"lookup and other hold {pct(share)} of cases")
        L += ["", "## E-18 verdict lines", "",
              f"- classes with 9 or more cases in the first 300: {sum(v >= 9 for k, v in cls300.items() if k != 'other')}; lookup and other: {pct(share)}",
              f"- coverage below 30%? {'YES' if cover < 0.30 else 'NO'} ({pct(cover)})",
              "- accuracy more than 2 points below Inkling alone (interval's upper end below -2)? "
              + ("not computed" if diff is None else "YES" if diff else "NO")]
        if ni:
            L.append("- **not informative**: " + "; ".join(ni))
        elif diff is not None:
            L.append("- refutation condition met: " + ("YES" if cover < 0.30 or diff else "NO"))
    L += ["", "## Classes", "", "| class | cases | cheap answers | accuracy | class handler | fine intents | withdrawn |", "| --- | --- | --- | --- | --- | --- | --- |"]
    sp = os.path.join(out_dir, "state.json")
    st = summarize.load(sp) if os.path.exists(sp) else {"classes": {}, "intents": {}}
    for cls, n in Counter(r["class"] for r in recs).most_common():
        rs = [r for r in recs if r["class"] == cls]
        h = st["classes"].get(cls, {}).get("handler")
        fines = [k for k in st["intents"] if k.split(":")[0] == cls]
        L.append(f"| {cls} | {n} | {sum(r['rung'] in CHEAP for r in rs)} | {pct(sum(ok(r['id'], r['answer']) for r in rs) / n)} | "
                 f"{fmt(h)} | "
                 f"{len(fines)} | {sum(bool(st['intents'][k].get('withdrawn')) for k in fines)} |")
    L += ["", f"Routes: {dict(Counter(r['route'].get('by') for r in recs))}"]
    text = "\n".join(L) + "\n"
    with open(os.path.join(out_dir, "summary-e18.md"), "w") as f:
        f.write(text)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("baseline", "summary"))
    stream.add_model_flags(ap)
    ap.set_defaults(n=450, chunk_size=50)
    ap.add_argument("--last", type=int, default=150)
    a = ap.parse_args()
    if a.cmd == "baseline":
        baseline(a.data, a.out, stream.build_models(a)[0], a.n, a.last)
    else:
        print(summary(a.out, a.data, a.chunk_size, a.last, a.n))


if __name__ == "__main__":
    main()
