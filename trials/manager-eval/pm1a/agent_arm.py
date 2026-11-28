"""PM-1a with a Claude Code subagent as the manager (the owner, 2026-11-28: "use a subagent here on my subscription").

The subagent is given manager.md and calls the stub's tools through this script, one shell command per call, so it sees
each tool's result before its next move, as a manager with MCP tools would. The stub's state between calls is rebuilt
by replaying the scenario's earlier calls. Labels are never printed.

    python3 -I agent_arm.py tools                          # the tool schemas
    python3 -I agent_arm.py msg   RUN ID                   # start scenario ID: prints its message (or event)
    python3 -I agent_arm.py call  RUN ID TOOL 'JSON'       # one tool call; prints the result
    python3 -I agent_arm.py final RUN ID 'TEXT'            # the closing text of the turn ('' for none)
    python3 -I agent_arm.py score RUN --label LABEL --out FILE   # replay-format results, scored

RUN is a directory holding ID.trace.jsonl, ID.final.txt and ID.t0 for each scenario.

Differences from the claude -p driver (Substrate): the manager is a subagent whose own system prompt is Claude Code's,
with manager.md given as instructions; one subagent may play several scenarios in a row (told to treat each as a fresh
session); wall time and tokens are not measured.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drivers  # noqa: E402
import replay  # noqa: E402
import score as S  # noqa: E402
import stub_pm  # noqa: E402


def world():
    scenarios, portfolio = replay.load_world()
    return {s["id"]: s for s in scenarios}, scenarios, portfolio


def paths(run, sid):
    return {k: os.path.join(run, f"{sid}.{k}") for k in ("trace.jsonl", "final.txt", "t0")}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tools")
    for c in ("msg", "call", "final"):
        p = sub.add_parser(c)
        p.add_argument("run")
        p.add_argument("id")
        if c == "call":
            p.add_argument("tool")
            p.add_argument("args", nargs="?", default="{}")
        if c == "final":
            p.add_argument("text", nargs="?", default="")
    p = sub.add_parser("score")
    p.add_argument("run")
    p.add_argument("--label", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.cmd == "tools":
        print(json.dumps(stub_pm.TOOLS, indent=1))
        return
    by, scenarios, portfolio = world()
    if a.cmd == "score":
        runs = []
        for sc in scenarios:
            p = paths(a.run, sc["id"])
            if not os.path.exists(p["t0"]):
                continue
            trace = S.load_trace(p["trace.jsonl"])
            final = open(p["final.txt"]).read() if os.path.exists(p["final.txt"]) else ""
            res = {"final_text": final, "launch_ts": float(open(p["t0"]).read()), "wall_s": 0.0, "tokens": drivers.tokens(),
                   "offered_tools": list(stub_pm.NAMES), "attempts": [c["tool"] for c in trace if "tool" in c], "error": None}
            sco = S.score(sc, replay.fresh(portfolio, sc), trace, res)
            runs.append({"id": sc["id"], "score": sco, "trace": trace, "final_text": final, "error": None,
                         "reported_model": a.label, "offered_tools": res["offered_tools"]})
        ok = sum(r["score"]["routing_ok"] for r in runs)
        with open(a.out, "w") as f:
            json.dump({"driver": f"subagent:{a.label}", "date": time.strftime("%Y-%m-%d"), "stopped": None, "runs": runs}, f, indent=1)
        print(f"{a.label}: routing {ok}/{len(runs)}; failed: {','.join(r['id'] for r in runs if not r['score']['routing_ok'])}")
        return

    if a.id not in by:
        sys.exit(f"no scenario {a.id}")
    os.makedirs(a.run, exist_ok=True)
    p = paths(a.run, a.id)
    sc = by[a.id]
    if a.cmd == "msg":
        for f in p.values():
            if os.path.exists(f):
                os.remove(f)
        open(p["t0"], "w").write(str(time.time()))
        print(S.message_for(sc))
        return
    if not os.path.exists(p["t0"]):
        sys.exit("run `msg` for this scenario first")
    if a.cmd == "final":
        open(p["final.txt"], "w").write(a.text)
        print("turn ended")
        return
    stub = stub_pm.Stub(replay.fresh(portfolio, sc), None)
    for c in S.load_trace(p["trace.jsonl"]):  # rebuild the state left by earlier calls
        if "tool" in c:
            stub.call(c["tool"], c["arguments"])
    stub.trace_path, stub.seq = p["trace.jsonl"], len(S.load_trace(p["trace.jsonl"]))
    try:
        args = json.loads(a.args)
    except ValueError as e:
        args, text = None, f"arguments are not JSON: {e}"
    if args is not None:
        text, _ = stub.call(a.tool, args)
    print(text)


if __name__ == "__main__":
    main()
