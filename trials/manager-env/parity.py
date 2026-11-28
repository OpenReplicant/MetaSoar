"""Parity: replay every saved PM-1a trace through manager-env and check routing_ok equals the saved score.

    python3 -I parity.py [FILE ...] [--runs-dir /home/user/MetaSoar/trials/kaggle/runs]

The trace's successful and failed tool calls are the actions, in order; final_text is the closing text of the turn. The
reward the environment returns is compared with the saved routing_ok (1.0 or 0.0), and, as a stricter check, the new
score's tags, named projects and action_ok/project_ok are compared with the saved ones. Exit code 1 on any mismatch.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from manager_env import ManagerAction, ManagerEnvironment  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FILES = [
    "{runs}/pm1a/out/trials/manager-eval/pm1a/results/pm1a-kaggle-inkling.json",
    "{runs}/pm1a/out/trials/manager-eval/pm1a/results/pm1a-kaggle-lfm3.json",
    "{repo}/trials/manager-eval/pm1a/results/agent/pm1a-agent-haiku.json",
    "{repo}/trials/manager-eval/pm1a/results/agent/pm1a-agent-sonnet.json",
]
FALLBACK_RUNS = "/home/user/MetaSoar/trials/kaggle/runs"


def default_files(runs_dir=None):
    runs = runs_dir or os.path.join(REPO, "trials", "kaggle", "runs")
    if not os.path.isdir(runs):
        runs = FALLBACK_RUNS
    return [f.format(runs=runs, repo=REPO) for f in FILES]


def replay_run(env, run):
    """Play one saved run through the environment; returns the final observation."""
    env.reset(scenario_id=run["id"])
    obs = None
    calls = [c for c in run["trace"] if "tool" in c]
    for i, c in enumerate(calls):
        # a run that hit the step limit ends on its last call, so its closing text rides along as that call's content
        md = {"content": run["final_text"]} if i == len(calls) - 1 and run.get("final_text") else {}
        obs = env.step(ManagerAction(type="call_tool", tool_name=c["tool"], arguments=c["arguments"], metadata=md))
        if obs.done:
            return obs
    return env.step(ManagerAction(type="end_turn", text=run.get("final_text") or ""))


def check(path, env=None):
    env = env or ManagerEnvironment()
    data = json.load(open(path))
    rows, bad = [], []
    for r in data["runs"]:
        obs = replay_run(env, r)
        new, old = obs.metadata["score"], r["score"]
        same = bool(obs.reward) == bool(old["routing_ok"])
        strict = (new["tags"], new["named"], new["action_ok"], new["project_ok"]) == \
                 (old["tags"], old["named"], old["action_ok"], old["project_ok"])
        rows.append((r["id"], same, strict))
        if not same or not strict:
            bad.append((r["id"], old["routing_ok"], obs.reward, old["tags"], new["tags"], old["named"], new["named"]))
    return rows, bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--runs-dir")
    a = ap.parse_args(argv)
    files = a.files or default_files(a.runs_dir)
    total = match = strict = 0
    failed = False
    for p in files:
        if not os.path.exists(p):
            print(f"MISSING {p}")
            failed = True
            continue
        rows, bad = check(p)
        n, m, s = len(rows), sum(1 for _, x, _ in rows if x), sum(1 for _, _, x in rows if x)
        total, match, strict = total + n, match + m, strict + s
        print(f"{os.path.basename(p)}: routing_ok matches {m}/{n}; tags, projects, action_ok, project_ok match {s}/{n}")
        for b in bad:
            print("   differs:", b)
        failed = failed or m != n
    print(f"total: routing_ok {match}/{total}; strict {strict}/{total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
