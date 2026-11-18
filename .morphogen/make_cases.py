"""Generate the held-out case set (M-05): BabyAI level families, each with seeds drawn from a secret seed, so the
seeds exist only inside the Actions run that makes them and in the private case repository.

    SEED=... python3 .morphogen/make_cases.py --seed-env SEED --out cases/babyai-heldout
"""
import argparse
import json
import os
import random
from pathlib import Path

LEVELS = {"redball": "BabyAI-GoToRedBallNoDists-v0", "goto": "BabyAI-GoToLocal-v0", "pickup": "BabyAI-PickupLoc-v0",
          "open": "BabyAI-OpenDoor-v0", "putnext": "BabyAI-PutNextLocal-v0"}
PER_LEVEL = 12

ap = argparse.ArgumentParser()
ap.add_argument("--seed-env", required=True)
ap.add_argument("--out", required=True, type=Path)
a = ap.parse_args()
rng = random.Random(os.environ[a.seed_env])
a.out.mkdir(parents=True, exist_ok=False)
with (a.out / "cases.jsonl").open("w") as f:
    for short, env in LEVELS.items():
        for i in range(PER_LEVEL):
            seed = rng.randrange(10_000, 2**31)
            f.write(json.dumps({"id": f"{short}-{i:02d}", "input": {"env": env, "seed": seed}, "answer": None}) + "\n")
print(f"{len(LEVELS) * PER_LEVEL} cases written")
