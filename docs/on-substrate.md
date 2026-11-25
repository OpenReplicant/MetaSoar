# MetaSoar on Substrate: experiments as changes to the map

A design note, 2026-11-25, proposed and not yet in `DECISIONS.md`. The owner asked whether MetaSoar's next build
should run on Substrate, dogfooding it, and what Substrate needs so that experimental self-modification is mapped
and the map helps rather than gets in the way, if necessary by tracking state in the background without LLM
calls.

## Where the three projects stand

Read from each repository's main on 2026-11-25:

- **Substrate is a default configuration, not a product** (Substrate S-209 to S-218): an agent harness (Claude Code
  first) set up with the Knowledge Kernel and Morphogen's kit. Its old assistant was removed (S-195). The compose
  stack, the gateway (Bifrost) and the two llama.cpp services (`llm`, `llm-fast`, profile `llm`) remain.
- **Morphogen is the kit**: map, research, catalog and optimise, on files only. The map, the options and the cells
  are Backstage entity files (`catalog-info.yaml`), with Morphogen's fields under `spec.morphogen`
  (`schemas/morphogen-spec.v1.json`). At its core is a judge that the optimiser cannot edit. Its rules come from the
  base commit, measurements are taken outside the candidate, paired rounds are decided by a sign test, and every
  verdict goes into a log that cannot be quietly edited.
- **A cell** is `change` (what may change: files, or settings with ranges), `run` (the workload, from the base),
  `better` (the metric and its direction), `tests` (what must keep passing) and `in` (what it belongs to). Optional
  fields are `score`, `observe` (telemetry collected outside the run) and `autonomy`. Morphogen's README already names
  MetaSoar's System 1 skills, each a cell, as a planned consumer of the judge. This settles the handoff's open
  question about what Morphogen calls a cell, from Morphogen's own repository.

## The fit: one lifecycle for skills, settings and components

M-21's lifecycle is proposed, then shadow, then active, with `system1.lock` written by the judge. That is Morphogen's
loop, applied to a System 1 policy:

| M-21 | Morphogen |
| --- | --- |
| a skill's policy, observer or applier | a cell; `change` names its files and settings |
| its cases and their outcomes | `run` and `score`, from the base; held-out cases kept on the operator's machine |
| shadow: run beside the current one, compare | paired rounds against the base, sign test |
| promoted to active; `system1.lock` updated | a pass, merged under the operator's `autonomy`; the verdict in the evidence log |
| audit rate on active skills | re-judging after merge; the ratchet when a cheat is found |

So MetaSoar should not build a judge of its own. The runner, the skills and the decision backends are cells, and an
experiment is a judged change to some of them. Experimental self-modification then needs only what any Morphogen
change needs, plus a map that knows what is running.

## What got in the way today

Before any experiment could run, this session spent about a dozen tool calls finding out facts the map should hold:

- **The engine and models:** whether LM Studio or llama.cpp served the models, which GGUF files, and which image
  build supports Inkling's architecture (b12591 or later; the native build here is b12345).
- **Unrecorded findings:** the thinking switch for each model (Inkling takes `reasoning_effort` as a soft level from
  0 to 0.99 and still thinks at 0; LFM3 takes `enable_thinking` and reasons in its answer when it is off), and the
  fact that both return top log-probabilities.
- **The resource budget:** what fits on the GPU (Inkling with 7 loop layers is about 6.2 GB, LFM3 about 1.9 GB, the
  card 8 GB), so both cannot run there at once.
- **Side effects:** that `lms status` starts LM Studio's background service.

Some of this was in Substrate's `DECISIONS.md` prose and its `.env`, and none of it was queryable. The experiment's
own containers then ran outside compose, so the map no longer matched what was running.

## What the map must do to help

1. **Answer the questions above in one read.** For each component: what runs where, from which image and model file,
   with which settings, on which port, using what share of the GPU and RAM; which trial owns it; and what differs from
   the base. Model facts found by probing, such as the thinking switch, a model's top log-probabilities or its speed,
   go on the model's catalog entry as properties and are written once.
2. **Keep observed state current in the background, with no model calls.** Morphogen's own table has an "observed"
   column (traces, OpenTelemetry) next to each "intended" one. Fill it with small deterministic encoders on a timer or
   a hook:
   - Docker events and `docker inspect`: container, image digest, arguments, ports, mounts.
   - File hashes of the model files.
   - A GPU and RAM snapshot.
   - Git: branch and base commit.
   - The gateway's call log: who called which model, and how often.

   They write observed entity files beside the intended ones, and a diff reports drift. My `docker run` containers
   would have appeared as drift, owned by no trial.
3. **Make writing to the map a side effect of acting.** A trial is started by a launcher that renders its compose
   override from the trial's entity. Running it therefore records it, and stopping it records that too. Hand-written
   catalog files go stale first, so nothing in the experiment path should depend on one.
4. **Report drift; do not block on it.** An experiment must be able to run before the map knows about it. The map
   catches up and says what is unexplained. Only a judged merge needs the map to be right.
5. **Keep the judge's inputs out of the loop's reach.** Held-out cases (for example JevBench's gold answers) stay
   where Morphogen keeps them, not in the cell's `change`.

## A trial, concretely

A trial is a branch plus one entity file. The entity names:

- the cells it changes and their settings ranges;
- its `run`, `score` and `better`;
- the components it needs, with overrides of their settings (for example `llm` with Inkling's experts on the GPU and
  `llm-fast` stopped);
- the data it pins (a dataset and revision).

The launcher renders the compose override and starts it. The observers record what actually ran. The judge's verdict
and the run's outputs go to the evidence log. When the trial ends, its components are stopped and the map shows them
gone.

## The smallest first build

1. **Observed state** (in Substrate, written as a kernel module per Substrate's S-212, or in Morphogen if it belongs
   in the kit): `observe` writes observed component files from Docker, model files, the GPU and git, and `drift`
   compares them with the catalog. There are no model calls; it runs in seconds.
2. **Model facts as catalog properties:** the thinking switch, log-probabilities, speed and memory for Inkling and
   LFM3, from today's probes and S-169.
3. **The trial launcher:** a trial entity, rendered to a compose override over `llm` and `llm-fast`, published on
   localhost only for the trial's lifetime.
4. **The first trial is E-04a** (`docs/decision-backends.md`): our models' readout against Jev's own predictions on
   JevBench cases, as a Morphogen cell.
   - `change`: the backend's prompt template, debiasing and temperature.
   - `run`: the readout over the cases, from the base.
   - `better`: coverage at 5% risk.
   - `tests`: the parse and readout checks.

   It is cheap (one forward pass per case), and it exercises every part above. The template's wording then becomes
   a setting an optimiser such as GEPA may tune behind the judge, which is the open question in
   `docs/typed-questions.md`.

E-04, the runner and E-01 then follow as trials on the same path.

## Open, for the owner

- Where observed state lives: in the kit (Morphogen), so every user gets it, or in Substrate's distribution.
- Whether MetaSoar's runner is built in this repository and catalogued from Substrate, or as a Substrate module.
- How much autonomy MetaSoar's trials get: `review` (the default) or `merge` for shadow-stage cells.

## Not verified here

- Morphogen was read from its README, `BRIEF.md`, the `morphogen` skill and the field names in its schema, not the
  schema's full definitions or the judge's code. Before building, check how `observe` is meant to be used and whether
  a cell can name runtime settings, such as compose arguments, in `change`.
- Substrate's `docs/framework.md` and `docs/parts.md` (the re-cut's shape) were not read in full.
