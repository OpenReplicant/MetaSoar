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

## MS-Eval's own harness: read, not run (2026-11-27)

The owner asked for MS-Eval's Docker harness to be run on Haiku, to compare observed delegation with the
stated decisions above. It was read in full (pinned commit, plus its two submodules at the pinned
revisions: `Danield21/toolathlon_gym` 872ebef, `Danield21/kimi-code` 4aabe61) and **not run**. Observed
Haiku numbers are therefore absent.

### How the harness works

- **Agent framework: Kimi-Code**, not Claude Code (`kimi_harness/kimi_main.py`). One Docker image holds the MCP
  servers and Kimi-Code; a second holds PostgreSQL with the task data. Each task gets a fresh container and database.
- **It needs a model API endpoint** (`API_BASE_URL`, `API_KEY`, `API_FORMAT` = `anthropic` or `openai`). The
  `claude-sonnet-5` preset speaks the Anthropic Messages API through a local gateway. There is no Claude Code
  mode and no subscription-login path.
- **Tools the main agent gets:** only the task's MCP tools, `TodoList`, and (in the delegation arms) `Agent` and
  `AgentSwarm`. Kimi's built-ins (Bash, Read, Write, Edit, Glob, Grep, WebFetch, Browser) are disallowed. The
  agent must finish by calling `claim_done`. Limits in the Sonnet preset: 100 steps, 7,200 s a task.
- **Rosters:** `spec` (the paper's headline arm, "auto-spec"): `plan` plus six domain specialists, each with a
  fixed tool ceiling; `gen`: `coder`, `explore`, `plan`; `sa`: no sub-agents (baseline).
- **Delegation detection:** read from the recorded trace (`raw_stream.jsonl`). A task counts as delegated if the
  main agent launched at least one non-planning sub-agent through `Agent` or `AgentSwarm`; `plan`-only launches
  are excluded (`eval/delegation_appropriateness/evaluate.py`). UDR and ODR need no reviewer model; the LLM
  reviewer (DeepSeek by default) is used only for the hit scores.
- **Scoring:** UDR = need-tasks with no delegation / 89; ODR = no-need tasks that delegated / 77. Labels come
  from the golden Delegation Priors, the same split used in this trial.

### Does the tool design steer toward or away from delegation?

Mostly toward delegation, with the main agent's own tools made narrow, and with a few brakes.

- **Toward:** (1) with Bash, file and web tools removed, the main agent has no way to read or write a file, run
  Python, or fetch a page except through MCP tools; in the spec roster the specialists are the ones with the
  office-document and workflow tools, so "use the matching specialist" is the natural path. (2) The system prompt names
  seven sub-agent types, each with a domain description, and gives seven worked examples, six of which end
  in a launch ("I will launch an `enterprise-data-analyst` agent ..."). Only the first example launches `plan` first.
  (3) Rules say "delegate when a subtask is independent and would otherwise bloat your own context", "when a
  domain specialist matches ... delegate to the narrowest matching profile", and describe parallel launches in detail.
  (4) Every task here is an MCP-heavy office workflow, so a specialist usually matches.
- **Away:** the prompt also says "Delegate only when a subtask requires more than one reasoning step or more than
  one serial tool call, and enables an independently verifiable deliverable", "handle single-step work directly",
  and "when no specialist matches, do the work yourself". Sub-agents are self-contained, so the main agent has to
  write a full brief, which costs steps. Sub-agent prompts and the `claim_done` rule (only the main agent may end the
  task) keep the main agent in the loop.
- **Net (a reading of the prompt, not a measurement):** the `spec` roster plus examples biases a model toward
  launching, so a model that follows the examples closely may over-delegate on short tasks that merely touch
  several named systems. The static prompt in this trial, which offers the choice in one
  sentence with no examples, does not carry that pull.

### Why it was not run

Running it on the subscription means writing an Anthropic-Messages-compatible adapter that answers each Kimi-Code
turn with a `claude -p --model haiku` call and emulates tool calls in text. That is possible in principle and it is not
a small adapter, but the cost decides it:

- From the paper's published Sonnet 5 run on these same 40 tasks (`input_summary.csv`): 2,125 agent steps (mean 53
  a task), 311 M input tokens (mostly cache reads), 9.8 M output tokens, 20 to 70 minutes a task.
