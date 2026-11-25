"""The workload for Morphogen's kit (the cells in catalog-info.yaml): play every case it is given, one line each.

    MORPHOGEN_INPUTS=/outside/babyai-inputs python .morphogen/bench.py

Reads cases.jsonl (one case a line: id, input, answer) from the directory the judge names (MORPHOGEN_INPUTS; the
operator's uncommitted morphogen.local.yaml names it, outside the repository) and plays each case's input as the
GitHub judge does: as JSON on stdin of `python -m metasoar.arm` in a process of its own, at most CASE_SECONDS a case.
Prints `id<TAB>last line of the episode's output` per case (empty when the episode failed or ran out of time), then a
closing line that is not JSON (the kit keeps a last JSON line as what the run says about itself, not for the scorer).
It computes no score: score.py does, from the base, for the cases of the set it is given.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASE_SECONDS = 60   # the GitHub judge's case-timeout (morphogen.yml)

n = 0
for line in (Path(os.environ["MORPHOGEN_INPUTS"]) / "cases.jsonl").read_text().splitlines():
    if not line.strip():
        continue
    case = json.loads(line)
    try:
        r = subprocess.run([sys.executable, "-m", "metasoar.arm"], input=json.dumps(case["input"]), cwd=ROOT,
                           capture_output=True, text=True, timeout=CASE_SECONDS)
        out = r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ""
    except subprocess.TimeoutExpired:
        out = ""
    print(f"{case['id']}\t{out}", flush=True)
    n += 1
print(f"{n} cases played")
