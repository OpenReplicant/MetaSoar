"""Run one of Soar's own agents, unchanged, and record what the impasse watcher would see.

    python3 -m metasoar.run water-jug-simple/water-jug.soar [MAX_DECISIONS] [OUT_DIR]

Through Soar's Python SML bindings, in this process. After every decision cycle it reads the goal stack (Soar's
`print --stack`), so impasses and their substates are seen from outside the agent, as the hook will see them
(docs/spec.md, "The only things we add"). Writes the full trace and a JSON summary; prints the summary.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import Python_sml_ClientInterface as sml

AGENTS = Path(os.environ.get("SOAR_AGENTS", "/opt/soar/Agents"))


def main():
    agent_file = AGENTS / sys.argv[1]
    max_dc = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    out = Path(sys.argv[3] if len(sys.argv) > 3 else "/out")
    out.mkdir(parents=True, exist_ok=True)

    kernel = sml.Kernel.CreateKernelInCurrentThread(True)
    if kernel.HadError():
        sys.exit(kernel.GetLastErrorDescription())
    agent = kernel.CreateAgent("metasoar")
    trace: list[str] = []
    agent.RegisterForPrintEvent(sml.smlEVENT_PRINT, lambda _id, _data, _agent, msg: trace.append(msg), None)

    stacks: list[dict] = []

    def after_decision(_id, _data, ag, _phase):
        stack = ag.ExecuteCommandLine("print --stack").strip().splitlines()
        stacks.append({"dc": ag.GetDecisionCycleCounter(), "depth": len(stack), "stack": [s.strip() for s in stack]})

    agent.RegisterForRunEvent(sml.smlEVENT_AFTER_DECISION_CYCLE, after_decision, None)

    loaded = agent.ExecuteCommandLine(f"source {{{agent_file}}}")
    if not agent.GetLastCommandLineResult():
        sys.exit(f"source failed: {loaded}")
    t0 = time.perf_counter()
    agent.ExecuteCommandLine(f"run {max_dc}")
    seconds = time.perf_counter() - t0

    impasses = [s for s in stacks if s["depth"] > 1]
    summary = {
        "agent": sys.argv[1],
        "soar": agent.ExecuteCommandLine("version").splitlines()[0].strip(),
        "decisions": agent.GetDecisionCycleCounter(),
        "seconds": round(seconds, 4),
        "max_depth": max((s["depth"] for s in stacks), default=0),
        "decisions_in_a_substate": len(impasses),
        "first_impasse": impasses[0] if impasses else None,
        "halted": "halted" in "".join(trace).lower() or "interrupt" in "".join(trace).lower(),
        "productions": len([l for l in agent.ExecuteCommandLine("print").splitlines() if l.strip()]),
    }
    (out / "trace.txt").write_text("".join(trace))
    (out / "stacks.jsonl").write_text("".join(json.dumps(s) + "\n" for s in stacks))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    kernel.Shutdown()


if __name__ == "__main__":
    main()
