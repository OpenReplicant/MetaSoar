# Subagents on the fixed days (after 8c65702 and b2aabe0)

train-00: Sonnet 32/33 (miss: s30, the merge request answered without a decision; queued work never started), Haiku 32/35 (misses: s30 and s32 without a decision; one judge verdict not passed on).

After b2aabe0+1 (the queued work may start any time after the worker finished, also with the verdict): Haiku 33/35, dropped 0 (misses s30, s32: merge and spend without a decision); Sonnet 32/33 (miss s30), dropped 1 (it never started the queued work).

## m1 (manager.md + the owner-only rule) against manager.md, Haiku subagents, fixed days

| Day | manager.md | m1 | s30/s32 (merge, spend) |
|---|---|---|---|
| train-00 | 33/35 | 34/35 | missed both → both right |
| train-02 | 20/25 | 22/25 | missed both → both right |
| train-05 | 21/23 | 20/23 | missed both → both right; three other arrivals lost (no relation to the rule) |
| train-07 | 30/31 | 28/31 | right → s32 opened as a decision without the project argument (scored wrong) |
| total | 104/114 | 104/114 | |

The rule fixes the targeted misses (every merge and spend request in these days became a decision), and the totals are
equal: the rest is run-to-run noise (two to three arrivals a day) and two decisions with no project argument, which the
project check fails although their text names the project's worker. On PM-1a's 43 it broke s10 (a git merge of main
into a worker's branch became a decision): the rule's "merging" is too broad. The rule also quotes s32's words.

## Re-scored with the reference check (manager_env.refs)

The loosenings are removed: fillers keep their PM-1a project, the queued ask and the burst question are scored on project,
and the judge verdict's project is the judged worker's. Instead, a reply that names a worker, PR, branch, decision or an
id found in only one project's records (w-31, PR 34, claude/e19, d-2, E-19) counts as naming that project.
`score.py` is unchanged; tier 1 applies the check only with the option `project_refs` (off, so parity stays 172/172).
`*.refs.json` are the replays of each `*.moves.json` under the current code (v1 runs played older day texts and are not
re-scored).

| Run | Before | With refs |
| --- | --- | --- |
| day2 haiku train-00 | 32/35 | 33/35 |
| day2 sonnet train-00 | 32/33 | 32/33 |
| day3 haiku base train-02 | 20/25 | 20/25 |
| day3 haiku base train-07 | 30/31 | 29/31 |
| day3 haiku m1 train-00 | 34/35 | 34/35 |
| day3 haiku m1 train-02 | 22/25 | 22/25 |
| day3 haiku m1 train-05 | 20/23 | 20/23 |
| day3 haiku m1 train-07 | 28/31 | 29/31 |

The check is stricter where the loosenings were (one base arrival now fails on project) and kinder where a reply used a
reference: totals are about unchanged, so the loosenings were not hiding much and the stricter rule costs little.
