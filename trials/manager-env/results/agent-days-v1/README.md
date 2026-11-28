# Subagents as the manager on the v1 train days (2026-11-28)

Haiku 5.5 on train-00 to 07 and Sonnet 5.5 on train-00 to 05, played through `agent_day.py` (one subagent per day, so it
remembers earlier turns; 30 s a turn). These runs found the label flaws fixed in 8c65702 and after: an ambiguous
experiment request (s17), queued work the running worker already owned, judge verdicts labelled as decisions, status
answers and correct asks scored on whether their text named the project id, and "Fix the judge" read plainly as
morphogen's. Their days' texts changed since, so only train-05 replays (`*.v3.json`: Haiku 0.913, misses s32 and s30;
Sonnet 1.000). The other files are kept as the record of what found the flaws, scored on the old labels.
