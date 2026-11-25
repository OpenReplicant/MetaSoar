"""The kit's scorer (the cells in catalog-info.yaml): bench.py's output on stdin, one JSON object of metrics out.

The judge runs it from the base, in its own process, with MORPHOGEN_PRIVATE naming a directory outside the repository
that holds the set's cases.jsonl: the held-out set for verdicts, the search set for probes. Each case is scored by
scorer.py's `score` (the GitHub judge's scorer, unchanged); lines for cases outside the set are ignored, so one run
can play both sets. Prints the means of `success` and `levels` over the set's cases, and cases_seen and
cases_expected, so the judge refuses a run that skipped cases.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scorer import score  # noqa: E402

cases = {}
for line in (Path(os.environ["MORPHOGEN_PRIVATE"]) / "cases.jsonl").read_text().splitlines():
    if line.strip():
        c = json.loads(line)
        cases[c["id"]] = c
outputs = {}
for line in sys.stdin:
    cid, sep, out = line.rstrip("\n").partition("\t")
    if sep and cid in cases:
        outputs[cid] = out
totals = {"success": 0.0, "levels": 0.0}
for cid, c in cases.items():
    got = score(c["input"], c.get("answer"), outputs.get(cid) or None)
    for k in totals:
        totals[k] += float(got.get(k, 0.0))
n = len(cases) or 1
print(json.dumps({**{k: v / n for k, v in totals.items()}, "cases_seen": len(outputs), "cases_expected": len(cases)}))
