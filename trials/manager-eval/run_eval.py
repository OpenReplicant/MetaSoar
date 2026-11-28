#!/usr/bin/env python3
"""Haiku 5.5 on MS-Eval's delegation labels: does the main agent delegate when it should?

Modes (run with python3 -I):
  prepare   write the subset (subset.json) and one prompt file per item (data/run/prompts/)
  run       call `claude -p --model haiku` once per item, in order; append to results/results.jsonl
            (resumable: items already in the file are skipped; stops on any rate or usage limit)
  score     read results/results.jsonl and write results/summary.json (rates with Wilson 95% intervals)

Each item is one MS-Eval task. The request is the task document up to the line where
the benchmark's own golden guidance starts (the marker below), so the prompt does not
reveal the label. The label is MS-Eval's need_subagent / no_need_subagent split.
"""
import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "manifest.json")
DATA = os.path.join(HERE, "data", "ms-eval")
RUN = os.path.join(HERE, "data", "run")
RESULTS = os.path.join(HERE, "results")
MARKER = "Task-Solving Rationable with Sub-task Decomposition:"
SEED = 20261127
PER_LABEL = 20  # 20 need-subagent and 20 direct tasks: 40 calls
CATS = "task_categories/cluster_by_delegation"

PROMPT = """You are the main agent of a multi-agent system. You can complete a request yourself with the tools a coding and office-work agent has (files, shell, spreadsheets, documents, calendars, email, Notion, Google Sheets, web access, and data warehouses or other services the request names). You can also delegate: launch sub-agents, either read-only research agents or writing agents that change files or documents. Sub-agents run in parallel. Each one costs time and context.

Read the user's request below and decide how to proceed. Answer with one JSON object and nothing else:
{"delegate": true or false, "reason": "one sentence"}
delegate true means you would launch one or more sub-agents for this request. delegate false means you would complete it directly in the main agent.

<request>
%s
</request>
"""


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def root_dir():
    return os.path.join(DATA, load_manifest()["commit"])


def read_text(rel):
    path = os.path.join(root_dir(), rel)
    if not os.path.exists(path):
        sys.exit(f"missing {rel}: run fetch_msEval.py first")
    with open(path, encoding="utf-8") as f:
        return f.read()


def request_text(doc_id):
    doc = read_text(f"data/oracle166/{doc_id}.task.md")
    if MARKER not in doc:
        sys.exit(f"marker not found in {doc_id}")
    return doc.split(MARKER, 1)[0].strip()


def build_subset():
    need = [x.strip() for x in read_text(f"data/{CATS}/need_subagent/need_subagent.txt").splitlines() if x.strip()]
    direct = [x.strip() for x in read_text(f"data/{CATS}/no_need_subagent/no_need_subagent.txt").splitlines() if x.strip()]
    rng = random.Random(SEED)
    items = []
    for label, pool in (("need_subagent", need), ("no_need_subagent", direct)):
        for doc_id in sorted(rng.sample(pool, PER_LABEL)):
            items.append({"id": doc_id, "label": label, "delegate_expected": label == "need_subagent"})
    return items


