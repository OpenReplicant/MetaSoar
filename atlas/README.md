# The atlas prototype (ARC-AGI-3)

The first tier of `docs/atlas.md`'s first experiment: claims learned from play, no model calls, no Soar. It is a
separate arm, not the judged agent (`agent/`), and reuses MetaSoar's perception and environment.

- `agent.py`: what it learns (passable colours; what touching and clicking each kind of object does; the player,
  its moves and its body) and how it chooses (test what is untested by a route over what it believes passable,
  untried colours counted passable; clicks not tried in this scene and never a point that did nothing on this
  level; then the map of scenes). The module docstring has the details.
- `play.py`: one episode, a case in and a result out, in the shape of `metasoar.play`'s.

```sh
echo '{"env": "arc3:LS20", "seed": 0, "max_steps": 500}' | podman run --rm -i -v "$PWD:/work:ro,Z" \
  ghcr.io/openreplicant/metasoar-sandbox@sha256:846875ecea32834ee9d44635128d382502086362341cf91c559a1b195ab1033d \
  sh -c 'cd /work && python3 -m atlas.play'
```

## Measured (training games only, seeds 0 to 19, 500 steps)

| game | Soar, PR #6 | atlas, first tier | atlas, with the lock |
|---|---|---|---|
| LS20 | 20 | 20 | 40 |
| VC33 | 31 | 23 | 23 |
| S5I5 | 9 | 5 | 5 |
| BP35 | 0 | 3 | 2 |
| RE86 | 2 | 0 | 0 |
| SK48 | 2 | 0 | 0 |
| DC22, SB26, TR87 | 0 | 0 | 0 |
| total | 64 | 51 | 70 |
| games with a level | 5 | 4 | 4 |
| slowest episode | about 8 s | 3.9 s | 5.0 s |

On LS20 the first level falls out of the claims: it touches the untested rotator, the scene changes, it touches the
door. BP35 completes a level for the first time with any agent here.

## Hidden state (in `agent.py`)

Two latent variables, after AutumnSynth's invented automata, each learned from play:
- **a budget**: steps since the budget last filled. Its size comes from harm that arrived with nothing touched
  (the player sent back to its start); a kind whose taking makes the ticking region jump is a refill. Routes to a
  target too far for what is left go through a refill first, choosing the spot that leaves the shortest way on.
- **a press count**: how many times this attempt the agent changed the scene by touching something, and at which
  counts something blocked it. If what blocks did so at the current count, it presses again before going back.

Also fixed on the way: an object counts as taken only if its cells lose its colour (floor fragments that the body
covers are not taken); a contact that changes the scene beyond what was touched is an event (the rotator), not a
take; passability goes by the majority of evidence; colours walked on often are floor, not things to test; a new
scene only when the agent caused a change, a level ended or the attempt started over (not when a life was lost).

On LS20 level 2 the agent now learns the budget (22 steps), the refill (the rings), that the door stays shut after
0 and 1 presses, and presses the rotator twice. It still runs out of budget on the way to the door: from the
rotator's corner the door is about 22 steps by the only way out, against a budget of 22. Whether the key's state
survives a lost life (so that pressing twice in one life and walking to the door in the next works) is untested.
The rest of the training games are unchanged (51 levels, seeds 0 to 19).

Then it was tested by reading the frame directly: the key's state does **not** survive a lost life (it is put back
with the player), and the key has four turns, of which the door wants the third, not the second. So a third latent
claim, and one fix:
- **a dial and a lock**: the region a press changes beyond what was touched is the dial; what blocked a touch is a
  lock (each contacted object, its own box). Each is read as a pattern per colour, cropped and reduced to its
  smallest scale, so the HUD's key drawn at twice the size of the door's matches it. While the dial does not fit any
  lock, press again; when it fits, go to the lock (through a refill if the budget would not last). The press count
  is now put back when a life is lost, as the game does.
- **floor is not a culprit**: a region of a floor colour under the size limit for walls had been blamed for a lost
  life and so walled off from every route; things of a floor colour are no longer contacts or harmful.

LS20 level 2 now falls on all 20 seeds, at about step 106 (three turns, a refill on the way, the door). Nothing in
the rule names the game: it is the claim "a thing that changes when pressed and matches what blocks is a key".

