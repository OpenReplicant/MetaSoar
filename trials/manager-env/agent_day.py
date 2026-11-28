"""Tier 2 with a Claude Code subagent as the manager: the day is driven one shell command per move, like
pm1a/agent_arm.py. The environment is rebuilt for each command by replaying the moves so far (they are deterministic:
every turn is given a fixed `--seconds`, default 30). Scores and labels are never printed until `report`.

    python3 agent_day.py start  RUN DAY                 # resets the day; prints the first arrival
    python3 agent_day.py call   RUN TOOL 'JSON'         # one tool call in the current turn; prints its result
    python3 agent_day.py end    RUN 'TEXT'              # ends the turn ('' for no closing text); prints the next arrival
    python3 agent_day.py report RUN --label L --out F   # the per-arrival scores and the day's metrics

RUN is a directory (one day each). Differences from run_day.py: the manager is one subagent for the whole day, so it
remembers earlier turns (run_day.py gives each turn a fresh session); turn time is fixed, not measured.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from manager_env import DayAction, DayEnvironment  # noqa: E402


def load(run):
    with open(os.path.join(run, "moves.json")) as f:
        return json.load(f)


def rebuild(m):
    env = DayEnvironment(m.get("options") or {})
    obs = env.reset(day_id=m["day"])
    for mv in m["moves"]:
        if mv["type"] == "call":
            obs = env.step(DayAction(type="call_tool", tool_name=mv["tool"], arguments=mv["args"]))
        else:
            obs = env.step(DayAction(type="end_turn", text=mv["text"], seconds=m["seconds"]))
    return env, obs


def show(obs):
    if obs.done:
        return "THE DAY IS OVER. Nothing more to do."
    head = f"[{obs.clock}] arrival {obs.arrival_index} ({obs.queue_len} more waiting)"
    return f"{head}\n{obs.message}"


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("run")
    s.add_argument("day")
    s.add_argument("--seconds", type=float, default=30.0)
    s.add_argument("--options", default="{}")
    c = sub.add_parser("call")
    c.add_argument("run")
    c.add_argument("tool")
    c.add_argument("args", nargs="?", default="{}")
    e = sub.add_parser("end")
    e.add_argument("run")
    e.add_argument("text", nargs="?", default="")
    r = sub.add_parser("report")
    r.add_argument("run")
    r.add_argument("--label", required=True)
    r.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.cmd == "start":
        os.makedirs(a.run, exist_ok=True)
        m = {"day": a.day, "seconds": a.seconds, "options": json.loads(a.options), "moves": []}
        _, obs = rebuild(m)
        json.dump(m, open(os.path.join(a.run, "moves.json"), "w"))
        print(show(obs))
        return
    m = load(a.run)
    if a.cmd == "report":
        env, obs = rebuild(m)
        if not obs.done:
            sys.exit("the day is not over yet")
        d = env.day
        out = {"driver": f"subagent:{a.label}", "day": m["day"], "seconds_per_turn": m["seconds"],
               "episode": d.episode(), "arrivals": d.records}
        json.dump(out, open(a.out, "w"), indent=1, default=str)
        ep = out["episode"]
        print(f"{m['day']} {a.label}: routing {ep['routing']:.3f} of {ep['arrivals']}; dropped {ep['dropped_loops']['count']}; "
              f"double writers {ep['double_writers']['count']}; interruptions {ep['interruptions']}; "
              f"wrong: {','.join(str(x.get('sid_full') or x.get('id')) for x in d.records if not x['routing_ok'])}")
        return
    env, obs = rebuild(m)
    if obs.done:
        sys.exit("the day is over")
    if a.cmd == "call":
        try:
            args = json.loads(a.args)
        except ValueError as ex:
            print(f"arguments are not JSON: {ex}")
            return
        mv = {"type": "call", "tool": a.tool, "args": args}
        obs = env.step(DayAction(type="call_tool", tool_name=a.tool, arguments=args))
        m["moves"].append(mv)
        json.dump(m, open(os.path.join(a.run, "moves.json"), "w"))
        if obs.tool_result is not None and obs.arrival_score is None:
            print(obs.tool_result)
        else:  # the environment ended the turn itself (step limit, stop_after_action, pm_nothing)
            print("(turn ended)\n" + show(obs))
        return
    obs = env.step(DayAction(type="end_turn", text=a.text, seconds=m["seconds"]))
    m["moves"].append({"type": "end", "text": a.text})
    json.dump(m, open(os.path.join(a.run, "moves.json"), "w"))
    print(show(obs))


if __name__ == "__main__":
    main()
