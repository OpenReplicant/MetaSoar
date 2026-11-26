# Experiments: one program, registered before they run (M-24)

A register, started 2026-11-25. The owner: "it might help to break it up into their own experiments, however the
whole-cognitive-architecture is a thing we want to test as a whole." Both are done, in three tiers:

1. **Parts, as gates.** Cheap experiments, each with its own falsifier, run first, so that a failure of the whole
   can be traced to a part.
2. **The whole, as the treatment.** The architecture with every part on, against its baselines.
3. **Ablations from the whole.** The whole with one part removed at a time. They test the whole and measure each
   part inside it, and they catch parts that pay only together, which experiments on parts alone miss. Leaving one
   out at a time, not every combination, is the budget.

**Rules.** An entry is written here before its experiment runs: what it claims, what would show it wrong, what it
needs first, and what it informs. A verdict is recorded in `DECISIONS.md` and its status here. Where a change to the
agent is judged, Morphogen judges it on held-out cases, and held-out verdicts are spent only on mechanisms
(`docs/next.md`).

**Measures shared by all, where they apply:** success; model calls and tokens per episode (from the gateway's log,
not the agent's count); cost and seconds per decision; for matchers, coverage at fixed risk (the share of states
taken while errors stay under a bound, `docs/typed-questions.md`); for probabilities, Brier score and calibration
error.

## Tier 1: parts