## Claims carried between games (the library)

At the end of a game the agent writes what each look (shape mask and colour) did when touched or clicked; at the
start of the next it reads those counts as priors for kinds it has not tried itself (a look that ended a level is
tried first, one that harmed is tried last). Measured leave one out: each training game, seeds 0 to 19, cold and
then warm from the other eight games' libraries for the same seed (about 260 to 310 looks each).

| game | cold | warm | episodes better | worse | mean step of first level (both scored) |
|---|---|---|---|---|---|
| VC33 | 23 | 28 | 7 | 3 | 32 cold, 39 warm |
| BP35 | 3 | 1 | 1 | 3 | |
| S5I5 | 5 | 3 | 0 | 2 | 95, 95 |
| LS20 | 20 | 20 | 0 | 0 | 29, 29 |
| the other five | 0 | 0 | 0 | 0 | |
| total | 51 | 52 | 8 | 8 | |

No effect to speak of: as many episodes got worse as better, and where both scored the first level came no sooner.
Looks shared between games are mostly small plain pieces whose outcomes differ by game, so a prior keyed on look
alone points the wrong way about as often as the right way. What would have to carry is the rule rather than the
look (a thing that changes the scene beyond itself is worth touching again; a ticking bar is a budget), which the
agent already brings to every game as code.

## The model tier (`propose.py`), first run

When a level goes 40 steps without completing, the agent asks a model for a hypothesis and a `plan(w)` that names
what to touch; a plan with no level in 60 steps is refuted and the next call is told so; at most 4 calls a level.
The prompt holds only what the agent has seen and learned (claims, objects, notable events with the cells they
changed, the frame as hex), about 3,000 tokens. Answers go through the cache as a mailbox: the episode stops at an
unanswered prompt and replays once it is answered, so the sandbox needs no network.

First run, Claude Haiku 5.5 (a small model, standing in for one run locally), on LS20 with the hand-written dial and
lock turned off, seeds 0 to 4: **1 level on each seed, the same as with no model** (4 seeds finished; seed 3 stopped
with 1 level and a fifth prompt unanswered). Over 22 answers the hypotheses went from "touch what completed a level
before" to "the switch changes the pattern in the bottom-left block", and by the third and fourth calls two seeds
named that change. None compared that pattern with the door's, and the plans then sent the player to touch the
bottom-left block itself (part of the HUD, out of reach) instead of pressing the switch until it matched the door.

Reading: the evidence was there (events with before and after patches; the frame), but a small model did not join
"the switch changes a pattern" to "the door shows a pattern" in four tries. Open: whether a stronger model does
with the same prompt (which separates the model from the representation), and whether reporting relations between
objects (equal shapes up to scale, as core knowledge of objects rather than a rule for this game) would let a
small one.

Then Claude Sonnet 5.5 on the same setup, seed 0, as an upper bound (it separates the model from the
representation). Its first call: the door's pattern must match "the target", and the switch probably changes it.
Second: the switch changes the pattern in the bottom-left box, and the door is shut until it matches. Third: **the
3x3 pattern in the bottom-left box, drawn at 2 cells a dot, must equal the door's 3x3 pattern; the switch edits it
and it resets when a life is lost; press until they match, then touch the door**, with a `plan(w)` that reads both
patterns from the frame and compares them: the hand-written dial and lock, found from the evidence. The level still
did not fall, and the trace says why: the plan was right and the agent ran out of budget carrying it out (the
pattern matched with 2 steps left and the door 20 away), because it refills only for the target in front of it.

One generic change to the executor, **top up while it is cheap** (a refill within 3 steps once less than half the
budget is left), and the same plans solve level 2 on seed 0 with the dial and lock turned off. With the dial and
lock on, the training games are unchanged by it (70 levels).

So far: the small model did not find the rule; the stronger one did, in three calls, from a prompt that holds only
what the agent saw. The bottleneck then moved from forming the hypothesis to executing it.

## Next

- LS20 level 3 and beyond; plan presses and refills as one sequence under the budget rather than one target at a
  time.
- Transfer by rule, not by look: carry roles (refill, rotator, door) matched by what an object does in its first
  contacts, not by its appearance.
- An LLM proposing rules where the enumerated outcomes do not explain an observation (the WorldCoder tier).
