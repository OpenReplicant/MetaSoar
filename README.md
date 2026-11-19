# MetaSoar

**The original Soar, unchanged, with Substrate on its impasses.** When Soar gets stuck in a way its own knowledge
cannot get out of, a watcher outside the agent hands the trace to [Substrate](https://github.com/OpenReplicant/Substrate),
which proposes a change: new rules, new settings, or, eventually, a change to the architecture itself. Each change
is judged by [Morphogen](https://github.com/OpenReplicant/Morphogen) on cases the builder never sees, and let in by
a gate. Nothing else is ours. What accumulates, and whether it rediscovers what we might have built in, is the
result.

**The test:** given an environment it has never seen (a game, a terminal, a conversation), through one generic
adapter, does it get better over episodes, and does what it learned make the next one faster to learn? Compared
with vanilla Soar and a vanilla LLM agent. The design is [`docs/spec.md`](docs/spec.md); the reasons are in
[`DECISIONS.md`](DECISIONS.md).

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
