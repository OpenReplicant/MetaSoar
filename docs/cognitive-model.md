# A cognitive model: the hypothesis (proposal, 2026-11-20)

> **Note (2026-11-24):** brought to `main` from the unmerged branch `claude/exciting-wozniak` (tag `archive/exciting-wozniak`). envkit, which this text cites (`envkit/...`), was retired (Substrate S-196): environments are OpenEnv environments now, and the code it names is in that tag until it is moved onto OpenEnv. MetaSoar's place since then is M-20; System 1 skills are M-19.

`docs/architecture.md` records what exists. This document states what we think a mind is, in terms the framework
can build and test: the parts, how they work together, and the predictions that would show it wrong.

## The headline (M-17, 2026-11-22)

**Impasse-driven compilation:** an agent that calls the model only at impasses, and compiles what it solved into
judged skills, gets cheaper on recurring tasks with no loss of success, against the same model with memory and no
compilation (the Knowledge Kernel's memory profile). That is P1 and P5 below; the rest follow it. Lineage: Soar
(decision cycle, impasses, chunking, elaboration), global workspace theory (attention), predictive processing
(surprise).

## The thesis

A mind is an environment nested in a world. Inside it, detectors and automatic processes post into one shared
picture of now; a deliberate process attends to a small part of that picture and acts; everything it learns is a
predictive model with provenance, scored by how well it predicts; and what deliberation solves is compiled into
skills that run without it. Deliberation (a model call, a person asked, an experiment run) is reserved for
impasses: where the compiled paths, the simulators and the reasoner can't decide.

## The parts

### The world: environments of the same order
An environment contains:

| part | what it is | in a game | in an organization or software |
|---|---|---|---|
| static object | properties, no actions | wall, pipe, cloud | a document, a record, a log |
| interactive object | exposes actions (affordances), no initiative of its own | `?` block, door, key | a CLI tool, an API, a database, an MCP server |
| actor | acts on its own, with its own goals | an enemy, another player | a person, an agent, a bot |
| sub-environment | an environment of the same order | a level, a room | a repository, a team, a shell session |

Affordances are **declared** (tool schemas, `--help`, skills) or **learned** (by contact, as the atlas learns what
touching a kind does); both become the same claim: this object affords this action, with this outcome.

**Executable environments** are interactive objects whose actions are programs: a shell, a Python interpreter, a
database, an MCP client. Their command is a program, their readings are its output, their custody is what may run.
Writing a whole script is a held macro (one round trip); a REPL step decides again after each result. Which is
better is a decision by situation, and which surface to use for which task (CLI, code, MCP) is a claim measured by
the agent, not a rule adopted from outside (the published comparisons disagree: see the sources at the end).

**People, models and sub-agents are oracle actors**: something that can be queried or tasked, with a cost, a delay
and a track record. A vision model naming a sprite, a viewer in a chat, the principal answering an interview and a
delegated session are one kind of thing to the agent.

### The agent is an environment too
```
the agent
 ├── perception: detectors posting observations
 ├── the subconscious: taps on every channel (inputs, outputs, the deliberate process's own reasoning),
 │     enrichers posting back at low salience: memory retrieval, the reasoner, the skill matcher,
 │     simulators' predictions and surprises, reflex triggers
 ├── the workspace: one picture of now, with provenance; focus is attention
 ├── knowledge: claims, mappings to shared terms, simulators, long-term memory
 ├── skills and executors: snippets on the ladder from improvised to automatic; sandboxed interpreters
 └── the deliberate process: a decision cycle on the focus (Soar's); at an impasse, the slow path
```
The model is one oracle actor inside this environment, not the agent. Most of what happens in it is not a model
call.

### Perception
Detectors turn raw readings into observations (SOSA's sensor and observation): hand-written and exact where the
world allows (pixel art), pre-made models where it doesn't (flow, segmentation, image features, depth), connectors
and entity resolution for software and organizations. A slow-path model can write specs for the fast detectors
(names, regions, hazards) from occasional keyframes; a spec is installed only when evidence agrees.

### The subconscious
Automatic, parallel, mostly not a model: what Soar's elaboration phase does before each decision, and what a global
workspace's unconscious processes do. It reads everything, including the deliberate process's own outputs and
reasoning, and enriches the picture: "last time this happened", "this contradicts that", "a saved skill fits",
"the simulator expected otherwise". It is the reason the system is not model calls all the way down.

### The workspace
One picture of now (`envkit/workspace.py`): entries with a key, kind, attributes (each with its source and time),
confidence, time to live and salience. Same key, same thing (binding). Focus, the few most salient entries, is
attention: small on purpose. What competes for focus (a threat in the game, a line in the chat, a contradiction the
reasoner found) is how the agent divides itself between tasks.

### Knowledge: predictive models with provenance
Everything learned is a model that predicts, with its source and evidence, scored by how well it predicts:
- a **claim** is a one-line simulator ("touching this kind ends a life");
- a **mapping** (SSSOM: subject, predicate, object, justification, confidence, author) ties a learned local category
  (a pixel hash, an author's name) to a shared term in a small ontology (PROV-O, SOSA, W3C ORG, FOAF, DOAP,
  Activity Streams, ODRL, SKOS, and a game ontology of Self, Enemy, Hazard, Pit, Platform);
- a **reasoner** (OWL-RL, on the slow path) infers from claims and mappings and finds contradictions, which become
  questions and experiments;
- a **simulator** is claims composed and run: an environment of the same order as the real one, built from learned
  modules, with the same readings, commands and custody;
- **long-term memory** is the graph of all of it that outlives a run.

### Simulation
Running a simulator forward is imagination and planning; running it beside the world is prediction, and the
difference is surprise. Surprise decides what to revise and what deserves attention. Simulators are judged by
prediction error on held-out data. Tests on code, the judge's held-out cases, the equivalence check of the
workspace and the vision benchmark against the game's memory are all this process, applied to code and
architecture; it applies the same way to the world, to the agent's own body (what its jumps reach), to an
organization (what a change will do) and to people (what the principal will answer). Agents exploit a simulator's
errors, so the world and held-out judgment stay in charge: the simulator proposes, the world disposes.

### Deliberation and the slow path
A decision cycle reads the focus and chooses (Soar's). When it can't (no rule applies, rules conflict, the
simulator is unsure), that is an impasse, and it opens a sub-environment to resolve it, using the slow path:
- **a model** (propose a rule, write a script, name a thing);
- **a person** (an interview; ask only when the simulator of that person is unsure of the answer, or when being
  wrong is expensive);
- **an experiment** (try the untried; the exploration bonus that shrinks with use).

Every slow-path call has a cost, and exploration has a budget.

### Escalation gates are learned (2026-11-26)
Every boundary between a cheap path and a dear one asks the same question: is the cheap path enough here? A local
decision model before a larger one, System 1 before System 2, Haiku before Opus (E-16), the agent's rules before the
hook. A first stage's own confidence is one answer to it, and a weak one: in E-04a's cascade, d1-2B's confidence
gives 0.769 at 38% escalated, while escalating exactly where d1-2B is wrong would give 0.865 at 37%. So a gate is a
learned model trained on cases where both outcomes are known; every escalation is such a case, so the training
data comes free with use, and one mechanism serves every layer. E-04b sharpened what it models: not when the cheap
path fails (a calibrated first stage already knows that) but what escalating gains, which needs the dear path's
record and information the cheap path lacks, such as the kind of question. Ranked that way, the cascade beat
Inkling alone (0.828 at 63% escalated, against 0.810). E-04c added that, with a few hundred cases, the gate is best kept simple: neither a tabular
foundation model nor an embedding of the question beat the second stage's record by question type.

### The skill ladder (chunking)
What the slow path solves is compiled, as Soar compiles an impasse's result into a rule:
1. **improvised**: written at an impasse, run in the sandbox;
2. **saved**: a skill (description, the script, the situation it solved, its evidence);
3. **chosen**: picked from the catalog when the situation matches (the deliberate process chooses, nothing is
   written);
4. **automatic**: a trigger fires it with no deliberation (a reflex);
5. **demoted**: when it starts to fail, back down the ladder.

Promotion is a claim with evidence; a skill's tests are its simulation and the gate between saved and automatic;
anything that acts in the world on someone's behalf is promoted through the judge.

### Custody and judgment
Custody runs through every part: which readings are fair under which profile (privileged data is an answer key,
never a sense), who may act for whom, whose data stays where. Judgment is held-out: a change to the agent stays
only if it wins on cases it was not built on. The agent may change itself; it may not grade itself.

## Where H-JEPA fits (2026-11-22, M-18)

LeCun's hierarchical joint-embedding predictive architecture (the JEPA family: I-JEPA, V-JEPA and its successors) is a
world model that predicts in a learned latent space, at several time scales. In this model it is a part, not the
whole mind. LeCun's other modules already have homes here: short-term memory is the workspace, the configurator is
attention, the cost module is goals and the judge, and the actor's fast and slow modes are the skill ladder and
deliberation at impasses.

Where it plugs in:
- **Perception:** a pretrained V-JEPA encoder as a detector's features for frames (games, the camera).
- **Simulators:** an action-conditioned JEPA as a learned simulator, judged before it is used, for P2's kind of test.
- **Surprise:** latent prediction error as the surprise signal P7 compares against recency.
- **Hierarchy:** its time scales line up with nested environments and with the skill ladder's levels.

Where we differ: knowledge stays as claims with provenance, and the decision cycle stays explicit; a JEPA is one
more predictive model, scored like the others by how well it predicts. Before using one: the weights' licence and
what runs on the owner's GPU (we would use pretrained weights, not train one).

## The loop

perceive → post → enrich (subconsciously) → bind and map → predict and compare (surprise) → decide (compiled path,
or deliberation at an impasse) → act or ask → the outcome arrives, usually late → revise claims and simulators →
compile what deliberation solved.

## Predictions: what would show it wrong

Each is testable with what exists or is next to build. If a prediction fails, the part it rests on is wrong or
missing.

| # | prediction | test | it fails if |
|---|---|---|---|
| P1 | The share of deliberate calls falls over time on recurring tasks, with no loss of success | the skill ladder in an executable environment: a task family repeated; count model calls and success per round | calls don't fall, or success falls as they do |
| P2 | A simulator of one's own motion turns one experience of a hazard into general competence | the mover with a learned motion simulator: lives to pass a pit seen once; first-try success on pits never seen; an unseen level | it needs as many lives as the place-memory mover, or no gain on the unseen level |
| P3 | Claims mapped to shared terms transfer between worlds where claims by appearance did not (cold 51, warm 52 levels: no effect) | game ontology plus SSSOM mappings; claims learned in one game, measured in another; then org to org | no difference from cold starts |
| P4 | Asking where the simulator of a person is unsure improves the map more per question than a fixed priority | the cartographer with a principal model, against the fixed list, on held-out answers | no gain per question |
| P5 | Subconscious enrichment cuts deliberation at equal success | the same agent with and without enrichers; count deliberate calls and tokens | no reduction, or success drops |
| P6 | The same mechanisms serve a game and an organization with no special cases | the workspace, claims, mappings, simulators and the ladder used unchanged in Mario and OpenReplicant | either world needs a mechanism the other doesn't have |
| P7 | Surprise is a better guide to attention than recency | focus by prediction error against focus by recency, in the stream (game plus chat) | no difference in game progress or replies |

Already measured, and consistent with the hypothesis: hand rules tuned on training games overfit held out (M-14);
place-bound learning plateaus at one life a lesson (the mover near 1450 pixels); the workspace is transparent (the
mover chooses identically through it); privileged data used as an answer key scores perception without leaking into
it.

## P2, first attempt (2026-11-20)

`atlas/mover.py` with `simulate=True`: a model of self's motion learned from every step (how self's horizontal and
vertical speed change under each action, by how long the button has been held and whether self stands), rolled
forward over flat ground at self's height except at the known pits, and used to judge each candidate macro before
it runs ("falls" is penalised, "clears" favoured). Practice on 1-1, 3000 steps, lives kept, three seeds:

| | pit deaths (seeds 0, 1, 3) | furthest point | prediction error, pixels a step |
|---|---|---|---|
| place memory only | 9, 6, 0 | 2473, 1691, 643 | - |
| with the simulator | 9, 7, 0 | 1789, 1537, 643 | 8 to 13 (26 before standing was detected correctly) |

**No gain yet: P2 is not supported by this attempt, and not refuted.** What was found: (1) "standing" by a still
step also fired at the top of every jump, which erased pits from the map; two still steps fixed it, and that fix
alone moved the place-memory mover (it is in both rows). (2) At the decisive moment before the wider pit the
simulator gives no verdict: its predicted arcs do not come back down within its 20-step horizon, so neither "falls"
nor "clears" is said and the place values decide as before. Next: predict the landing (roll until self stands or
falls out of view, not for a fixed horizon), and give the pit its extent from where self was last seen falling.

## What it does not yet explain

- **Where goals come from.** The principal supplies them; intrinsic drive is open (reducing surprise is one
  candidate, and has known failure modes: an agent that seeks the predictable).
- **Affect.** Salience stands in for it; whether more is needed is open.
- **Language as more than an oracle's interface**: talking to the chat, explaining itself, being taught.
- **Metacognition beyond the judge**: knowing what it knows, and when its simulators are out of their depth.
- **Development**: which skills and simulators should come first, and whether a curriculum matters.

## Build order

1. **The self-motion simulator** in the mover (P2): record transitions, fit, plan jumps by simulating, measure
   prediction error, revise where surprised.
2. **The executable environment and the skill ladder** (P1): an `exec` world (shell and Python in the sandbox), a
   skills catalog posted into the workspace, promotion and demotion with evidence.
3. **The knowledge layer** (P3, P4): SSSOM mappings, the two small ontologies, the reasoner posting inferences and
   contradictions; the principal model for the cartographer.
4. **The subconscious** (P5): taps on all channels, enrichers posting at low salience.
5. **Soar's cycle on the workspace**, impasses opening sub-environments for the slow path.
6. **Attention by surprise in the stream** (P7).

## Sources for the executable-environment comparison

The published comparisons of CLI, code and MCP tool use disagree, which is why the surface is a measured claim
here: [MCP vs CLI for AI agents (arXiv)](https://arxiv.org/html/2610.30157); [Tyk's enterprise comparison](https://tyk.io/learning-center/mcp-vs-cli-for-ai-agents-enterprise-comparison-guide/);
[MindStudio: 35x tokens, 72% on hard tasks](https://www.mindstudio.ai/blog/mcp-servers-35x-more-tokens-cli-tools-reliability-benchmark);
[CodeAct: executable code actions (ICML 2024)](https://arxiv.org/abs/2402.01030);
[Anthropic: code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp);
[Cloudflare: Code Mode](https://blog.cloudflare.com/code-mode-mcp/);
[Anthropic: Agent Skills and progressive disclosure](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills).
