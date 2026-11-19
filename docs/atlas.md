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

## What the closest work shows (read 2026-11-19)

Three systems learn a game's rules from playing or watching it, and report results. All three were read in full
(the PDFs' text).

**EMPA** (Tsividis et al. 2021, arXiv 2107.12544, "Human-Level Reinforcement Learning through Theory-Based
Modeling, Exploration, and Planning").
- A theory is a game description in a subset of VGDL: object classes with dynamic types, pairwise interaction
  rules by class, win and loss conditions. Inferred by Bayesian inference over that space, per game.
- Exploration seeks the most informative events, which "are always agent-object and object-object interactions for
  classes of objects that have not previously been observed in contact"; plans can be long and exist only to cause
  such contacts.
- Planning: best-first search with the most probable theory as simulator, intrinsic rewards for goals, subgoals and
  goal gradients, novelty pruning (Iterative Width), and a meta-controller that switches search modes on
  prediction errors.
- Results on 90 games: within 0.1x to 10x of human efficiency "on 79 out of 90 games"; DDQN "more than 100x less
  efficient on 67 out of 90 games" (DDQN capped at 1 million steps). Ablations: replacing its exploration with
  epsilon-greedy "fail[s] dramatically" on exploration-hard games; removing planner heuristics leaves some games
  with no level solved.
- Given to it, not learned: the state "is fully observed" (objects, no pixels); "which object corresponds to the
  avatar, its type ... as well as the projectile"; which objects are walls; deterministic interactions; 14
  predefined interaction types. Up to 24 hours per game, with an unoptimised engine. No cross-game transfer.

**WorldCoder** (Tang, Key and Ellis 2024, arXiv 2402.12275).
- The world model is Python: a transition function and a reward function, written and debugged by an LLM (GPT-4)
  until they reproduce every recorded transition; programs to refine are chosen by a bandit (REx).
- **Optimism under uncertainty**, as a logical constraint: the model must let the planner reach a rewarded end
  from the start state, so where the goal is not yet understood the LLM writes an optimistic reward (touching the
  key counts), and the agent goes and tests it. Without it, nothing is solved in AlfWorld ("necessary for any
  non-zero performance") or MiniGrid's harder environments; on Sokoban, with dense reward, it makes little
  difference.
- Sample efficiency: Sokoban's model built "over the first 50 actions" (deep RL takes over a million); MiniGrid
  UnlockPickup from "no more than 100 actions" (PPO had no reward after 3×10^8). Cost: "after front-loading 400k
  LLM tokens (about $15), it can issue as many actions as needed without subsequent LLM queries", against an LLM
  call per action for ReAct (which solved 15% ± 8% of basic Sokoban levels).
- Given to it, not learned: symbolic, discrete states (its authors: "the real world is messy and continuous");
  deterministic dynamics; the goal in words. Transfer is refining the previous program, "a very basic mechanism";
  no library. Fails on Sokoban with 5+ boxes (planning).

**AutumnSynth** (Das, Tenenbaum, Solar-Lezama and Tavares, POPL 2023, "Combining Functional and Automata Synthesis
to Discover Causal Reactive Programs"; inspired by ARC, the paper says).
- Learns a program in Autumn, a reactive language for grid worlds: objects, update functions, and on-clauses ("on
  event, update"). Four steps: perception (one-colour regions, as ours), tracking (nearest match), update functions
  for each object's change, then **cause synthesis**: an observable event that fires exactly when each update
  happens, and where none exists, **invented latent state** (a small automaton: a counter, a mode, a switch).
- Results: 27 of 30 of its own programs, 24 of them with latent state (up to 11 states); 21 of 27 EMPA games' first
  levels, mostly matching unseen traces. Traces were curated by hand to show every dynamic.
- Cost: 2 minutes to 13 hours per program on its own corpus, up to 38.8 hours on EMPA's; offline, not online
  ("synthesized incrementally ... with each new observation" is future work). Hand-tuned biases, which it hopes to
  learn ("a library of higher-level Autumn functions ... in the style of DreamCoder"). Deterministic causes only.

What they mean here:
1. **Rules over objects, plus latent state, are the right form of transition claim.** EMPA's interaction rules,
   WorldCoder's programs and Autumn's on-clauses are the same idea. Autumn adds what LS20 needed: hidden state
   invented when no visible cause explains a change (the key's rotation count, the budget, lives).
2. **Two exploration mechanisms with evidence behind them:** cause the interactions not yet observed (EMPA), and
   act on an optimistic model of the goal and let reality correct it (WorldCoder). My hand-written curiosity was
   a crude version of the first; the ablations say both matter.
3. **The generalist-as-teacher has a measured instance.** WorldCoder pays an LLM once (about $15 of tokens) and
   then acts with no model calls; ReAct pays per action. That is the atlas's falling model calls per step.
4. **Nobody has solved perception for them.** EMPA is told the avatar and the walls; WorldCoder needs symbolic
   states; AutumnSynth's parsing works only on clean grids. ARC-AGI-3's frames are clean grids, so this is the
   right place to start, and MetaSoar's perception (objects, the mover, ticking cells) is already most of
   AutumnSynth's step 1 to 2.
5. **Speed is the open problem for learning within an episode.** EMPA takes up to a day per game, AutumnSynth hours
   per program offline, WorldCoder minutes of LLM time. A held-out case here is 500 steps under a time bound. So
   the provisional tier has to learn incrementally (cheap local fixes as each observation arrives), with full
   synthesis offline in the slow loop.
6. **None was judged on games held out from its builders,** and none transfers much. The held-out judge and a
   growing library are what this project adds.

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
3. **Transition models as a kind of component.** Not only "this signal means X" but "on event E, objects of kind K
   update by U": Autumn's on-clauses, EMPA's interaction rules, the mechanics claims at the heart of game learning
   (touch the rotator, the key turns; a ring refills the budget). Where no visible event explains an update, a
   latent variable is proposed (a counter, a mode), as AutumnSynth does.
4. **Models of different kinds behind one interface.** A local model declares its scope, predicts within it, and
   reports cost and latency; whether it is a rule, a network, a physics engine or a model call does not matter to
   the router. Where a simpler or cheaper model predicts as well, it wins (description length against accuracy).
5. **The generalist as teacher.** Repeated narrow work by a generalist is the signal to build a specialist
   (distilled model, pipeline, synthesised rule), trialled on that scope and switched in when it matches. The
   generalist stays the fallback for anything new. The headline number is Substrate's existing KPI: model calls
   per event, falling.

A claim, for the atlas: subject, relation, object or value; **scope** (the context where it holds); **kind**
(existence and identity, property, spatial relation, transition, latent variable, invariant, affordance, goal);
**prediction** (what it
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

ARC-AGI-3 as a Substrate environment: frames as signals, the game's actions as actuators. Built from the three
papers' parts, with MetaSoar's perception in front:
1. **Perception (the fast tier, no model calls):** objects, the mover, ticking cells, as MetaSoar has now
   (AutumnSynth's steps 1 and 2).
2. **Transition claims (the provisional tier):** rules in an Autumn-like form ("on event, update"), with latent
   variables where no visible cause explains a change. Proposed by an LLM from the record of the game so far, as
   WorldCoder does, and repaired incrementally against each new observation rather than rewritten.
3. **Exploration:** cause the interactions not yet seen (EMPA), and act on an optimistic guess of the goal
   (WorldCoder); surprise (a rule's prediction failing) triggers repair.
4. **Planning:** search with the current rules as the simulator, toward the goal or the next informative contact.
5. **The slow loop:** rules and perception that held across games go to the library, judged on held-out games
   through Morphogen, with a measure that moves off zero (progress within a level as well as levels completed),
   and games improved or regressed counted.
6. **Arms:** Soar with the hand-built rules (`agent/` as merged in #4, and `claude/agent-routes`), a plain LLM
   player, and the atlas. The plan's three-way comparison, with the atlas as the third arm.

Risks, now with numbers to set against: an LLM per step costs per action (ReAct's way); WorldCoder's way front-loads
about $15 of tokens per environment, too much for 48 held-out cases per verdict unless the library makes repairs
small. The time bound needs learning in seconds, where the papers take minutes to a day. Model calls and tokens
per game, falling as the library grows, are the numbers that say whether it works.

## Notes (2026-11-19, the owner and Claude)

**Pretrained models as instinct, and first principles, in one catalog.** A perception option is a component like
any other, with a scope, a cost and a record:
- on ARC-AGI-3's clean 64×64 grids, exact one-colour regions (MetaSoar's perception) are correct and take
  microseconds; a pretrained backbone (DINOv2, SAM) adds little there;
- what a pretrained model adds even on ARC is **prior knowledge**: a vision-language model looking at a frame can
  guess "a player, a key display, a door, pickups", a hypothesis for play to test, once a level rather than once a
  step (WorldCoder's use of GPT-4, as perception rather than code);
- in robotics, 3D and VR, pretrained models are the instinct (segmentation, depth, pose, grasping); learning is
  what is built around them. A large model can hand narrow work to a smaller one; the router decides by record.

**Similarity as online learning.** Two places it fits:
- the provisional tier: act on what happened in the most similar past situations, learning from a handful of
  episodes (episodic control: Blundell et al. 2016, Pritzel et al. 2017; from memory, to be read before citing);
- transfer: objects and situations embedded by appearance, so a claim about a look in one game is proposed for a
  similar look in another; clusters of situations instead of exact scene hashes, whose exactness made click games'
  scenes look new when they were not.
- The caveat: looking alike is not acting alike, so a retrieved claim enters as a hypothesis (provenance: carried
  over) and is confirmed or refuted by play.

**The store as a module, and maybe a product: governed belief, not memory.** Agent memory on Postgres with
provenance and time travel is no longer open ground (Zep and Graphiti, Mem0, Letta, Cognee, LangMem; Postgres-native
and recent: pgmnemo, attestari, gnokee; one search, 2026-11-19, not a survey). What that search did not show is
Substrate's combination:
1. claims with an interpreter, a confidence and a review status, not facts with times;
2. belief revision in the database: a changed source flags what cites it and what was derived from that, with no
   model call (truth maintenance);
3. a registry of components with scopes and records from held-out judging, routing by that evidence, a verdict
   itself a statement whose reference is the judge;
4. independence enforced by Postgres logins (an author cannot read held-out cases; a judge cannot activate);
5. actors' mailboxes (pgmq) beside the store, under one set of transactions and permissions.

A narrow interface (statements with evidence; claims with status; retraction and its spread; recall by similarity,
structure and logic; components with scopes and verdicts) is worth having for Substrate's own sake. Its first
outside user would be the atlas's library across games. Before calling it a product: a real market survey (the
research skill), and the cost of shipping a Postgres extension (packaging, upgrades, support).

**Blueprints as interfaces with roles; catalogs searched by role.** The owner: the premise that a narrow interface
keeps a module clean suits how Substrate maps blueprints. A blueprint is a set of interfaces, each slot named by
the role it plays and the intent behind it, and the component catalog is searched by what fills a slot (its role,
its contract, its judged record for that scope) rather than by description. The atlas's measurements point the same
way: claims carried between games by appearance did nothing (8 episodes better, 8 worse), because a look predicts
poorly what a thing does; what an agent can carry is a role (a refill, a dial, a lock) recognised by its behaviour
in the first contacts. Matching a part to a slot by role and evidence is one operation at both levels: an object to
a role in a game, a component to a role in a blueprint.

## Read for it

Read in full (2026-11-19): EMPA (arXiv 2107.12544); WorldCoder (arXiv 2402.12275); AutumnSynth (POPL 2023,
doi 10.1145/3571249). Still from memory, to be read before citing: DreamCoder (Ellis et al. 2021, growing a library
across tasks); truth-maintenance systems (Doyle 1979); mixtures of experts and Dyna for local models in RL.
