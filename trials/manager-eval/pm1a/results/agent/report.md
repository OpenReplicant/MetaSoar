# PM-1a results, 2026-11-28

Arms: haiku (subagent:haiku), sonnet (subagent:sonnet). Scenarios scored: 43 of 43. Runs per scenario: 1 (the design says 3). Intervals are bootstrap over scenarios (percentile, 95%).

| Metric | haiku | sonnet | haiku minus sonnet, paired 95% |
|---|---|---|---|
| Routing accuracy (project and action) | 88.4% [79, 98]% | 88.4% [79, 98]% | +0.0 pt [+0.0, +0.0] pt |
| Action accuracy | 93.0% [84, 100]% | 93.0% [84, 100]% | +0.0 pt [+0.0, +0.0] pt |
| Project accuracy (where labelled) | 83.3% [69, 96]% | 86.7% [73, 97]% | -3.3 pt [-11.1, +0.0] pt |
| Delegation recall (start/message/stop when expected) | 72.2% [50, 92]% | 72.2% [50, 92]% | +0.0 pt [+0.0, +0.0] pt |
| Delegated when it should not have | 0.0% [0, 0]% | 0.0% [0, 0]% | +0.0 pt [+0.0, +0.0] pt |
| Did the work itself (scenarios: outside tool or >10 lines of code) | 0 [0.0, 0.0] | 0 [0.0, 0.0] | +0.0 [+0.0, +0.0] |
| Escalation precision | 88.9% [72, 100]% | 88.9% [72, 100]% | +0.0 pt [+0.0, +0.0] pt |
| Escalation recall | 100.0% [100, 100]% | 100.0% [100, 100]% | +0.0 pt [+0.0, +0.0] pt |
| Brief fields present (objective, output, boundaries, done_when) | 100.0% [100, 100]% | 100.0% [100, 100]% | +0.0 pt [+0.0, +0.0] pt |
| Runner as labelled (where labelled) | 100.0% [100, 100]% | 100.0% [100, 100]% | +0.0 pt [+0.0, +0.0] pt |
| Reply latency, median s (launch to first desktop_say/ask) | 5.0 [4.2, 5.5] | 5.3 [4.7, 6.0] | -0.3 [-1.3, +0.3] |
| Session wall time, mean s | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | +0.0 [+0.0, +0.0] |
| Tokens per scenario, mean (all input + output) | 0 [0.0, 0.0] | 0 [0.0, 0.0] | +0.0 [+0.0, +0.0] |
| Tool calls per scenario, mean | 1.98 [1.7, 2.3] | 1.98 [1.7, 2.3] | +0.0 [-0.2, +0.3] |

## Falsifier: "haiku is reliable enough"

**Verdict: not refuted on PM-1a's tests; unsettled until test 4 (PM-1b) runs.**

1. Routing-and-delegation accuracy, haiku minus sonnet: +0.0 pt, 95% interval [+0.0, +0.0] pt: not refuted (the interval excludes a 5-point gap).
2. haiku did the work itself in 0 scenario(s) (limit: more than 1): not refuted (replay only).
3. Must-escalate scenarios haiku missed that sonnet got: 0 (limit: more than 1): not refuted (one run, not a majority of three).
4. Live brief quality: PM-1b, not run.

## Scenarios where they differ

| Scenario | Message | Expected | haiku | sonnet |
|---|---|---|---|---|
| s17 | Try the 2B model as the intent parser and compare it with the current  | start metasoar | WRONG: ask metasoar,substrate | WRONG: ask - |
| s21 | Can you write me the SQL for the portfolio tables here in the chat so  | start substrate | WRONG: answer - | WRONG: answer substrate |

## Every wrong routing

| Arm | Scenario | Expected | Did |
|---|---|---|---|
| haiku | s14 | start/ask/queued metasoar | ask - |
| haiku | s17 | start metasoar | ask metasoar,substrate |
| haiku | s18 | start substrate | ask - |
| haiku | s21 | start substrate | answer - |
| haiku | s26 | message/ask metasoar | ask - |
| sonnet | s14 | start/ask/queued metasoar | ask - |
| sonnet | s17 | start metasoar | ask - |
| sonnet | s18 | start substrate | ask - |
| sonnet | s21 | start substrate | answer substrate |
| sonnet | s26 | message/ask metasoar | ask - |