| ID | Claim | It fails if | Needs | Informs | Status |
| --- | --- | --- | --- | --- | --- |
| E-01 | Matching on a recorded log is good enough to act on (System 1, experiment 1) | no observer reaches a precision worth acting on | a skill with a usage record | W-01, A-01 | proposed |
| E-02 | An agent compiles policies that beat rewritten instructions (System 1, experiment 2) | compiled policies do no better on held-out cases than a rewritten `SKILL.md` | E-01 | W-01, A-02 | proposed |
| E-03 | The best observer differs by task (System 1, experiment 4) | one filler wins everywhere | E-01 | the standard: whether the interface earns its keep | proposed |
| E-04 | A typed question chooses when to think, and a local model read by its probabilities does it as well as a decision model (System 1, experiment 5) | no backend beats always-on or always-off on accuracy for tokens; or the 1.7B's lead does not survive more questions | benchmark questions labelled locally, thinking on and off | W-01 (`route`), A-03 | proposed |
| E-04a | Our local models, read by their probabilities, are usable decision backends on JevBench, against Jev's own predictions on the same cases (`docs/decision-backends.md`) | after debiasing (both option orders) and one temperature per slice, the readout's pooled accuracy is more than 10 points below Jev's, or its pooled coverage at 5% risk is under half of Jev's | the Leanmcp JevBench cases and predictions at `ed50fe0`; `trials/decision-readout/` | the backend for M-22; E-04's observers; whether to tune (prompt, then fine-tuning) as a Morphogen cell | registered 2026-11-25 while its first run was under way (only partial results on one slice seen). **LFM3 1.7B untuned: falsifier met** (0.528 against Jev's 0.842). **Inkling 2 Mini untuned: not met** (0.810 against 0.843, paired difference -3.3 points [-6.5, -0.3]; coverage 0.51 against 0.64). **d1-2B: met** (0.640 against 0.842; well calibrated as shipped, order-stable, 77 ms); **d1-omni-600M: met** (0.457) (`trials/decision-readout/README.md`) |
| E-05 | Near-miss mining writes features that beat nearest neighbours (System 1, experiment 6) | no gain over nearest neighbours on held-out questions | E-04's labels | A-02 | proposed |
| E-06 | Retrieval transfers: the outcomes of a state's nearest cases predict its own | no better than the base rate | any case base (E-01, E-04) | everything built on cases | proposed |
| E-07 | Precision measured in shadow holds once a policy is active | precision active falls far from precision in shadow | a runner with shadow and audit | A-03, the lifecycle | proposed |
| E-08 | Patterns can be mined from the agent's own replies (pattern catalog, experiment 1) | coverage or the compiled share too low to matter | a recorded reply log on one recurring task | E-09 | proposed |
| E-09 | A filled pattern does as well as free writing for less (pattern catalog, experiment 2) | outcomes fall, or text turns stilted | E-08 | W-01 where replies are part of the task | proposed |
| E-10 | Nesting raises coverage without lowering outcomes (pattern catalog, experiment 3) | it does not | E-09 | M-23 | proposed |
| E-11 | A simulator of one's own motion turns one hazard into general competence (P2) | as many lives as the place-memory mover; no gain on an unseen level | the mover | W-02 | first attempt 2026-11-20 (`docs/cognitive-model.md`) |
| E-12 | Claims mapped to shared terms transfer between worlds (P3) | no difference from cold starts | the knowledge layer | W-02 | proposed |
| E-13 | Asking where a simulator of a person is unsure improves the map more per question (P4) | no gain per question | the cartographer | W-02 | proposed |
| E-14 | Surprise is a better guide to attention than recency (P7) | no difference in progress or replies | the stream | A-08 | proposed |
| E-15 | A model proposing claims at surprises recovers a rule deleted from the atlas (the atlas's model tier) | it does not recover the dial and lock on LS20 | `atlas/` | W-02 | next (`docs/next.md`) |
| E-16 | Haiku first, escalating to Opus on outcome triggers, matches Opus throughout on success at a fraction of its cost (the orchestrator, `docs/on-substrate.md`) | success is significantly lower than Opus throughout on the same recorded tasks; or cost per task, from the gateway's meter, is not lower | a set of recorded tasks with their own checks; the gateway's meter; a Haiku-main session spawning Opus subagents, checked to work | the orchestrator's routing cell; W-01's model calls per episode | proposed |
| E-17 | **The handler ladder (M-26) cuts model calls on a stream of recurring intents with no loss of accuracy.** On TabMWP (Lu et al., ICLR 2023; tables and math word problems, generated from templates, so intents recur by construction), a stream of the `test1k` cases in a fixed random order: an intent elaborator (a small local model names the question's intent, an exact key, as in Agentic Plan Caching) routes each case to the cheapest rung that holds for its intent; the large model (Inkling) solves what nothing else holds; after enough of one intent's cases it writes a plan template (then adapted by the small model) and a Python handler over the table; each is promoted only when it agrees with the large model's own answers on that intent's earlier cases at 95% or more (no gold labels used), and falls back to the large model when it raises or its answer fails a check (type, choices) | over the last 500 cases of the stream, templates and handlers together answer under 30% of cases; or accuracy there is more than 2 points below the large model alone on the same cases (paired, 95% interval) | TabMWP at `5a1a522` (data CC BY-NC-SA 4.0, fetched, not committed; `dev1k` for prompts, `test1k` for the stream); Inkling and a small local model served as in E-04a; the large model's accuracy and speed on TabMWP measured first | W-01's first instance (model calls falling over a stream); M-26; which rungs pay | registered 2026-11-26. TabMWP is templated, so this tests the mechanism, not its reach on real work |

## Tier 2: the whole

| ID | Claim | Against | It fails if | Status |
| --- | --- | --- | --- | --- |
| W-01 | **The headline (M-17, P1).** With every part on, the agent calls the model only at impasses and compiles what it solved, so on recurring task families it gets cheaper with no loss of success | vanilla Soar 9.6.5; a vanilla LLM agent; the same model with the kernel's memory and no compilation (M-17 (b)) | calls do not fall over rounds, or success falls as they do | proposed; System 1, experiment 3 (an OpenEnv environment with repeating situations) is its first instance |
| W-02 | **One set of mechanisms (P6).** The same parts, unchanged, serve a game and an organisation | the same baselines, in each world | either world needs a mechanism the other has not | proposed |

## Tier 3: ablations from W-01

Each runs W-01 with one part removed and everything else unchanged. Each answers: what does this part add, inside
the whole?

| ID | Removed | Replaced by | What it tells |
| --- | --- | --- | --- |
| A-01 | System 1 | every state to the model | the size of the whole effect |
| A-02 | the compilers | the case base kept, used by retrieval alone (pure case-based reasoning) | whether compiling adds anything over remembering |
| A-03 | calibration | raw scores against thresholds | whether one currency is needed |
| A-04 | typed impasses | one generic impasse, learned from the same way | whether routing learning by impasse type pays |
| A-05 | the Soar engine | the standalone runner | whether Soar's recursion and chunking add anything (`docs/system1-skills.md`, "Relation to Soar") |
| A-06 | hierarchical metacognition | the unified design of Laird, Lebiere, Rosenbloom and Stocco (2025): the improver's work done by the agent's own cycle on its own trace | which kind of metacognition the architecture should have |
| A-07 | the enrichers, the subconscious (P5) | none | whether enrichment cuts deliberation at equal success |
| A-08 | attention by surprise (P7) | attention by recency | E-14, inside the whole |

## Order

Tier 1 entries that gate W-01 come first: E-01, E-04, E-06 (cheap, and everything rests on them), then E-02, E-05,
E-07. W-01 runs once its instance (an OpenEnv environment with repeating situations) exists, with A-01 beside it,
since A-01 is W-01's own comparison. The other ablations follow W-01's first result.
