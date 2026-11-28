#!/usr/bin/env python3
"""Compare Haiku's stated decisions with the paper's observed Sonnet 5 delegation on the same 40 tasks.

Reads results/results.jsonl (stated) and MS-Eval's published
eval/eval_results/claude-sonnet-5/auto-spec/task_metrics.csv (observed; saved to
data/published/sonnet5_task_metrics.csv, sha256 in the README). Run with python3 -I.
Writes results/stated_vs_sonnet.json.
"""
import csv, json, math, os
H = os.path.dirname(os.path.abspath(__file__))

def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 3), round(c + h, 3)

stated = {}
for line in open(os.path.join(H, "results", "results.jsonl"), encoding="utf-8"):
    r = json.loads(line); stated[r["id"]] = r
obs = {r["task"]: r for r in csv.DictReader(open(os.path.join(H, "data", "published", "sonnet5_task_metrics.csv"), encoding="utf-8"))}
rows = []
for t, r in stated.items():
    o = obs[t]
    need = r["label"] == "need_subagent"
    assert (o["need_delegation"] == "True") == need, t
    rows.append(dict(id=t, need=need, haiku_stated=bool(r["delegate"]), sonnet_observed=(o["delegated"] == "True")))
out = {}
for name, key in (("haiku_stated", "haiku_stated"), ("sonnet_observed_on_subset", "sonnet_observed")):
    nd = [x for x in rows if x["need"]]; dr = [x for x in rows if not x["need"]]
    u = sum(not x[key] for x in nd); o_ = sum(x[key] for x in dr)
    out[name] = dict(UDR=[u, len(nd), round(u / len(nd), 3), wilson(u, len(nd))], ODR=[o_, len(dr), round(o_ / len(dr), 3), wilson(o_, len(dr))])
out["flips"] = [x for x in rows if x["haiku_stated"] != x["sonnet_observed"]]
out["agree"] = sum(x["haiku_stated"] == x["sonnet_observed"] for x in rows)
json.dump(out, open(os.path.join(H, "results", "stated_vs_sonnet.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "flips"}, indent=1))
for x in out["flips"]:
    print(("need " if x["need"] else "direct"), "haiku", x["haiku_stated"], "sonnet", x["sonnet_observed"], x["id"])