def prepare():
    os.makedirs(os.path.join(RUN, "prompts"), exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    items = build_subset()
    for it in items:
        prompt = PROMPT % request_text(it["id"])
        path = os.path.join(RUN, "prompts", it["id"] + ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(prompt)
        it["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        it["prompt_chars"] = len(prompt)
    with open(os.path.join(RESULTS, "subset.json"), "w", encoding="utf-8") as f:
        json.dump({"seed": SEED, "per_label": PER_LABEL, "source": "MS-Eval " + load_manifest()["commit"],
                   "items": items}, f, indent=1)
    print(f"subset: {len(items)} items")


DECISION = re.compile(r"\{[^{}]*\"delegate\"[^{}]*\}")
LIMIT = re.compile(r"rate limit|usage limit|hit your .{0,40}limit|limit reached", re.I)


def parse_decision(text):
    for m in DECISION.finditer(text or ""):
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(obj.get("delegate"), bool):
            return obj["delegate"], obj.get("reason", "")
    return None, ""


def call_haiku(prompt, cwd):
    cmd = ["claude", "-p", "--model", "haiku", "--output-format", "json",
           "--no-session-persistence", "--tools", ""]
    start = time.monotonic()
    proc = subprocess.run(cmd, input=prompt, cwd=cwd, capture_output=True, text=True, timeout=900)
    secs = time.monotonic() - start
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"result": proc.stdout, "is_error": True, "parse_failed": True}
    out["_returncode"] = proc.returncode
    out["_stderr"] = proc.stderr[-500:]
    out["_wall_s"] = round(secs, 2)
    return out


def run(limit):
    with open(os.path.join(RESULTS, "subset.json"), encoding="utf-8") as f:
        items = json.load(f)["items"]
    path = os.path.join(RESULTS, "results.jsonl")
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            done = {json.loads(line)["id"] for line in f if line.strip()}
    cwd = tempfile.mkdtemp(prefix="haiku-eval-cwd-")  # empty, outside the repo: no CLAUDE.md is loaded
    n = 0
    for it in items:
        if it["id"] in done:
            continue
        if limit is not None and n >= limit:
            break
        with open(os.path.join(RUN, "prompts", it["id"] + ".txt"), encoding="utf-8") as f:
            prompt = f.read()
        out = call_haiku(prompt, cwd)
        reply = out.get("result") or ""
        limited = bool(LIMIT.search(reply + " " + out.get("_stderr", ""))) or (
            out.get("is_error") and LIMIT.search(json.dumps(out)) is not None)
        delegate, reason = parse_decision(reply)
        rec = {
            "id": it["id"], "label": it["label"], "delegate_expected": it["delegate_expected"],
            "prompt_sha256": it["prompt_sha256"], "reply": reply, "delegate": delegate, "reason": reason,
            "correct": None if delegate is None else delegate == it["delegate_expected"],
            "wall_s": out["_wall_s"], "duration_ms": out.get("duration_ms"),
            "usage": out.get("usage"), "total_cost_usd": out.get("total_cost_usd"),
            "is_error": bool(out.get("is_error")), "returncode": out["_returncode"],
            "rate_limited": limited,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        n += 1
        print(f"{it['id']} {it['label']} delegate={delegate} correct={rec['correct']} {out['_wall_s']}s")
        if limited:
            print("rate or usage limit reached: stopping; rerun later to resume", file=sys.stderr)
            return 2
    return 0


def wilson(k, n, z=1.959964):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def score():
    path = os.path.join(RESULTS, "results.jsonl")
    with open(path, encoding="utf-8") as f:
        recs = [json.loads(line) for line in f if line.strip()]
    need = [r for r in recs if r["delegate_expected"]]
    direct = [r for r in recs if not r["delegate_expected"]]
    # UDR: needs delegation but did not; ODR: needs no delegation but delegated.
    # An unparsed reply counts as not delegating (it is not a decision to delegate).
    udr_k = sum(1 for r in need if r["delegate"] is not True)
    odr_k = sum(1 for r in direct if r["delegate"] is True)
    unparsed = sum(1 for r in recs if r["delegate"] is None)
    def tok(key):
        return sum((r["usage"] or {}).get(key, 0) or 0 for r in recs)
    tot_in = tok("input_tokens")
    tot_out = tok("output_tokens")
    tot_cache_w = tok("cache_creation_input_tokens")
    tot_cache_r = tok("cache_read_input_tokens")
    times = sorted(r["wall_s"] for r in recs)
    summary = {
        "model": "claude-haiku-5-5 (claude -p --model haiku)",
        "n_items": len(recs),
        "n_need": len(need), "n_direct": len(direct),
        "UDR": {"k": udr_k, "n": len(need), "rate": round(udr_k / len(need), 4) if need else None,
                "wilson95": wilson(udr_k, len(need))},
        "ODR": {"k": odr_k, "n": len(direct), "rate": round(odr_k / len(direct), 4) if direct else None,
                "wilson95": wilson(odr_k, len(direct))},
        "hit_accuracy": {"k": sum(1 for r in recs if r["correct"]), "n": len(recs),
                         "rate": round(sum(1 for r in recs if r["correct"]) / len(recs), 4) if recs else None},
        "unparsed": unparsed,
        "rate_limited": any(r["rate_limited"] for r in recs),
        "tokens": {"input": tot_in, "cache_creation": tot_cache_w, "cache_read": tot_cache_r, "output": tot_out},
        "total_cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in recs), 6),
        "wall_s": {"median": times[len(times) // 2] if times else None,
                   "max": times[-1] if times else None},
        "published_sonnet5_msEval": {"UDR": "39.3% (on 89 need-subagent tasks)", "ODR": "29.8%",
                                     "hit_F1": "31.4%", "conditions": "full agent runs in Kimi-Code, 166 tasks, "
                                     "live local MCP/database environment, adaptive effort, runs not stated"},
    }
    with open(os.path.join(RESULTS, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["prepare", "run", "score"])
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    if a.mode == "prepare":
        prepare()
    elif a.mode == "run":
        sys.exit(run(a.limit))
    else:
        score()


if __name__ == "__main__":
    main()
