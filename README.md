# MetaSoar

**The cognitive layer of [Substrate](https://github.com/OpenReplicant/Substrate)** (M-15): how an agent inside an
environment perceives, attends, predicts and learns. Inspired by Soar, not Soar itself; "MetaSoar" is a working title.
Its hypothesis is [`docs/cognitive-model.md`](docs/cognitive-model.md): detectors and automatic processes post into
one picture of now, a deliberate process attends to a small part of it, everything learned is a predictive model with
provenance, and what deliberation solves is compiled into skills that run without it. The predictions there say what
would show it wrong. What exists, layer by layer, is [`docs/architecture.md`](docs/architecture.md).

Substrate is the framework (environments, gated actuators, pass-through to Claude Code, components judged against
it); the [Knowledge Kernel](https://github.com/OpenReplicant/kernel) is the store; the judge is held out of the
agent's reach ([Morphogen](https://github.com/OpenReplicant/Morphogen) is one). MetaSoar adds what an agent needs on
the inside, and a lockstep runtime (`envkit/`) for worlds faster than the wall clock: ARC-AGI-3, Super Mario Bros.
from the screen, and an organization's history replayed a day a tick.

**The test** stays: given an environment it has never seen, does it get better over episodes, and does what it
learned make the next one faster to learn? Judged on held-out cases, never on training results (M-14).

## Status

Soar 9.6.5 plays BabyAI (Minigrid) through one generic adapter, starting from four rules that pick actions at
random (success 5 to 55% by level, `trials/baseline`). Morphogen judges every change to the agent's rules on 60
held-out episodes (M-05). Next: the hook, sending a stuck step to Substrate.

```sh
podman build -t localhost/metasoar-sandbox -f deploy/sandbox/Containerfile .
echo '{"env": "BabyAI-GoToLocal-v0", "seed": 7}' | podman run --rm -i -v "$PWD:/work:ro,Z" localhost/metasoar-sandbox \
  python -I -c "import sys, runpy; sys.path.append('/work'); runpy.run_module('metasoar.play', run_name='__main__')"
```

## Parts

| Part | Where |
| --- | --- |
| Soar 9.6.5 and the environments, the image every episode runs in | `deploy/sandbox/` |
| The adapter: any Gymnasium environment onto Soar's I/O | `metasoar/adapter.py` |
| One episode, a case in and a result out (Morphogen's module) | `metasoar/play.py` |
| The agent: its rules, the only thing a judged change may touch | `agent/` |
| Morphogen: the policy, the scorer, the case generator | `.morphogen/`, `.github/workflows/` |

MetaSoar is under the Apache License 2.0 (`LICENSE`). What it fetches at setup keeps its own licence: Soar (BSD, its `LICENSE.md`), Minigrid (Apache-2.0), Gymnasium (MIT), the ARC-AGI-3 toolkit, engine and games (MIT).
