# A cognitive model: the hypothesis (proposal, 2026-11-20)

`docs/architecture.md` records what exists. This document states what we think a mind is, in terms the framework
can build and test: the parts, how they work together, and the predictions that would show it wrong.

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
