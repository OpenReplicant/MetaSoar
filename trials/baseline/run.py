"""The starting agent on BabyAI level families, many seeds each: one result line per episode, then a summary.

    python3 -I trials/baseline/run.py [SEEDS] > .state/trials/baseline/results.jsonl   (in the sandbox image)

Seeds 1000 and up, so they never overlap the judge's held-out cases (generated in Actions, M-05).
"""
import json
import sys
import warnings

sys.path.append("/work")
warnings.filterwarnings("ignore")
from metasoar.play import episode  # noqa: E402

LEVELS = ["BabyAI-GoToRedBallNoDists-v0", "BabyAI-GoToLocal-v0", "BabyAI-PickupLoc-v0", "BabyAI-OpenDoor-v0",
          "BabyAI-PutNextLocal-v0"]
n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
summary = {}
for level in LEVELS:
    rs = [episode({"env": level, "seed": 1000 + i}) for i in range(n)]
    for r in rs:
        print(json.dumps(r))
    summary[level] = {"success": sum(r["success"] for r in rs) / n, "mean_return": round(sum(r["return"] for r in rs) / n, 4),
                      "mean_steps": sum(r["steps"] for r in rs) / n, "stuck": sum(r["stuck_steps"] for r in rs),
                      "mean_seconds": round(sum(r["seconds"] for r in rs) / n, 3)}
print(json.dumps({"summary": summary}), file=sys.stderr)
