"""Which arm plays a case, for Morphogen's judge: a case as JSON on stdin, the result as JSON on stdout.

An ARC-AGI-3 case goes to the atlas prototype (`atlas.play`) when the tree has one, every other case to the Soar
agent (`metasoar.play`). The judge runs this module from the base and from the candidate alike, so on a tree
without `atlas/` nothing changes, and a pull request that adds the atlas is judged against the Soar agent on main.
"""
import json
import sys
import warnings
from pathlib import Path

ATLAS = Path(__file__).resolve().parent.parent / "atlas" / "play.py"


def episode(case: dict) -> dict:
    if str(case.get("env", "")).startswith("arc3:") and ATLAS.is_file():
        from atlas.play import episode as play
    else:
        from metasoar.play import episode as play
    return play(case)


def main():
    warnings.filterwarnings("ignore")
    print(json.dumps(episode(json.loads(sys.stdin.read()))))


if __name__ == "__main__":
    main()
