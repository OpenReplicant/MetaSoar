"""Download the ARC-AGI-3 training games into the image (M-09). Only the training games: the held-out ones never go
into this public image; they reach the judge's sandbox as case inputs from the private case repository."""
import logging
import sys

logging.disable(logging.CRITICAL)
from arc_agi import Arcade  # noqa: E402

TRAIN = {"SK48", "S5I5", "TR87", "BP35", "RE86", "DC22", "LS20", "VC33", "SB26"}
arc = Arcade(environments_dir=sys.argv[1], recordings_dir="/tmp/arc3-recordings")
got = []
for e in arc.get_environments():
    if e.title.upper() in TRAIN:
        if arc.make(e.game_id) is None:
            sys.exit(f"could not fetch {e.game_id}")
        got.append(e.title)
missing = TRAIN - {g.upper() for g in got}
if missing:
    sys.exit(f"missing training games: {sorted(missing)}")
print("fetched", sorted(got))
