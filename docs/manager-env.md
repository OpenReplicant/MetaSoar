# The manager as an OpenEnv environment (proposal, 2026-11-28)

**Status:** a proposal from a cloud session, not built. It answers two things the owner said on 2026-11-28:

> "we should be using openenv and building our environments for the benchmarks, so we can act on the test runs as
> though they are training runs, instead of doing all this manually... we designed a system for this kind of stuff."

> "we aren't just looking for a good 'operator' to connect calls, the fully-evolved form is more like a project
> manager juggling multiple projects and an always-attended interface"

The system it refers to is M-20: experiments run on OpenEnv, and Morphogen's kit (map, research, catalog, optimise
behind its judge) improves what runs in them. PM-1a does none of that today: it is a replay script, and the prompt
rounds of 2026-11-28 are hand-run GEPA (`trials/manager-eval/pm1a/gepa.py`).

## What PM-1a measures, and what it misses

PM-1a puts **one** message or event to a fresh manager and scores the first move: the action, the project, and
whether it escalated. That is the switchboard part of the job. A project manager also has to:

- **hold state across a day:** a worker it started at 09:10 reports at 11:40; a decision it opened is answered later;
  the plan it was told at 10:00 changes what "run it again" means at 15:00;
- **juggle:** several projects and workers at once, one writer per project, a queue of work for busy projects;
- **stay attended:** the owner can write at any moment, also while the manager is busy with events, and should get a
  short answer quickly; events should not crowd the owner out;
- **close loops:** every finished worker gets judged, every open decision is followed up, nothing is dropped;
- **interrupt sparingly:** the owner is asked only what only they can decide.

None of these show up in single-turn replays.

## The environment

One OpenEnv environment, `manager-env`, in two tiers sharing one world model.

| | Tier 1: step | Tier 2: day |
| --- | --- | --- |
| Episode | one PM-1a scenario (as now) | a simulated working day: a timed stream of owner messages and worker or supervisor events over several projects |
| World | the stub portfolio | the same portfolio, which persists: workers progress, finish, fail, hit limits, by a script per episode |
| The owner | silent | a simulated owner: answers `desktop_ask` and decisions from a per-episode answer sheet, and keeps sending messages on their own schedule |
| Reward | `score.py`'s routing, per step | per step as tier 1, plus episode terms (below) |
| Data | the 43 PM-1a scenarios now, the 220 v2 after the label review | generated from templates over the v2 scenarios: each day strings 15 to 40 of them together with the events they imply |

**Interface.** OpenEnv 0.3's `MCPEnvironment`: the manager's nine tools are the environment's MCP tools (the stub,
`stub_pm.py`, already defines them), an observation is the incoming message or event plus any tool results, and
`step` is one tool call or the end of a turn. Time is simulated: the clock advances by the manager's measured
seconds, so a slow manager lets messages pile up, and that is what "always attended" is measured against.

**Rewards (OpenEnv rubrics).**

- Per step: routing as PM-1a (action, project, escalation), from `score.py` unchanged.
- Per episode:
  - owner wait: the median and 90th percentile of the time from an owner message to the first reply;
  - dropped loops: finished workers never judged, decisions never followed up, queued work never started;
  - double writers: two writers on one project at once;
  - interruptions: asks and decisions the answer sheet marks as unnecessary;
  - ledger accuracy: answers about state that contradict the world.

The single number optimised is a weighted sum. The weights are the owner's call, and every term is reported
separately.

## What it buys

1. **Test runs become training runs.** OpenEnv's harness (`openenv.core.harness.collect`) writes every rollout as a
   JSONL record with its verification, in the `messages` form TRL's `SFTTrainer` reads. Then:
   - the same runs that measure Haiku produce E-20's training data (d1-2B on Haiku's decisions), and Sonnet's runs
     produce better teacher data;
   - GRPO or rejection sampling on Inkling and LFM3 against the rubric is possible on Kaggle, with no new harness.
2. **Optimisation through the kit, not by hand.** Morphogen's `optimise` (GEPA, as in S-224) gets a cell whose workload
   is `manager-env` episodes and whose scorer is the rubric. Its judge holds out episodes the optimiser never sees, so
   the in-sample problem of the hand-run rounds goes away: tier 1 trains on the failed set, and tier 2's held-out days
   are the gate.
