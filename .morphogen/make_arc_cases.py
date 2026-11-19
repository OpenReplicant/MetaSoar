"""Generate the held-out ARC-AGI-3 case set (M-09) inside Actions: the 16 public games the split holds out
(never in the public sandbox image), each game's metadata and source carried in its cases, with seeds 0 to 2.

    python3 .morphogen/make_arc_cases.py --out cases/arc3-heldout
"""
import argparse
import hashlib
import json
import logging
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)
from arc_agi import Arcade  # noqa: E402

TRAIN = {"SK48", "S5I5", "TR87", "BP35", "RE86", "DC22", "LS20", "VC33", "SB26"}
SEEDS = (0, 1, 2)
MAX_STEPS = 500

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True, type=Path)
a = ap.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
tmp = Path(tempfile.mkdtemp())
arc = Arcade(environments_dir=str(tmp), recordings_dir=str(tmp / "rec"))
n = 0
with (a.out / "cases.jsonl").open("w") as f:
    for e in sorted(arc.get_environments(), key=lambda e: e.title):
        if e.title.upper() in TRAIN:
            continue
        if arc.make(e.game_id) is None:
            raise SystemExit(f"could not fetch {e.game_id}")
        d = next(tmp.glob(f"{e.game_id.split('-')[0]}/*/metadata.json")).parent
        meta = json.loads((d / "metadata.json").read_text())
        meta.pop("local_dir", None)
        meta.pop("date_downloaded", None)
        src = next(p for p in d.glob("*.py"))
        game = {"metadata": meta, "file": src.name, "source": src.read_text()}
        for s in SEEDS:
            f.write(json.dumps({"id": f"{e.title.lower()}-{s}", "input": {"env": f"arc3:{e.title}", "seed": s, "max_steps": MAX_STEPS, "game": game}, "answer": None}) + "\n")
            n += 1
print(f"{n} cases written")
