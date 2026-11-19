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

## Next

- Latent state: count what a kind's repeated contact does (the second rotator press LS20's level 2 needs), after
  AutumnSynth's invented automata.
- Claims carried between levels are kept now; between games, the library (the slow loop).
- An LLM proposing rules where the enumerated outcomes do not explain an observation (the WorldCoder tier).
