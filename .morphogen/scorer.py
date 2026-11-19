"""MetaSoar's scorer (M-05): runs only in the judge's trusted job, on the episode's output as text.

The output is metasoar.play's one line of JSON. A case is correct when the episode succeeded (ended with positive
reward, or the game won). For ARC-AGI-3 `levels` is the levels completed. Its answer is unused: an episode is scored by what the environment said, not by a stored answer.
"""
import json


def score(case_input, answer, output):
    try:
        got = json.loads(output.strip().splitlines()[-1]) if output else None
    except (ValueError, IndexError):
        got = None
    ok = bool(got and got.get("success") is True and got.get("env") == case_input.get("env")
              and got.get("seed") == case_input.get("seed"))
    same = bool(got and got.get("env") == case_input.get("env") and got.get("seed") == case_input.get("seed"))
    levels = float(got.get("return", 0.0)) if same and str(case_input.get("env", "")).startswith("arc3:") else 0.0
    return {"correct": ok, "success": 1.0 if ok else 0.0, "levels": levels}
