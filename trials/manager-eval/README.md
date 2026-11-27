# Manager-eval: Haiku 5.5 on MS-Eval's delegation labels

A static check of whether Claude Haiku 5.5 delegates when it should, run for the manager-agent
design (Substrate `docs/manager-agent.md`, section 8, PM-1). It is a sanity check on one part of
the manager's job. It is not PM-1 and does not replace it.

## Benchmark

**MS-Eval** (Ding et al., arXiv 2610.22869; code at https://github.com/LINs-lab/MS-Eval, MIT licence per its
README; data licence not checked). 166 tasks; 89 are labelled `need_subagent` (the task needs delegation)
and 77 `no_need_subagent`. The labels are MS-Eval's own golden tags, in
`data/task_categories/cluster_by_delegation/`.

Chosen because it is the only candidate that measures the delegate-or-not decision with published
numbers for a Claude model. The others were checked and not used:
- **tau2-bench** (arXiv 2506.07982): the paper page gives no repository, and its scores are for
  a support-agent setting, not delegation.
- **DecisionBench** (arXiv 2605.19099): not fetched; it measures peer choice, not delegation.

## Subset and how it was chosen

- Seed `20261127`, `random.Random(seed).sample` of 20 tasks from each label: 40 items in all.
- Ids and labels are in `results/subset.json`.
- Pinned source: MS-Eval commit `4c1bbd3dc0d736623bba563e56cfd8666f85daac`. `manifest.json` holds the
  sha256 of each file read (171 files); `fetch_msEval.py` refuses any file that does not match.
  Benchmark data goes to `data/` (git-ignored) and is not committed.

## Adapter (what differs from MS-Eval)

MS-Eval runs each task as a full agent run (Kimi-Code harness, Toolathlon-Gym MCP servers and databases,
Docker), then labels what the agent did. That needs a container runtime, live MCP environments and
a reviewer model, so it is not run here. This trial instead poses each task's request once, as a
single decision:

- The request is the task document up to the line `Task-Solving Rationable with Sub-task Decomposition:`.
  Everything from that line is MS-Eval's own golden guidance, which states the answer, so it is removed
  (all 166 documents contain it). Prompts: `run_eval.py`, `PROMPT`.
- Haiku is asked for `{"delegate": true|false, "reason": ...}` with tools disabled (`--tools ""`), so
  the answer is a stated decision, not an observed one.
- Scoring: `UDR` = share of need-subagent items answered `delegate: false`; `ODR` = share of direct
  items answered `delegate: true`. Same definitions as the paper, on this static decision.

## How Haiku was called

`claude -p --model haiku --output-format json --no-session-persistence --tools ""`, prompt on stdin,
run from an empty directory outside the repository. Sequential, 40 calls, no retries, no rate or usage
limit was hit. Every reply, decision, wall time and token count is in `results/results.jsonl`. Token
totals are in `results/summary.json`. The prompts themselves are not committed (they hold benchmark
text); `run_eval.py prepare` rebuilds them from the fetched data, and each file's sha256 is in
`results.jsonl` as `prompt_sha256`.

## Results (Haiku 5.5, n = 40)

| Measure | Haiku 5.5 (static decision) | Published, Sonnet 5 (MS-Eval, full agent runs) |
| --- | --- | --- |
| UDR (need delegation, did not) | 65% (13 of 20), 95% Wilson [43%, 82%] | 39.3% (of 89 need tasks) |
| ODR (no need, delegated) | 10% (2 of 20), 95% Wilson [3%, 30%] | 29.8% (of 77 no-need tasks) |
| Hit accuracy | 62.5% (25 of 40) | hit F1 31.4% (different measure) |
| Unparsed replies | 0 | - |

No Opus model is in the MS-Eval paper, so there is no published Opus number to compare with. The
paper's Sonnet row is `Claude-Sonnet-5` and the manager design names Sonnet 5.5. Sonnet was not run here.

Median wall time per call 2.1 s; 40 calls used about 0.02 USD at API-equivalent rates (subscription
usage, so the money is not spent, but the calls count against the limit).

## Caveats

- **Not comparable on the numbers.** Published rates come from agent runs with tools, an adaptive
  effort setting, and an unstated number of runs. These are one-shot stated decisions with no tools.
  Haiku's 65% is a decision about delegation, not a measured rate of sub-agent launches.
- **Small sample.** 20 items per label; the intervals are wide. The UDR interval's lower end (43%) is
  above Sonnet's published 39.3%, which hints Haiku under-delegates more, but the gap is not
  established.
- **Direction.** Haiku's misses on need items are mostly "the steps depend on each other, so do it in
  one pass", which may be right for many of these tasks. Whether the label or the reading is wrong
  for the thirteen is a question for a human reviewer.
- **Scenario fit.** MS-Eval's tasks are office and data workflows with many tools. PM-1's requests are
  project work across repositories. Use the result as one signal, not as a verdict on PM-1.
- **Prompt sensitivity.** One prompt, one wording of "delegate". No prompt variants were run.

## How to add arms

- **Sonnet 5.5 (the design's comparison arm):** `run_eval.py` with `--model sonnet` in place of the
  hard-coded `haiku` (add a `--model` flag). Same subset, same prompt, same scoring.
- **Inkling 2 and LFM3 (llama.cpp):** `call_haiku` is the only function that talks to a model. Add a
  second caller that posts `PROMPT % request` to the local OpenAI-compatible endpoint with `temperature 0`,
  and write its replies to `results/results-<arm>.jsonl`. Serve them as in `docs/experiments.md` (E-04a).
- **d1-2B (routing choices):** the same caller, with `{"delegate": ...}` replaced by the routing question
  from PM-1's `F` arm.
- **Full-run version:** the paper's harness (`LINs-lab/MS-Eval`, `spec/run.sh`) with the arm's model in
  `config.env`. Needs Docker and a reviewer model key; not attempted here.

## Files

- `fetch_msEval.py`: fetch and verify the pinned files.
- `manifest.json`: sha256 of each file read.
- `run_eval.py`: `prepare`, `run` (resumable), `score`.
- `results/subset.json`, `results/results.jsonl`, `results/summary.json`.
