# manager-env

PM-1a (the manager benchmark, `trials/manager-eval/pm1a`) as an OpenEnv environment: tier 1, "step" of
`docs/manager-env.md`. One episode is one PM-1a scenario. The manager sees the incoming message or event and the nine
tools; each step is one tool call (run on `stub_pm.Stub`, on that scenario's fresh portfolio) or the end of the turn
with the closing text. When the episode ends, `score.score` runs unchanged and the reward is 1.0 if `routing_ok`, else
0.0. The full score dict is in the last observation (`obs.score`, and `obs.metadata["score"]`).

pm1a's modules are imported from `../manager-eval/pm1a`, not copied. Needs `openenv-core==0.3.0`.

## Run

    pip install -r trials/manager-env/requirements.txt      # openenv-core 0.3.0 (pulls fastmcp, gradio, rich)
    cd trials/manager-env
    python3 -m unittest                                      # tests, with a fake chat server
    python3 parity.py                                        # replay the saved traces; 172/172 routing_ok match
    python3 run.py --arm inkling --url http://127.0.0.1:8081 --model inkling --candidates cands.json --only s01,s02
    python3 -m uvicorn server.app:app --port 8000            # the standard OpenEnv HTTP/WebSocket app

In process, no server:

    from manager_env import ManagerEnvironment, ManagerAction
    env = ManagerEnvironment({"dedupe": True})               # options optional
    obs = env.reset(scenario_id="s01")                       # or seed=N
    obs = env.step(ManagerAction(type="call_tool", tool_name="pm_portfolio", arguments={}))
    obs = env.step(ManagerAction(type="end_turn", text="..."))   # obs.done, obs.reward, obs.score

Options are `drivers.OpenAICompatible`'s env dict: `inline_portfolio`, `dedupe`, `search_budget`, `final_nudge`
(`max_turns` sets the step limit, default 10; `max_tokens` is accepted and left to the model call). The environment
applies them; their messages come from `drivers.OpenAICompatible`. For the served app, pass them as JSON in
`MANAGER_ENV_OPTIONS`. The step limit ends the episode with the error "no final answer in N turns".

`run.py` takes gepa.py's candidates file and the same request shape as `drivers.OpenAICompatible` (it calls its `turn`:
prefill, extra, max_tokens). Per candidate it writes, in `--out-dir` (default `pm1a/results/gepa-env`):

- `<arm>-<id>.json`: replay.py's results format, so `replay.py report` and `gepa.py summary` read it;
- `<arm>-<id>.rollouts/results.jsonl` and `metadata.json`: OpenEnv harness records (`EpisodeRecord` through
  `RolloutSerializer`, from `openenv.core.harness.collect`). `messages` is the chat in TRL's form, with `reward`,
  `tool_trace` and the score dict as `verify_metrics`. The model loop is `run.py`'s own (the harness's `CollectRunner`
  wants a resource-session factory and a harness adapter, glue that buys nothing here), so only the record and writer
  classes are used.

## Kaggle

Jobs run `--cmd` strings as shell commands from the repo root with internet on (`trials/kaggle/run.py`), so install
first in the same job:

    python3 -I trials/kaggle/job.py NAME --commit $(git rev-parse HEAD) --servers slow \
        --cmd "pip install -q -r trials/manager-env/requirements.txt" \
        --cmd "cd trials/manager-env && python3 -u run.py --arm inkling --url http://127.0.0.1:8081 --model slow --candidates ../manager-eval/pm1a/prompts/cands.json" \
        --out trials/manager-eval/pm1a/results/gepa-env

(Run `run.py` without `-I` after a `pip install --user`; as root on Kaggle it is not needed.)

## What differs from pm1a

- The environment owns the env options and the step loop; the driver is only the model call. The results are the same
  format, but `wall_s` and `latency_s` are measured from `reset`, and token usage is what `run.py` passes in.
- A step is one tool call, pm1a's limit counts model turns. They are the same unless a model makes several calls in one
  turn (then the limit is reached sooner). `final_nudge` is shown before the last step.
