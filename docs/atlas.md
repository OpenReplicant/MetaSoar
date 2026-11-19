# An atlas of local models (a proposal, 2026-11-19)

A proposal for the owner, written to be carried into Substrate. It comes from what MetaSoar's ARC-AGI-3 work
showed, read against Substrate's `docs/framework.md` and `DECISIONS.md` (read 2026-11-19 from
`OpenReplicant/substrate` at `fd3a9b4`). Nothing here is decided.

## In one paragraph

A system learns a new environment by keeping an **atlas**: a graph of claims about what is there, how it behaves
and what acting does, where each region of the graph is covered by a **local model** (a rule, a pipeline, a
learned network, a physics engine, a program, a language model's prior) with a stated scope and a measured record.
Models compete for their scope on how well they predict and what they cost; a **generalist** (an LLM, a vision
model) covers what nothing cheaper covers yet, and **teaches**: where it keeps doing the same narrow job, a
specialist is built, trialled against it on that scope, and takes over when it matches. What survives in one
environment is offered to the next. This is a pattern for governing components, so it belongs to Substrate's core;
which models to start with, how to route and what counts as surprise are opinions about cognition, kept apart
and tested.

## Why: what MetaSoar showed

- **The learner was the language model, not Soar.** Every gain came from a model (me) reading traces and writing
  rules and perception. Soar's own learning was never used, and could not have found game mechanics: chunking
  compiles deliberation that already exists; RL tunes preferences over features someone designed.
- **Hand-built rules overfit.** PR #6 took the training games from 40 to 64 levels (LS20 0 to 20/20) and was
  refused on held-out games: 2 better, 0 worse, 46 tied (p 0.25). The judge did its job.
- **The hard part was representation.** Most effort went into perception (objects, what the player controls,
  what counts as a scene change, walls) and into a map of what actions do. Spatial and numeric work moved to
  Python because it was too costly as Soar rules (matching cost, M-12).
- **Failure was quiet, not an impasse.** On unknown games the agent never stalled; it acted confidently without
  understanding. A hook on Soar's impasses would rarely fire on the failures that matter. Surprise (an observation
  a model cannot explain) is the trigger that would.
- **ARC-AGI-3 rewards learning within a game.** Each held-out game is new; only what is truly general carries.
- **Training totals are partly chance.** Runs are deterministic per seed but chaotic: a ±2 in a game that scores
  2/20 is noise. Count games improved and games regressed, not levels summed.
- **The judge is nearly blind at the floor.** With most cases at 0 levels on both sides, almost everything ties.
  A measure with a gradient (progress within a level) is needed before any author's changes can be judged.

## Substrate already has most of it

| Substrate's framework | Soar | In the atlas |
|---|---|---|
| the store and claim log, a blackboard every actor reads | working memory | the graph of claims |
| components with a trigger and an action | productions | local models with a scope |
| escalation when no trigger fires or an event is outside what was judged | impasse, substate | fall back to the generalist |
| distilling the LLM's repeated decisions into components | chunking | the generalist teaches, a specialist takes over |
| confidence measured on held-out cases within the trigger's scope | none | each model's record decides where it is trusted |
| adaptive perception: the LLM builds a pipeline for a stream it cannot handle | none | the system builds its own senses |
| maps, roles, interfaces, catalogs | none | which model covers what, and the candidates |
| fast and slow perception paths | none | the time-scale hierarchy |

The resemblance to Soar is why Substrate's cognition ideas looked like Soar, and the bottom rows are where
Substrate goes past it: Soar's chunks are never tested, scoped or retired (the framework says as much of CogRec).

## What the atlas adds

1. **Claims that predict, scored online.** Beside the judge's batch verdicts, every model predicts the next
   signals in its scope as they arrive. Its running error is the **surprise** signal: it routes trust (which model
   to believe now), drives exploration (test the claim least certain), and triggers learning.
2. **Two speeds of learning.** A **provisional** tier forms and tests hypotheses within seconds, scoped to the
   episode, self-tested, unreviewed. The **durable** tier is today's: author, judge, owner. Promotion from
   provisional to durable is what the judge gates.