## Checks

- haiku: tool sets offered across runs: [['desktop_ask', 'desktop_say', 'kernel_search', 'pm_decision_open', 'pm_portfolio', 'pm_project_note', 'pm_worker_message', 'pm_worker_start', 'pm_worker_stop']]; models reported: ['haiku']; errors: 0; no desktop_say (closing text only): 16; failed tool calls: 0; scenarios over 8 tool calls: 0.
- sonnet: tool sets offered across runs: [['desktop_ask', 'desktop_say', 'kernel_search', 'pm_decision_open', 'pm_portfolio', 'pm_project_note', 'pm_worker_message', 'pm_worker_start', 'pm_worker_stop']]; models reported: ['sonnet']; errors: 0; no desktop_say (closing text only): 5; failed tool calls: 0; scenarios over 8 tool calls: 0.

## A scorer question (not changed here)

`score.py` scores the project of an `ask` like any other action: an ask that names no project gets `project_ok`
false, even where the label allows `ask` (s14 allows start, ask or queued; s26 allows message or ask). Haiku and
Sonnet both asked without naming a project on s14 and s26, so both would score 40/43 instead of 38/43 if an allowed
ask that names no project were not scored on project (as an `ack` already is not). The Kaggle Inkling and LFM3 runs are
unchanged by that rule (30/43 and 9/43). The scorer is Substrate's (`scripts/trials/manager/score.py`); the change, if
wanted, belongs there first. Until then every number here uses it unchanged.

## m1 (manager.md + prompts/owner-only.md), Haiku subagents, 2026-11-28

33/43 against 38/43 for manager.md; fixed none, changed five: s32 now opens the decision (right action) but names no
project (the scorer's project check fails it); s10 ("merge main into the manager branch", a worker's git step) became a
decision: the rule's "merging" is too broad; s03 and s23 flipped with no relation to the rule (run-to-run noise, 2-3 of
43); r05 is void (the subagent ran two stray commands on it). The rule also quotes s32 ("whatever it costs"), so its
PM-1a score is in-sample. To be rewritten (narrow: approving a pull request or release into main; examples in new words)
and measured on manager-env days, not on 43 single runs.

## In-sample (recorded 2026-11-28)

Every number here for a tuned prompt (p1, p3, p4, m1) is in-sample: the failures that shaped the prompts were read on
these 43 scenarios, and until e836603 the prompts quoted scenario phrases. Kaggle rounds 1 and 2 ran the quoting
versions. Run-to-run variation of one 43-scenario run is 2 to 3 scenarios. The fair test is E-21's held-out days.

## Haiku with the narrowed owner-only rule (m1v2, after e836603)

`pm1a-agent-haiku-m1v2.json`: **39/43** (base 38, m1 33). The narrowing undid all five m1 regressions (s03, s10, s23,
s32, r05; s10 "bring main into the branch" is a worker message again), and s26 also passed. Wrong: s14, s17, s18 (asked
the person instead of starting work), s21 (no move). One point over base is within run-to-run noise (2 to 3 cases), and it
is in-sample: the rule was written after reading these scenarios' failures.

## Kaggle round 2 (pm1a-gepa-r2, commit 7097fe0: the prompts before the rewording; in-sample)

| Candidate | Routing | Baseline (Kaggle, manager.md) | Won | Lost |
| --- | --- | --- | --- | --- |
| inkling-p1 | 35/43 | 30/43 | r01 r06 s09 s14 s21 s29 s30 s33 | s03 s26 s35 |
| inkling-p3 | 34/43 | 30/43 | r01 r04 s09 s21 s29 s30 s31 s32 s33 | s03 s10 s16 s23 s34 |
| inkling-p4 | 33/43 | 30/43 | r01 s09 s14 s21 s29 s30 s31 s33 | s03 s23 s24 s26 s35 |
| lfm3-r1 | 13/43 | 9/43 | r01 r04 s07 s09 s22 s27 s28 s34 | s04 s05 s31 s36 |
| lfm3-r1req | 12/43 | 9/43 | | |
| lfm3-p3router | 9/43 | 9/43 | | |

These prompts quoted scenario phrases, so the gains are an upper bound. The test that counts is E-21 on held-out days.
