# The architecture: one loop, in layers, for any world (2026-11-20)

The same loop runs whether the world is a game, a live stream or an organization: perceive, post what was seen into
one picture of now, bind and map it to shared terms, reason, decide, act or ask, and revise claims when the outcome
arrives (usually late). This document is the map of the layers, what holds them together, where OpenReplicant's
repositories sit in it (placed by their own descriptions), and what exists so far.

```
  judgment       Morphogen: every change to an agent is judged on held-out cases
                 (seeds, levels; for an organization, later periods of time)

  agency         a decision cycle on the workspace (Soar); an impasse, a contradiction or an unknown
                 goes to the slow path: a model, an interview, an experiment (MetaSoar)

  knowledge      claims and mappings (SSSOM) over small ontologies; a reasoner infers and flags
                 conflicts; long-term memory as a graph (kernel, cognee)

  workspace      one picture of now: entries with provenance (PROV), binding, expiry, focus (attention)

  perception     detectors post observations (SOSA): the sight, HUD readers, git and ticket
                 connectors, entity resolution

  environments   declared as data, nestable, with custody profiles: games, a stream with its chat,
                 an organization with its principal (Substrate's contract; envkit)

  runtime        actors exchanging messages; lockstep or realtime; in process now, NATS or pgmq
                 later (actor-model)
```

## The loop

