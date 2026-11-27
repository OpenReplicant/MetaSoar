"""E-17 summary: writes results/summary-e17.md from stream.jsonl, state.json, baseline.jsonl and the gold answers.

Gold is read here and only here. Per chunk: rung shares, fallback rate, accuracy, calls and seconds per case. Over the
last 150: coverage by templates + handlers, accuracy, accuracy difference against the large model alone (paired,
95% bootstrap interval over cases), and E-17's two refutation conditions. Then the intents.
Usage: python3 -I summarize.py [--last 150]
"""
from __future__ import annotations

import argparse, json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import smoke  # noqa: E402
import stream  # noqa: E402


def jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f]


def load(path):
    with open(path) as f:
        return json.load(f)


def bootstrap(xs, reps=2000, seed=0):
    """Mean and 95% percentile interval of a list, resampling cases."""
    rng, n = random.Random(seed), len(xs)
    means = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return sum(xs) / n, means[int(0.025 * reps)], means[int(0.975 * reps) - 1]


def summarize(out_dir, data_dir, chunk_size=100, last=150, total=300):
    recs, base = jsonl(os.path.join(out_dir, "stream.jsonl")), {r["id"]: r for r in jsonl(os.path.join(out_dir, "baseline.jsonl"))}
    gold = load(os.path.join(data_dir, "problems_test1k.json"))  # the only place gold is read
    ok = lambda pid, ans: bool(smoke.correct(ans, gold[pid]))
    pct = lambda x: f"{100 * x:.1f}%"
    L = ["# E-17 summary", "", f"{len(recs)} cases, chunks of {chunk_size}.", "", "## Per chunk", "",
         "| chunk | n | handler | template | large | fallback | accuracy | large calls/case | large s/case | small calls/case | small s/case |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for ch in sorted({r["chunk"] for r in recs}):
        rs = [r for r in recs if r["chunk"] == ch]
        n = len(rs)
        share = lambda k: pct(sum(r["rung"] == k for r in rs) / n)
        L.append(f"| {ch} | {n} | {share('handler')} | {share('template')} | {share('large')} | "
                 f"{pct(sum(r['fallback'] for r in rs) / n)} | {pct(sum(ok(r['id'], r['answer']) for r in rs) / n)} | "
                 f"{sum(r['large']['calls'] for r in rs) / n:.2f} | {sum(r['large']['seconds'] for r in rs) / n:.1f} | "
                 f"{sum(r['small']['calls'] for r in rs) / n:.2f} | {sum(r['small']['seconds'] for r in rs) / n:.1f} |")
    tail = recs[-last:]
    L += ["", f"## Last {len(tail)} cases", ""]
    cover = sum(r["rung"] != "large" for r in tail) / max(1, len(tail))
    acc = sum(ok(r["id"], r["answer"]) for r in tail) / max(1, len(tail))
    missing = [r["id"] for r in tail if r["rung"] != "large" and r["id"] not in base]
    L += [f"- coverage by templates + handlers: {pct(cover)}", f"- accuracy of the stream: {pct(acc)}"]
    refuted = [cover < 0.30]
    if missing or not tail:
        L.append(f"- paired difference: withheld, {len(missing)} baseline answers missing (run baseline.py)")
        diff = None
    else:
        d = [ok(r["id"], r["answer"]) - ok(r["id"], base[r["id"]]["answer"] if r["rung"] != "large" else r["answer"]) for r in tail]
        mean, lo, hi = bootstrap(d)
        L.append(f"- large model alone accuracy (baseline for cheaper-rung cases, stream's own otherwise): {pct(acc - mean)}")
        L.append(f"- paired accuracy difference, stream minus large alone: {100 * mean:+.1f} points, 95% bootstrap interval [{100 * lo:+.1f}, {100 * hi:+.1f}]")
        diff = hi < -0.02
        refuted.append(diff)
    if len(recs) < total:  # the falsifier is about the stream's last segment, so it is not read before the stream ends
        L += ["", "## E-17 verdict lines", "", f"- withheld: the stream is incomplete ({len(recs)} of {total} cases)"]
        refuted, diff = [], "incomplete"
    L += ([] if diff == "incomplete" else ["", "## E-17 verdict lines", "",
          f"- coverage below 30%? {'YES' if cover < 0.30 else 'NO'} ({pct(cover)})",
          f"- accuracy more than 2 points below the large model alone, beyond the interval (interval's upper end < -2)? "
          + ("not computed" if diff is None else "YES" if diff else "NO"),
          "- refutation condition met: " + ("YES" if any(refuted) else "NO" if diff is not None else "not yet (difference not computed)")])
    L += ["", "## Intents", "", "| intent | cases | rungs used (handler/template/large) | highest rung reached | handler agreement | template agreement |",
          "| --- | --- | --- | --- | --- | --- |"]
    sp = os.path.join(out_dir, "state.json")
    intents = load(sp)["intents"] if os.path.exists(sp) else {}
    for key, it in sorted(intents.items(), key=lambda kv: -kv[1]["n"]):
        used = [sum(r["intent"] == key and r["rung"] == k for r in recs) for k in ("handler", "template", "large")]
        cands = it["candidates"]
        fmt = lambda c: "none" if not c else f"{c['agree']}/{c['n']} {c['status']} v{c['version']}"
        reach = next((k for k in ("handler", "template") if cands[k] and cands[k]["status"] == "active"), "large")
        L.append(f"| {key} | {it['n']} | {'/'.join(map(str, used))} | {reach} | {fmt(cands['handler'])} | {fmt(cands['template'])} |")
    text = "\n".join(L) + "\n"
    with open(os.path.join(out_dir, "summary-e17.md"), "w") as f:
        f.write(text)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--last", type=int, default=150)
    ap.add_argument("--data", default=smoke.DATA)
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--chunk-size", type=int, default=100)
    ap.add_argument("--n", type=int, default=300, help="the stream's length (E-17b: 450)")
    a = ap.parse_args()
    print(summarize(a.out, a.data, a.chunk_size, a.last, a.n))


if __name__ == "__main__":
    main()
