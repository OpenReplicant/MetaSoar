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
- The portfolio is not shared across episodes; nothing persists. Tier 2 (a simulated day) is not built.
- Over plain HTTP, `metadata` is dropped by OpenEnv's serializer, so the score dict is also a field, `obs.score`.
- `MCPEnvironment` is the base class, but its FastMCP tool machinery is not used (see `environment.py`): the tool list
  and calls come from `stub_pm`.

Parity: `parity.py` plays every saved trace (kaggle inkling and lfm3, agent haiku and sonnet) as the actions and checks the
environment's reward against the saved `routing_ok`: 172 of 172 match, and the tags, named projects, `action_ok` and
`project_ok` match in 172 of 172. The Kaggle files are gitignored: `parity.py` uses `trials/kaggle/runs`, or
`/home/user/MetaSoar/trials/kaggle/runs` when that is missing (`--runs-dir` sets it).