3. **One environment for every arm.** Haiku and Sonnet (Claude Code against the MCP tools), Inkling and LFM3
   (llama.cpp on Kaggle), d1-2B (the choice readout) and later Soar itself (M-01's hook) all run against the same
   episodes and rubric.

## Order, if approved

1. **Tier 1 on OpenEnv:** wrap `stub_pm.py` and `score.py` as `manager-env`. Check that it reproduces PM-1a's numbers
   for the existing traces, so nothing changes in the scoring.
2. **The cell:** a Morphogen catalog entry with its workload and scorer. The 2026-11-28 GEPA rounds re-run through it
   should give the same result as by hand. That needs the Morphogen repository in the session.
3. **Tier 2, first:** a day generator over the 43 scenarios, a scripted worker and owner, the episode rubrics, and 10
   train days and 10 held-out days. Register it in `docs/experiments.md` (purpose and falsifier) before any
   optimisation is judged on it.
4. **Then the v2 scenarios** once their labels are reviewed: more days, and E-20's data from the same rollouts.

## Open questions for the owner

- The episode weights, above all how owner wait trades against interruptions.
- Whether the simulated owner may be an LLM (cheaper to write, but a second model in the loop) or must be scripted
  answer sheets (deterministic, more work).
- Where `manager-env` lives: MetaSoar, where the experiments are registered, or Substrate, which owns the manager.
  This proposal assumes MetaSoar, with Substrate's harness as the source of the tools.

## Tier 2 spec, v1 (2026-11-28; the owner: "don't wait for me so much")

Defaults taken where the open questions above are unanswered: the owner is **scripted** (answer sheets, deterministic);
the episode terms are **reported separately**, with no weighted sum until the owner sets weights; it lives in MetaSoar.

**A day** is a list of arrivals on a simulated clock from 09:00: the owner's messages and the supervisor's and
workers' events. It is built from **storylines**, short sequences whose later arrivals depend on what the manager did
earlier, interleaved by a seed, plus **fillers**: PM-1a scenarios whose label does not depend on state (status
questions, escalations).

**Storylines (v1).** Each has its arrivals, its labels, and the loop it opens:

| Storyline | Arrivals and labels | Loop to close |
| --- | --- | --- |
| experiment | owner asks for a Kaggle run on a project with a running worker → start (kaggle runner); later the started worker's `finished` → start kind judge on it | the judge |
| plan change | owner: stop the running worker → stop; 10 min later owner gives the new plan → start | the new start |
| ambiguous | owner sends a request two projects fit → ask; the scripted answer 5 min after the ask names one → start on it | the start after the answer |
| decision relay | a worker's `needs_input` → decision; the owner answers the decision 20 min later (an arrival of kind `decision.answered`) → message to that worker with the answer | the message |
| queued | owner asks for writing work on a busy project → ask or queued; later that project's worker `finished` → judge, and the queued work started (in that turn or the next) | the queued start |
| limit | a worker's `limited` → nothing; then its `failed` after the second resume → decision | the decision |
| burst | three worker events within 2 minutes, then an owner status question 1 minute later → answer | (owner wait, below) |

Labels that name a worker are resolved at run time: "the worker started in this storyline's first arrival". If that
worker was never started, its later events do not arrive and the storyline's loop counts as dropped.

**World.** One portfolio for the whole day (`stub_pm.Stub`, not reset between turns). Workers the manager starts are
simulated by a seed: a progress report 20 to 60 minutes later, then `finished` (70%), `limited` and then resumed by
the supervisor (15%), or `failed` (15%). A judge worker emits `finished` with a verdict 15 minutes after it starts.
Two writing workers on one project at the same time are recorded (kind judge and kaggle runs are not writers).

**Turns.** One turn per arrival, a fresh model session each time (the portfolio, its notes and open decisions are the
manager's memory, as designed). The clock advances by the turn's measured seconds times `speed` (default 1.0), so a
slow manager lets arrivals queue. The queue order is FIFO; `owner_first: true` is an option (it is a design lever for
"always attended", so it is measured, not assumed).

**Measured, per day:**
- routing per arrival, by `score.score` with each arrival's resolved label (as tier 1);
- owner wait: for each owner message, from its arrival to the first desktop_say, desktop_ask, pm_decision_open or
  pm_worker_start in the turn that handles it (median and 90th percentile, simulated seconds);
- dropped loops: storyline loops still open at the end of the day;
- double writers;
- interruptions: asks and decisions on arrivals whose label expects neither.

**Data.** Days of 15 to 30 arrivals: 10 train days built from the PM-1a texts, and 10 held-out days whose storyline and
filler messages are rewritten by an agent that has not seen the prompts or candidates (same structure, new words and
project details), kept out of every optimisation run.