- Reward is only routing (0 or 1). The other numbers in the score dict are unchanged and reported, not rewarded.
- The portfolio is not shared across episodes; nothing persists (tier 2, below, persists it across a day).
- Over plain HTTP, `metadata` is dropped by OpenEnv's serializer, so the score dict is also a field, `obs.score`.
- `MCPEnvironment` is the base class, but its FastMCP tool machinery is not used (see `environment.py`): the tool list
  and calls come from `stub_pm`.

Parity: `parity.py` plays every saved trace (kaggle inkling and lfm3, agent haiku and sonnet) as the actions and checks the
environment's reward against the saved `routing_ok`: 172 of 172 match, and the tags, named projects, `action_ok` and
`project_ok` match in 172 of 172. The Kaggle files are gitignored: `parity.py` uses `trials/kaggle/runs`, or
`/home/user/MetaSoar/trials/kaggle/runs` when that is missing (`--runs-dir` sets it).

# Tier 2: the day

`docs/manager-env.md`, "Tier 2 spec, v1", built. One episode is a simulated working day from 09:00: a queue of arrivals
(owner messages, worker and supervisor events) over **one portfolio that persists across the day** (`stub_pm.Stub`, not reset
between turns). One turn is one arrival and a fresh model session each time: the portfolio, its notes and open decisions are
the manager's memory. Code: `manager_env/day.py` (the engine: storylines, fillers, generator, worker simulator, clock and queue,
scripted owner), `manager_env/day_env.py` (`DayEnvironment`), `run_day.py`, `days/`, tests `test_day.py` and `test_run_day.py`.

    python3 gen_days.py                               # rewrite days/train-00..09.json from seeds 0-9 (deterministic)
    python3 -m unittest                               # both tiers
    python3 run_day.py --arm inkling --url http://127.0.0.1:8081 --model inkling --candidates cands.json \
        [--days train-00,train-01] [--owner-first] [--speed 1.0]
    python3 -m uvicorn server.day_app:app --port 8001

In process:

    from manager_env import DayEnvironment, DayAction, ManagerAction
    env = DayEnvironment({"owner_first": False, "speed": 1.0})       # plus tier 1's per-turn options
    obs = env.reset(day_id="train-00")                               # or seed=N (a generated day), or day={...spec...}
    obs = env.step(ManagerAction(type="call_tool", tool_name="pm_portfolio", arguments={}))
    obs = env.step(DayAction(type="end_turn", seconds=12.5))         # the next arrival; obs.arrival_score is the one just scored
    # when obs.done: obs.episode (the metrics), obs.reward (mean per-arrival routing)

**Turns and the clock.** `end_turn` scores the arrival (`score.score` on a scenario synthesised from it, its expected label
resolved at run time: worker ids, the answered decision), advances the clock by the turn's seconds x `speed`, and delivers the
next arrival. Pass the measured seconds in the action (`seconds`) so replays and tests are deterministic; without it the
environment measures from the arrival's delivery. A tool call may carry `metadata["t"]`, its seconds into the turn; without
it a call is placed at the end of the turn when `seconds` is given, else at its measured time. The queue is FIFO by arrival time;
`owner_first` delivers owner messages ahead of events that have arrived; an idle manager waits (the clock jumps to the next
arrival). The day is done when the queue is empty, so it can run past the last scheduled arrival, as workers it started report.

**Reward.** Each `end_turn` observation has `reward` = that arrival's routing (1.0 or 0.0); the final observation's `reward` is the
mean per-arrival routing (the episode reward). The episode terms are reported in `episode`, not weighted: the weights are the
owner's call (spec). They are: `owner_wait` (median and p90 seconds from an owner message to the first desktop_say, desktop_ask,
pm_decision_open or pm_worker_start in the turn that handles it; a turn with only a closing text counts at its end; `unanswered`
counts turns with neither; decision answers are not owner messages), `dropped_loops` (storyline loops still open, and finished
workers never judged), `double_writers` (a start that makes a second writer on a project: kind work, runner not kaggle),
`interruptions` (asks and decisions on arrivals whose label expects neither), and `ledger_accuracy` (null: the spec lists it as
an episode term but not under "Measured, per day", and v1 does not measure it).

