# System 1 skills: learned responses, triggers and observers in an Agent Skill folder (M-19)

A research spec, proposed 2026-11-24. Its decision is M-19. It continues impasse-driven compilation (M-17, on
branch `claude/exciting-wozniak-0sof8t`, not yet on `main`) and places it where Substrate's S-209 (f) put it.

## The idea in one paragraph

Agents already rewrite a skill's instructions after an episode of using it. The owner: "rather than just asking the
language model to write better instructions for language models to follow they can write the deterministic and
automated responses along with whatever trigger mapping supported". So a skill can hold more than instructions. It
can hold **policies** (a response the system runs without a model call, and the trigger that says when), **observers**
(how the current state is watched for those triggers), and **cases** (the record each policy was learned from and is
judged on). When an observer is confident that a trigger fits, the response runs: System 1, fast and cheap. When
nothing fits, the language model reads the skill's instructions as it does today: System 2. That case is recorded,
and a new policy can be compiled from it. And "how observers watch for triggers" is "another configurable parameter
point ... it needs testing and optimization like anything". So observers are judged and tuned like any other part.

## The folder: a convention on Agent Skills, not a new format

The Agent Skills spec (agentskills.io) requires only `SKILL.md` and allows any other files. It names `scripts/`,
`references/` and `assets/` as conventional. A System 1 skill adds three conventional directories and one manifest:

```
deploy-check/
  SKILL.md            the slow path: instructions the model reads (unchanged)
  scripts/            responses: executables a policy runs (the spec's own directory)
  observers/          how state is watched: feature detectors, matchers, their settings
  cases/              the record: each case's state, what was done, the outcome when it arrives
  system1.yaml        the manifest: policies, observers, thresholds
```

A harness that knows nothing of System 1 still loads the skill. It sees `SKILL.md` and some extra files, so nothing
breaks. A harness, hook or runner that does know reads `system1.yaml`.

The manifest, kept small:

```yaml
system1: v0
observers:
  error-text:                       # an observer: state in, features or a match out
    run: observers/error_text.py    # any executable; JSON in on stdin, JSON out
    input: [tool_output]            # which part of the state it watches
policies:
  retry-on-lock:
    when: {observer: error-text, match: lock_timeout, min_confidence: 0.9}
    do: scripts/retry_with_backoff.sh
    cases: cases/retry-on-lock/
    status: active                  # proposed | active | retired; only a judge's pass makes it active
fallback: model                     # below every threshold: the model reads SKILL.md
```

## The observer: one interface, many fillers

The hard part is matching state to policy. The observer is the one interface that matters:

- **In:** the state, as the harness or the environment has it (a prompt, a tool's output, an event, an observation
  from an environment).
- **Out:** zero or more `(policy, confidence)` pairs, and the features it used, so a miss can be explained.

The fillers, from cheapest to richest. All of them are swappable behind the same interface:

| Filler | What it is | Good for |
| --- | --- | --- |
| A feature-detector script | any executable: a regex, a parser, a check of a file or a service | exact, cheap, legible triggers |
| Rules over features | a few conditions over what detectors report | combinations, still legible |
| A small model asked for probabilities | the state as text, the candidate policies listed, a local model asked how likely each fits | fuzzy text, no training data yet |
| Nearest past case | embeddings of the state, compared with the cases each policy was learned from | many similar situations |
| A tabular model | the state's features as a row, scored by a tabular foundation model (TabPFN-style) or a small classifier | structured state, few examples |

Observers can be chained: a cheap detector narrows the candidates and a richer matcher decides among them. The
threshold is a setting, and so is the chain.

## Where it fires

Harness-agnostic. Wherever a runner can see the state before the model acts:

- **In a harness:** a hook that runs before the model sees the input (in Claude Code, `UserPromptSubmit` and
  `PreToolUse`; other harnesses have their own). On a confident match, the hook runs the response and hands the
  model its result, or answers directly where the harness allows.
- **In an environment:** a runner subscribed to events (an OpenEnv environment's observations, a queue's
  messages). It acts on a match through the environment's own gated actions, so a policy is under the same gates
  as anything else.
- **On its own:** a CLI that reads a state from stdin and prints the match. Tests and judges use this.

A policy's response is an action like any other: it waits behind its gate when it changes the world.

## The learning loop

1. **An impasse.** No observer is confident, so the model handles the state by reading `SKILL.md`. That is M-17's
   impasse.
2. **The case is recorded:** the state, what the model did, and later the outcome. Labels are outcomes, never the
   decider's own choice, and they may arrive long after.
