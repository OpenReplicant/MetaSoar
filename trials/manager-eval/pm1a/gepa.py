"""Candidate sweeps for prompt/environment optimisation (GEPA-style) of the OpenAICompatible manager. Standard library
only; run with python3 -I.

    python3 -I gepa.py run --candidates cands.json --arm inkling --url http://127.0.0.1:8081 --model inkling \
        [--only s01,s02] [--out-dir DIR] [--resume]
    python3 -I gepa.py summary DIR [--baseline results/pm1a-DATE-haiku.json ...]

cands.json: {"candidates": [{"id": "c0", "prompt": "prompts/c0.md" | null, "env": {...}, "extra": {...}, "prefill": "off|on|auto"}]}
`prompt` is relative to this folder (null: manager.md); `env` is drivers.OpenAICompatible's environment options.
`run` writes DIR/<arm>-<id>.json per candidate, in replay.py's format (default DIR: results/gepa). `summary` reads every
DIR/*.json (and the baselines), prints the per-scenario routing_ok matrix, each candidate's routing accuracy on the
scenarios it ran, and the Pareto front over the scenarios all candidates ran, and writes DIR/summary.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I does not put the script's folder on the path

import drivers  # noqa: E402
import replay  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(HERE, "results", "gepa")


def load_candidates(path):
    cands = json.load(open(path))["candidates"]
    ids = [c["id"] for c in cands]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate candidate ids in {path}")
    return cands


def make_driver(c, arm, url, model):
    prompt = c.get("prompt")
    return drivers.OpenAICompatible(url, model, os.path.join(HERE, prompt) if prompt else None, c.get("extra") or {},
                                    name=f"openai-compatible:{arm}-{c['id']}", prefill=c.get("prefill") or "off",
                                    env=c.get("env") or {})


def run(a, log=print):
    cands = load_candidates(a.candidates)
    out_dir = a.out_dir or DEFAULT_DIR
    os.makedirs(out_dir, exist_ok=True)
    scenarios, portfolio = replay.load_world()
    only = set(a.only.split(",")) if a.only else None
    stopped = None
    for i, c in enumerate(cands, 1):
        out = os.path.join(out_dir, f"{a.arm}-{c['id']}.json")
        log(f"== candidate {c['id']} ({i}/{len(cands)}) -> {out}")
        runs, stopped = replay.run_all(make_driver(c, a.arm, a.url, a.model), scenarios, portfolio, out, only, a.resume,
                                       log=lambda s, cid=c["id"]: log(f"[{cid}] {s}"))
        ok = sum(1 for r in runs if r["score"]["routing_ok"])
        log(f"== {c['id']}: routing {ok}/{len(runs)}" + (f"; STOPPED: {stopped}" if stopped else ""))
        if stopped:
            break
    return stopped


def load_results(paths):
    """name -> {scenario id: routing_ok}. Files that are not run results (summary.json) are skipped."""
    out = {}
    for p in paths:
        try:
            d = json.load(open(p))
        except ValueError:
            continue
        if not isinstance(d, dict) or "runs" not in d:
            continue
        out[os.path.basename(p).removesuffix(".json")] = {r["id"]: bool(r["score"]["routing_ok"]) for r in d["runs"]}
    return out


def dominated(v, others):
    return any(all(x >= y for x, y in zip(o, v)) and any(x > y for x, y in zip(o, v)) for o in others)


def summarize(dir_, baselines=(), scenario_order=None):
    cand_paths = sorted(os.path.join(dir_, f) for f in os.listdir(dir_) if f.endswith(".json") and f != "summary.json")
    cands, bases = load_results(cand_paths), load_results(baselines)
    everyone = {**cands, **{n: v for n, v in bases.items() if n not in cands}}
    order = scenario_order or [s["id"] for s in replay.load_world()[0]]
    ids = [i for i in order if any(i in v for v in everyone.values())]
    acc = {n: {"ran": len(v), "ok": sum(v.values()), "accuracy": (sum(v.values()) / len(v)) if v else None}
           for n, v in everyone.items()}
    common = [i for i in ids if cands and all(i in v for v in cands.values())]
    vec = {n: [int(v[i]) for i in common] for n, v in cands.items()}
    front = [n for n, v in vec.items() if common and not dominated(v, [w for m, w in vec.items() if m != n])]
    return {"scenarios": ids, "common_scenarios": common, "candidates": list(cands), "baselines": [n for n in bases if n not in cands],
            "matrix": {n: {i: v[i] for i in ids if i in v} for n, v in everyone.items()}, "accuracy": acc,
            "common_accuracy": {n: (sum(v) / len(v) if v else None) for n, v in vec.items()}, "pareto_front": front}


def markdown(s):
    names = list(s["matrix"])
    L = ["| Scenario | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for i in s["scenarios"]:
        L.append(f"| {i} | " + " | ".join("-" if i not in s["matrix"][n] else "ok" if s["matrix"][n][i] else "WRONG" for n in names) + " |")
    L.append("| **accuracy (ran)** | " + " | ".join(
        "-" if s["accuracy"][n]["accuracy"] is None else f"{100 * s['accuracy'][n]['accuracy']:.0f}% ({s['accuracy'][n]['ok']}/{s['accuracy'][n]['ran']})"
        for n in names) + " |")
    L += ["", f"Common scenarios (all candidates ran): {len(s['common_scenarios'])}. Baselines (not in the front): "
          f"{', '.join(s['baselines']) or 'none'}.", "", "Pareto front (not dominated on the per-scenario routing_ok vector over the common set):"]
    L += [f"- {n}: {100 * s['common_accuracy'][n]:.0f}% on the common set" for n in s["pareto_front"]] or ["- (none)"]
    return "\n".join(L)


def summary(a):
    s = summarize(a.dir, a.baseline or [])
    with open(os.path.join(a.dir, "summary.json"), "w") as f:
        json.dump(s, f, indent=1)
    text = markdown(s)
    print(text)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--candidates", required=True)
    r.add_argument("--arm", required=True)
    r.add_argument("--url", required=True)
    r.add_argument("--model", required=True)
    r.add_argument("--only")
    r.add_argument("--out-dir")
    r.add_argument("--resume", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("dir")
    s.add_argument("--baseline", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        sys.exit(2 if run(a, log=lambda x: print(x, flush=True)) else 0)
    summary(a)


if __name__ == "__main__":
    main()