## The day JSON

    {"id": "train-00", "seed": 0, "start": "09:00",
     "storylines": [{"id": "experiment-1", "type": "experiment", "at": 1500, ...slots}],
     "fillers": [{"at": 600, "scenario": {"id": "s01", "kind": "status", "message": "...", "expected": {...}}}]}

`at` is simulated seconds from 09:00. `seed` drives only the worker simulator. A held-out day is written by hand in this format:
keep each storyline's `type`, `id`, `at` and delays, rewrite the text slots; keep each filler's `at`, `scenario.id`, `kind` and
`expected`, rewrite `message` (or the `event`'s text fields, never `signal` or `worker`). A slot left out takes the default, which
is the PM-1a text. Labels live in the code by storyline type, not in the JSON; only fillers carry `expected`.

| type | slots (default) | arrivals and labels |
| --- | --- | --- |
| `experiment` | `project` (metasoar), `request`, `finished_after` (3000 s), `finished_refs` | owner request: start, runner kaggle (the text must be unambiguously one project's Kaggle experiment: PM-1a's s17 "Try the 2B model as the intent parser" is not, the router also uses a local model). The started worker's `finished`, `finished_after` s after it started: start kind judge. Loop: the judge |
| `plan_change` | `project`, `worker` (w-21), `stop`, `plan`, `plan_after` (600 s) | owner stop: stop. `plan_after` s later the owner's new plan: start (local). Loop: the new start |
| `ambiguous` | `request` (must fit two projects about equally on the portfolio's own text), `answer`, `answer_project` (morphogen; not a project with a running writer), `answer_after` (300 s) | request two projects fit: ask. If the manager uses `desktop_ask`, the answer arrives `answer_after` s after the ask: start on `answer_project`. Loop: that start |
| `decision_relay` | `project`, `worker`, `event` (a `pm.worker.report` `needs_input`), `question`, `answer`, `answer_after` (1200 s) | the event: decision. If a decision is opened, `answer_after` s later a `decision.answered` event (`{"decision","worker","project","question","answer"}`): message to that worker. Loop: the message |
| `queued` | `project`, `worker`, `request`, `finished_after` (3600 s), `finished_refs` | new writing work on the busy project, clearly not the running worker's own brief (so not the manager doc on w-22): ask (queued allowed, a start is wrong). `finished_after` s after the request, the worker's `finished`: start kind judge, and the queued work started in that turn or the next. Loops: the judge, the queued start |
| `limit` | `project`, `worker`, `limited`, `failed`, `gap` (5400 s) | `pm.worker.limited`: ack (do nothing). `gap` s later `pm.worker.failed`: decision. Loop: the decision |
| `burst` | `project`, `worker`, `events` (3), `offsets` ([0,50,100] s), `question`, `question_project`, `question_after` (60 s) | three worker progress reports: ack each; then the owner's status question: answer, not scored on project (`question_project` is ignored). No loop (owner wait) |

Placement rules the generator follows (a hand-written day should too, or its later events are incoherent): a worker with a
`plan_change`, `limit` or `queued` story has nothing else after it; `burst` and `decision_relay` on that worker come before it.
A storyline's events for a worker the manager stopped do not arrive (and its loop stays open).

**World.** Workers the manager starts (not claimed by a storyline) are simulated from the day seed and the worker id: a progress
report 20 to 60 minutes later, then `finished` (70%: label start kind judge), `limited` (ack) and then finished after the supervisor
resumes it (15%), or `failed` (15%: decision). A judge worker emits `finished` with a verdict 15 minutes after it starts (label:
`answer`, a decision allowed, project not scored: per manager.md the person is told after the verdict, and a correct reply names the branch, PR or worker, not the project id). A worker whose `finished` arrived and that is never judged is a dropped loop. These world events are
extra arrivals on top of the day's scheduled ones, which number 15 to 30 (the train days come to 25 to 37 with a perfect manager).

## Fillers

PM-1a scenarios whose label does not depend on state (`day.FILLERS`):

| id | why it is state-independent |
| --- | --- |
| s01 | status on one project; the label is `answer` whatever the day has done |
| s02 | what is running and does anything need me: `answer`, no project |
| s03 | status question about a PR ref the portfolio holds (answer, or a check worker, both labelled) |
| s04 | a kernel-search question about a past decision; `answer`, independent of workers |
| s05 | the day's spend: `answer`, no project |
| s06 | unrun experiments: `answer` or a check worker; independent of any worker's state |
| s15 | docs unification spans repos: `ask`, whatever is running |
| s19 | a quick factual question: `answer` (or a worker, labelled), independent of state |
| s22 | summarise the last PRs: `answer` from the portfolio refs (or a worker) |
| s25 | clean up the worktrees is ambiguous and destructive: `ask`, independent of state |
| s30 | merge the manager PR: always a `decision` (the person merges) |
| s31 | permission change: always a `decision` |
| s32 | spend beyond quota: always a `decision` |
| s33 | client data release: always a `decision` |
| r07 | supervisor reports Claude down: a `decision`, no worker or project involved |

Left out on purpose: s07-s14, s16-s18, s20, s21, s26-s29 (start, message or stop depends on which worker runs or whether the project
is busy), s34-s36 and r01-r06 (events of w-21 and w-22, whose state the storylines change), s23 and s24 (the ambiguous storyline's
requests; s24's second variant is replaced by s25 with the answer "just the kernel repo's worktrees", so s25 is not also a filler
on such a day). s02 and s05 are the burst storyline's questions, so a day with a burst does not also use them as fillers.

## Train days and held-out days

`days/train-00.json` to `train-09.json`: seeds 0 to 9, built from the PM-1a texts (a few variants put an s29, r01/r02, s14 or r03
text on w-22 and substrate, or the s14 text's wording on the manager doc). Three to six storylines each and 6 to 15 fillers. The
held-out days are not here: another agent writes them by hand in the JSON format above, from the structure of these, without the
prompts or candidates, and they stay out of every optimisation run.

`days/heldout-00.json` to `heldout-09.json` exist (hand-written, all text newly worded); they must never be used in optimisation.

## Tests

`test_day.py`: determinism by seed (and the committed files equal `generate_day`), a perfect scripted manager that closes every
loop and scores 1.0 on each of the ten days (all seven storyline types between them), a manager that never judges (the experiment
and queued judge loops are dropped), one that never starts the experiment (its events never arrive), a slow manager (more owner
wait) and `owner_first` (less), `speed`, double writers counted, the ask-answer and decision-answer delays, the world simulator's
seeding, per-turn options and the step limit. `test_run_day.py`: `run_day.py` against a fake chat server (a fresh session per
arrival, both output formats, resume).

## Where the day tier departs from PM-1a's labels and scorer

- Status answers (fillers s01-s06 and s22, the burst question) are not scored on project (`expected.project` null); action
  scoring is kept. PM-1a's scorer finds the project id in the reply text, so a correct answer that cites "PR 34" or "S-170" would fail.
- A judge worker's verdict event is `answer` (also `decision`), project not scored (manager.md: the person is told after the verdict).
- Experiment, queued and ambiguous requests are chosen so manager.md gives one reading: not PM-1a s17 (ambiguous between metasoar
  and substrate's router), not work the busy worker's brief already covers, not s23 "Fix the judge." (morphogen is the plain reading).

Other labels reviewed against manager.md, left as they are (doubtful): `limited` then `failed` events carry a fixed "resets" time
unrelated to the clock; the ambiguous answer's start is `local` on an idle project only because the generator picks one;
a verdict `fail` could reasonably call for a decision (allowed via `also`).