3. **Compiling.** When cases like it repeat, an agent writes a candidate: a response script, a trigger, and if
   needed a new observer or new settings for one. It is not limited to a better instruction.
4. **Judging.** The candidate goes to a judge it cannot edit. With Morphogen, each policy and each observer is a
   cell: what may change (the script, the observer's file, the threshold), how it is run (replay the recorded cases;
   in an environment, episodes), and what is better. The measures: the trigger's precision and recall against the
   outcomes, the response's success rate, latency, cost per decision, and how often the slow path is still needed.
   Held-out cases stay out of the author's reach.
5. **Promotion and retirement.** A pass makes the policy `active`. A policy whose outcomes fall below its bar
   goes back to `proposed`, and the slow path takes those states again.

Nothing grades its own work. The agent that writes a policy is never the one that judges it.

## Becoming a standard

It could become one because it asks so little: a skill stays a valid Agent Skill, and the extension is three
directories and one manifest that any harness may ignore. What to propose upstream, and when:

- **Only after evidence**, meaning at least the first two experiments below with numbers.
- **Propose the smallest part:** the manifest's `observers` and `policies` with the observer interface (JSON in,
  matches out). Not our judge, not our gates, not a matcher.
- **Where:** the Agent Skills spec's repository (github.com/agentskills/agentskills), as a proposal for an optional
  extension, with a reference runner (a hook plus the CLI) that anyone can use without our other projects.

## Experiments, smallest first

1. **Replay on a recorded log.** Take a skill with a real usage record (Claude Code transcripts on one recurring
   task). Write two policies by hand and fit one observer of each kind. Replay the held-out half. Measure precision,
   recall, and the model calls saved. This tells us whether matching is good enough to act on at all.
2. **An agent compiles a policy.** Same log, but the agent writes the script, trigger and observer from the
   training cases, and Morphogen judges it on the held-out ones. Compare it against a hand-written policy and
   against only rewriting `SKILL.md`. This is the owner's claim, tested directly.
3. **An OpenEnv environment with repeating situations.** For example a terminal or a ticket queue, where some
   states recur. Run episodes with the slow path only, then with System 1 learning between episodes. Measure
   success, model calls and cost per episode as episodes go on. Does the system get cheaper as it learns, without
   getting worse?
4. **The observer as the tuned parameter.** Fix the policies, and let an optimiser choose among observer fillers
   and thresholds (Morphogen's `tune`). Is the best observer different per task? If so, the interface earns its
   keep.
5. **When to think: a setting chosen per input.** The owner (2026-11-24): the local `slow` model (Inkling 2 Mini)
   "performed much better in thinking mode on (vs off) in reasoning-heavy benchmarks, so finding a way to classify
   when an input should be processed with thinking mode could involve a nearest-neighbor search and benchmarks
   would give us some reason to trust the labeling". One model, one switch, so the comparison is clean (the same
   model on both sides). **Labels made locally:** run the model over public benchmark questions with known answers
   (reasoning, maths, law, plain lookups as the contrast), each with thinking on and off, through the gateway.
   Each question gets whether thinking changed the answer and what it cost (tokens, seconds). No published
   per-question results are needed. **Observers compared:** always off, always on, nearest neighbours on the
   questions' embeddings, a small classifier on those embeddings, and the `fast` model asked for the probability
   that the input needs reasoning. **Measure:** accuracy against tokens and seconds on held-out questions, then on
   real inputs from the record, where benchmark questions may sit far from the work. The threshold and `k` are a
   cell for Morphogen to tune. The same set-up extends to choosing a model, not just a setting, where a router at
   the gateway would use it (S-178 to S-183's ladder).

**What would falsify it:**

- Observers that cannot reach a precision worth acting on before the cost of building them outweighs the model
  calls saved.
- Policies the agent compiles that do no better on held-out cases than rewritten instructions.
- Learned policies that fail on new situations the way M-13's and M-14's hand-written rules did. That is the
  standing warning here: a rule the agent did not find for itself is one more thing for held-out cases to break.

## Related

- M-17 (impasse-driven compilation) and M-18 (H-JEPA as a part of the cognitive model) are on branch
  `claude/exciting-wozniak-0sof8t`, not yet on `main`.
- Substrate S-209 (f): System 1 research is MetaSoar's, shipped as a skill-folder convention.
- Substrate S-178 to S-183: the multi-response ladder. That is the same idea at the model endpoint, a design input.
- M-13, M-14: why learned rules must be judged on held-out cases.