| step | in a game (Mario) | in an organization (OpenReplicant) |
|---|---|---|
| perceive | the sight: camera, background, tracked things from pixels | connectors and entity resolution: commits, authors, sessions, repositories |
| post | things, camera, lives and level counts into the workspace | actors, repositories, commits into the same workspace |
| bind | the box, the model's name and the harm claim are one thing | "OpenReplicant" and a person's name may be one actor |
| map | `kind:5195fd47` close match `game:Enemy` | "co-author only" broad match `prov:SoftwareAgent` |
| reason | an Enemy is a Hazard, so avoid it before dying to it | a person and a software agent are disjoint: two sources conflict, ask |
| decide | which macro, here, in this situation | whom to ask, what to delegate, what to leave |
| act | buttons | delegation (recorded; acting in the org is the principal's to allow) |
| ask | an experiment: try the untried | an interview: a question in the principal's mailbox |
| outcome | a life lost, reported three seconds after the fall | revenue, churn or a merged change, weeks after the decision |
| revise | claims about kinds, places and pits | claims about actors, links, purposes |

People, models and sub-agents are all **oracle actors**: something that can be queried or tasked, with a cost, a
delay and a track record. A vision model naming a sprite, a viewer in the chat, the principal answering an interview
and a delegated session are the same kind of thing to the agent, and choosing whom to ask or task next is one
explore-and-exploit policy (the mover's bonus for the less tried is the same rule).

## What holds it together

1. **Everything learned is a claim with provenance**: what a kind does, which actor is self or principal, what a
   term means. Nothing is believed without a source and a time, and anything can be refuted by later evidence.
2. **Uncertainty drives exploration, within a budget.** Impasses, contradictions the reasoner finds and gaps in the
   map decide what to try or whom to ask. The budget (four interviews a run; a shrinking bonus for the tried) is
   what keeps exploration from becoming a rabbit hole.
3. **Shared terms make learning portable.** Learned local categories (a pixel hash, an author's name) get SSSOM
   mappings to ontology terms. What was learned in one world is then a statement about a class, which can carry to
   another world, and two agents in different worlds can be compared claim by claim.
4. **Custody runs through every layer**: which readings are fair under which profile (the game's memory is an answer
   key, never a sense), who may act for whom, whose data stays where (a ROM, an org's history).
5. **Self-improvement is judged.** An agent may change its own code; only held-out results decide whether the
   change stays. Training results are not evidence (DECISIONS.md, M-14: hand rules that gained 6 training levels
   scored 0 better and 12 worse held out).
6. **The core holds no opinions about cognition.** The runtime, environments, workspace mechanics, the claim and
   mapping formats and the judge are framework. What to attend to, which claims to form and how to explore are the
   agent's, and are judged like any agent code.

## The layers

### Runtime
Modules are actors: named input and output ports, no shared state, messages only (`envkit/core.py`). Two schedulers
run the same modules: **lockstep** (deterministic, as fast as the machine; delivery is depth first, so an encoder's
output reaches the agent before the world's tick) and **realtime** (worlds on the wall clock, everything else on its
own thread; a slow model call falls behind instead of freezing the world, which makes a fast path necessary). The
bus is publish and subscribe, so it can move out of process (NATS, as in actor-model, or pgmq) without changing a
module; messages will then need a codec per port type and frames passed by reference.

### Environments
Declared in TOML, data only (`environments/*.toml`): modules, their parameters and wiring, what is exposed, and
profiles saying which readings are fair for which use. An environment can be a module of another (a stream holds a
game and a chat). Private values come from the machine (`$NES_ROM`, `$ORG_SNAPSHOT`). The agent is chosen at run
time, never in the declaration: the world side is people's, the agent side is the candidate's, the scorer is the
judge's.

### Perception
Detectors are encoders: they turn a world's raw readings into observations. Hand-written and exact where the world
allows (pixel art repeats pixel for pixel: `envkit/vision.py`, scored against the game's memory); pre-made models in
the same slots where it doesn't (optical flow, segmentation, image features, depth for 3D games); connectors and
entity resolution for an organization (`envkit/org.py`). A vision-language model belongs here too, on the slow path:
from occasional keyframes it writes specs for the fast detectors (names, HUD regions, hazards), installed only once
evidence agrees.

### Workspace
One current picture (`envkit/workspace.py`). Entries are symbols with provenance: key, kind, attributes (each with
the source that set it and when), confidence, time to live, salience. Same key, same thing: a second source's
attributes merge into the entry. Entries expire when not posted. `focus` is the few most salient: attention, small
on purpose. Fast reactions may read detectors directly; the workspace is the deliberate path.

### Knowledge
Not built yet. Claims and mappings as workspace entries, exported as linked data:
- **mappings in SSSOM**: subject, predicate (`skos:exactMatch`, `closeMatch`, `broadMatch`), object, justification
  (semapv: learned from play, lexical, manual curation by the principal, logical reasoning), confidence, author;
- **small ontologies**, written only as far as the reasoning needs: a game one (Self, Enemy, Hazard, Pit, Platform)
  and an organization one on W3C ORG, PROV-O, FOAF and DOAP; SOSA for observations, Activity Streams for events,
  ODRL for permissions;
- **a reasoner on the slow path** (OWL-RL rules over a JSON-LD snapshot) posting what it infers back into the
  workspace with itself as the source, and posting contradictions and under-determined questions as the next
  interviews or experiments;
- **long-term memory** as a graph that outlives a run (the role kernel and cognee-enhanced describe).

### Agency
A decision cycle reads the workspace and chooses. MetaSoar's premise is Soar's: when the cycle can't decide (an
impasse), the slow path takes over. Here the slow path has three forms: ask a model, ask a person (an interview),
or run an experiment (try the untried). The agents so far are hand-built Python on the workspace pattern: the atlas
(ARC), the mover (Mario), the cartographer (OpenReplicant). Putting Soar's own cycle on the workspace, with its
impasses as the trigger for the slow path, is the step that makes this MetaSoar.

### Judgment
Morphogen judges a change to an agent on held-out cases and refuses changes that don't win there
(`.github/workflows/morphogen.yml`). It judges ARC-AGI-3 today. Mario needs held-out levels or games; an
organization needs held-out time (learn the record up to a date, predict the weeks after).

## Where things stand

| layer | state |
|---|---|
| runtime | in process; lockstep and realtime both working; no out-of-process bus |
| environments | ARC-AGI-3, Mario (NES driver), a stream with a scripted chat, OpenReplicant; nesting and custody profiles tested |
| perception | the sight (1-1: player found 98%, enemies 92%, camera within 2 px 96%); org entity resolution |
| workspace | built; the mover reading Mario through it chooses exactly as it does reading the detectors |
| knowledge | claims live inside each agent; no ontology, SSSOM, reasoner or long-term memory |
| agency | atlas, mover, cartographer; Soar's cycle not on the workspace |
| judgment | ARC-AGI-3 only |

Results so far: on ARC-AGI-3 the atlas's hand rules overfit (M-14); on Mario the mover's furthest point in a life
rises from about 300 to 1816 pixels over 9000 steps of practice (a fixed rule: 717) and plateaus near 1450, because
what it learns is tied to places and costs a life a lesson; on OpenReplicant the cartographer maps actors,
repositories, links and eras from 829 events and asks its principal four questions it can't settle from the record.

## Next

1. **The knowledge layer**: SSSOM mapping entries and export, the two small ontologies, the OWL-RL reasoner posting
   inferences and conflicts. Tests: the cartographer choosing interviews by contradiction and under-determination;
   the mover avoiding a hazard it has only been told about.
2. **Soar's cycle on the workspace**, its impasses sending work to the slow path.
3. **A model of self-motion** for the mover (what its jumps reach), posted as claims, so a pit seen once can be
   crossed and a pit never seen can be judged.
4. **Held-out tests beyond ARC**: an unseen Mario level; held-out time for the organization.
5. **Live**: answers from the principal flowing in while a run goes on; the stream with a real chat; delegation to
   real sessions once the principal allows it.
