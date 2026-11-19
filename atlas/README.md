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

| game | Soar, PR #6 | atlas, first tier |
|---|---|---|
| LS20 | 20 | 20 |
| VC33 | 31 | 23 |
| S5I5 | 9 | 5 |
| BP35 | 0 | 3 |
| RE86 | 2 | 0 |
| SK48 | 2 | 0 |
| DC22, SB26, TR87 | 0 | 0 |
| total | 64 | 51 |
| games with a level | 5 | 4 |
| slowest episode | about 8 s | 3.9 s |

On LS20 the first level falls out of the claims: it touches the untested rotator, the scene changes, it touches the
door. BP35 completes a level for the first time with any agent here.

## Hidden state (in `agent.py`; LS20 level 2 not solved yet)

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

## Next

- LS20 level 2: test whether the key survives a lost life; plan presses and refills as one sequence under the
  budget rather than one target at a time.
- Transfer by rule, not by look: carry roles (refill, rotator, door) matched by what an object does in its first
  contacts, not by its appearance.
- An LLM proposing rules where the enumerated outcomes do not explain an observation (the WorldCoder tier).
