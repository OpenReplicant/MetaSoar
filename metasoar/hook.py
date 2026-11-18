"""The impasse hook (docs/spec.md; M-03, M-06): watches the agent from outside, and when it is stuck or keeps
failing, writes what it saw and the request Substrate gets.

    python3 -I -m metasoar.hook collect [EPISODES_PER_LEVEL]   # in the sandbox image, /work the checkout
    python3 -m metasoar.hook request REPORT.json                # the request for Substrate, as text

It fires on two things, and only these (its settings are the judge's, not the agent's):
- **stuck**: a step where Soar wrote no action within `patience` decisions (Soar's own max-nil-output-cycles)
- **failing**: a level family whose training episodes fail at least FAIL_RATE of the time
Training episodes use seeds 2000 and up; the judge's held-out seeds are drawn above 10000 inside Actions and never
seen here. Until Substrate's MCP server exists (its blueprint), the request is given to a Claude Code session with
Substrate's skills, which answers it with a pull request carrying a Morphogen card.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

LEVELS = ["BabyAI-GoToRedBallNoDists-v0", "BabyAI-GoToLocal-v0", "BabyAI-PickupLoc-v0", "BabyAI-OpenDoor-v0",
          "BabyAI-PutNextLocal-v0"]
FAIL_RATE = 0.5
TRAIN_SEED = 2000
OUT = Path("/out")


def collect(per_level: int) -> dict:
    sys.path.append("/work")
    warnings.filterwarnings("ignore")
    from metasoar.play import episode
    levels, triggers = {}, []
    for li, level in enumerate(LEVELS):
        rs = [episode({"env": level, "seed": TRAIN_SEED + li * 1000 + i, "trace": True}) for i in range(per_level)]
        fails = [r for r in rs if not r["success"]]
        stuck = [r for r in rs if r["stuck_steps"]]
        levels[level] = {"episodes": per_level, "success": round(1 - len(fails) / per_level, 3), "stuck": len(stuck)}
        if stuck:
            triggers.append({"kind": "stuck", "level": level, "examples": stuck[:3]})
        if len(fails) / per_level >= FAIL_RATE:
            ex = [{k: r[k] for k in ("seed", "mission", "steps", "return")} | {"first_actions": r["actions"][:20]} for r in fails[:3]]
            triggers.append({"kind": "failing", "level": level, "fail_rate": round(len(fails) / per_level, 3), "examples": ex})
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "levels": levels, "triggers": triggers}


REQUEST = """# A request to Substrate, from MetaSoar's hook

**Intent:** the agent in OpenReplicant/MetaSoar plays BabyAI better: it {why}.
**How it will be judged (from MetaSoar's base, not this request):** Morphogen, on the held-out case set
`babyai-heldout`; KPIs `success` (decides, higher) and `wall_seconds` (bounds). See `.morphogen/policy.json`.
**What may change:** `agent/**` only (Soar rules, sourced from `agent/main.soar`); everything else is the judge's.
**The pull request** must carry exactly one `morphogen-card` block naming `agent/**` as scope and the case set and
KPIs above (docs: Morphogen's `docs/cards.md`).

## What the hook saw ({at})

{levels}

{triggers}

The adapter's input link and output link are described in `metasoar/adapter.py`; the environments are Minigrid's
(its source documents the observation's encoding).
"""


def request(report: dict) -> str:
    failing = [t["level"] for t in report["triggers"] if t["kind"] == "failing"]
    stuck = [t["level"] for t in report["triggers"] if t["kind"] == "stuck"]
    why = "; ".join(x for x in (f"fails most training episodes of {', '.join(failing)}" if failing else "",
                                f"gets stuck in {', '.join(stuck)}" if stuck else "") if x) or "has nothing to report"
    levels = "\n".join(f"- {k}: success {v['success']} over {v['episodes']} episodes, {v['stuck']} stuck" for k, v in report["levels"].items())
    trig = "\n".join(f"- **{t['kind']}** in {t['level']}: " + json.dumps(t["examples"][:2]) for t in report["triggers"])
    return REQUEST.format(why=why, at=report["at"], levels=levels, triggers=trig or "(no triggers)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "collect":
        r = collect(int(sys.argv[2]) if len(sys.argv) > 2 else 20)
        OUT.mkdir(parents=True, exist_ok=True)
        f = OUT / f"report-{r['at'].replace(':', '')}.json"
        f.write_text(json.dumps(r, indent=1))
        print(f.name)
    elif cmd == "request":
        print(request(json.loads(Path(sys.argv[2]).read_text())))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