- A text adapter cannot use the native prompt cache across steps. Each of about 2,000 sequential calls would resend a
  context that grows to 100 k tokens or more, so the shared Claude subscription would be asked for hundreds of
  millions of input tokens (against 0.2 M for the 40 stated-decision calls). That would drain the owner's shared limit
  and would stop at the first rate-limit error long before 40 tasks finished.
- Besides the model, the run needs a 40 GB image build, 16 GB RAM, a PostgreSQL container per task, and live
  access to the external MCP services some tasks use (arXiv, Yahoo Finance, YouTube, rail data), so a Haiku run would
  also differ from the paper's in the environment.
- Emulated tool calling changes how the model behaves, so delegation measured through it would not be Haiku
  in Kimi-Code with native tool use, which is what the paper measured for Sonnet.

Nothing was built or started: no container, image or `claude` call was made for this part, and no API key was used.

### What can be said from published data instead

MS-Eval published Sonnet 5's per-task observed delegation (`eval/eval_results/claude-sonnet-5/auto-spec/task_metrics.csv`,
sha256 `0effb0ed66fdb27f63703b5de5ed6e554ed3b57f655dc2a8fce72f4bb35fd41f`, saved under `data/published/`). On the
trial's 40 tasks (`compare_sonnet.py`, output `results/stated_vs_sonnet.json`):

| | under-delegation (need tasks, n = 20) | over-delegation (direct tasks, n = 20) |
| --- | --- | --- |
| Haiku 5.5, stated decision (this trial) | 65% (13/20), Wilson [43%, 82%] | 10% (2/20), [3%, 30%] |
| Haiku 5.5, observed in the harness | not run | not run |
| Sonnet 5, observed, same 40 tasks (paper's run) | 30% (6/20), [15%, 52%] | 40% (8/20), [22%, 61%] |
| Sonnet 5, observed, all tasks (paper) | 39.3% (of 89) | 29.8% (of 77) |

Haiku's stated and Sonnet's observed decisions agree on 19 of 40 tasks and differ on 21. In 17 of the 21
Sonnet launched sub-agents and Haiku said it would not: 10 need-tasks (mostly multi-system `terminal-*`, `canvas-course-*`,
`yf-sector-outlook-report`, `ecommerce-commodity-impact`) and 7 direct tasks (`yf-*`, `yt-*`, `wc-category-performance-ppt`
and others). In the other 4 Haiku said delegate and Sonnet did not: `arxiv-research-pipeline-notion-excel`,
`canvas-late-submission-gcal`, `supplier-contract-compliance-audit` (need-tasks) and `howtocook-diet-gform-notion-excel`
(direct). The full list is in `results/stated_vs_sonnet.json`. Different models, so this is not a Haiku-observed diff, and 20 items a side leaves wide intervals. It is
consistent with the prompt pull described above: on direct tasks Sonnet launched sub-agents in 40% of cases against
Haiku's stated 10%, and on need-tasks it skipped delegation less often than Haiku said it would (30% against 65%).

## How to add arms

- **Sonnet 5.5 (the design's comparison arm):** `run_eval.py` with `--model sonnet` in place of the
  hard-coded `haiku` (add a `--model` flag). Same subset, same prompt, same scoring.
- **Inkling 2 and LFM3 (llama.cpp):** `call_haiku` is the only function that talks to a model. Add a
  second caller that posts `PROMPT % request` to the local OpenAI-compatible endpoint with `temperature 0`,
  and write its replies to `results/results-<arm>.jsonl`. Serve them as in `docs/experiments.md` (E-04a).
- **d1-2B (routing choices):** the same caller, with `{"delegate": ...}` replaced by the routing question
  from PM-1's `F` arm.
- **Full-run version:** the paper's harness (`LINs-lab/MS-Eval`, `toolathlon_gym/run_sh_eval/<model>/spec/run.sh`) with
  the arm's model in `config.env`. Needs an API endpoint; see the section above for why it was not run on the subscription.

## Files

- `fetch_msEval.py`: fetch and verify the pinned files.
- `manifest.json`: sha256 of each file read.
- `run_eval.py`: `prepare`, `run` (resumable), `score`.
- `compare_sonnet.py`: stated Haiku decisions against the paper's observed Sonnet 5 delegation.
- `results/subset.json`, `results/results.jsonl`, `results/summary.json`, `results/stated_vs_sonnet.json`.