3. **Transition models as a kind of component.** Not only "this signal means X" but "in context C, action A turns
   pattern P into P′": graph rewrite rules, the mechanics claims at the heart of game learning (touch the
   rotator, the key turns; a ring refills the budget).
4. **Models of different kinds behind one interface.** A local model declares its scope, predicts within it, and
   reports cost and latency; whether it is a rule, a network, a physics engine or a model call does not matter to
   the router. Where a simpler or cheaper model predicts as well, it wins (description length against accuracy).
5. **The generalist as teacher.** Repeated narrow work by a generalist is the signal to build a specialist
   (distilled model, pipeline, synthesised rule), trialled on that scope and switched in when it matches. The
   generalist stays the fallback for anything new. The headline number is Substrate's existing KPI: model calls
   per event, falling.

A claim, for the atlas: subject, relation, object or value; **scope** (the context where it holds); **kind**
(existence and identity, property, spatial relation, transition, invariant, affordance); **prediction** (what it
can be checked against); **evidence and confidence**; **provenance** (perceived, inferred, carried over, proposed by
a model); **status** (hypothesis, confirmed, refuted). This extends S-135's statement with a reference, rather
than replacing it.

## Where the Postgres choices fit, and where they do not

Fit:
- statements with pinned evidence, and triggers that flag what cites a changed source: a truth-maintenance system,
  belief revision when support goes;
- pgvector, the graph projection and SPARQL: recall by similarity, by structure and by logic over the same store;
- pg_cron: offline consolidation (distil, prune, re-score), where the slow loop's library work runs;
- logins and row-level security: the judge's independence made real;
- pgmq actors under Nomad or compose: each local model a process with a mailbox and a card, supervised and
  swappable.

Do not fit:
- **The database is not in the fast loop.** Control at 100 Hz or more, tracking and physics live in actors' own
  memory and talk peer to peer; Postgres holds the slow tier (claims, maps, verdicts, the library) and summaries
  of what the fast tier saw. The framework's rate ceiling, made a hard rule.
- **Logical inference over uncertain claims is brittle.** Keep SPARQL and reasoning for structure (types, part-of,
  interfaces); decide belief about dynamics by prediction scores.

## Core and opinions, kept apart

- **Substrate's core:** the registry of components with scopes, claims and records; proposing, building,
  trialling, replacing; online prediction scores beside the judge's verdicts; the two tiers; routing by measured
  performance and cost. No view on how minds work.
- **Opinions about cognition, as hypotheses to trial:** the generalist mapper; surprise as the learning trigger;
  exploration by information gain; the time-scale hierarchy (reflexes, skills, deliberation); object-centric
  perception; a deliberate tier (Soar among the candidates, against a plain planner). Each is built as components
  and kept or dropped on evidence.

The same core serves software (Substrate's focus: components, interfaces, claims checked by tests) and worlds
(games, robots, 3D and VR). Mapping a codebase and mapping a game are the same activity on different signals.

## The first experiment

ARC-AGI-3 as a Substrate environment: frames as signals, the game's actions as actuators.
1. **Pass-through:** a vision LLM plays at a deliberate rate (a cheap model, not every frame), everything
   recorded.
2. **Distillation:** from the record, perception pipelines, transition claims and exploration habits as
   components, provisional within a game and promoted when judged.
3. **Judging:** held-out games through Morphogen, with a measure that moves off zero (progress within a level as
   well as levels completed), and games improved or regressed counted.
4. **Arms:** Soar with the hand-built rules (`agent/` as merged in #4, and `claude/agent-routes`), a plain LLM
   player, and the atlas. The plan's three-way comparison, with the atlas as the third arm.

The main risk is cost: a model in the loop for 48 cases of 500 steps. Model calls per step, falling as components
take over, is the number that says whether it works.

## Read for it (from memory, to be read before citing)

EMPA (Tsividis et al. 2021, theory-based RL on video games); WorldCoder (Tang, Key and Ellis 2024, world models
written as code); AutumnSynth (Das et al. 2023, causal programs for grid games); DreamCoder (Ellis et al. 2021,
growing a library across tasks); truth-maintenance systems (Doyle 1979); mixtures of experts and Dyna for local
models in RL.
