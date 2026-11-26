# MetaSoar

**The research layer: cognitive architecture for agents that get better from their own experience.** Its
baseline is the original Soar 9.6.5, unchanged. When the agent gets stuck in a way its own knowledge cannot get
out of (an impasse), a watcher outside the agent hands the trace to an improver: an ordinary agent harness with
[Morphogen](https://github.com/OpenReplicant/Morphogen)'s kit. The improver proposes a change (new rules, new
settings, eventually a change to the architecture). Morphogen judges each change on cases the improver never
sees, and a gate lets it in. What accumulates, and whether it rediscovers what we might have built in, is the
result. The headline hypothesis is impasse-driven compilation (M-17). Its first product-shaped output is
**System 1 skills** ([`docs/system1-skills.md`](docs/system1-skills.md), M-19): learned responses, triggers and
observers kept in an Agent Skill folder, each one judged.

**The test:** given an environment it has never seen (a game, a terminal, a conversation), through one generic
adapter, does it get better over episodes, and does what it learned make the next one faster to learn? Compared
with vanilla Soar and a vanilla LLM agent. The design is [`docs/spec.md`](docs/spec.md); the reasons are in
[`DECISIONS.md`](DECISIONS.md).

**Soar-derived, not Soar orthodox (M-24).** Soar 9.6.5, unchanged, is the baseline and the research engine; where
the design departs from Soar is listed in [`docs/system1-skills.md`](docs/system1-skills.md) ("Relation to Soar"),
and the wider bar is the Common Model of Cognition. The experiments, parts and the whole, are registered in
[`docs/experiments.md`](docs/experiments.md).

## Where MetaSoar sits (M-20)

| Project | Is | For MetaSoar |
| --- | --- | --- |
| [Morphogen](https://github.com/OpenReplicant/Morphogen) | the kit: map, research, catalog and optimise behind a judge (Substrate's S-209) | the judge of every change, and the improver's tools |
| [OpenEnv](https://huggingface.co/docs/openenv) | the environment standard | where experiments run (BabyAI and ARC-AGI-3 move onto it) |
| [the kernel](https://github.com/OpenReplicant/kernel) | Postgres made into a knowledge kernel | an optional store for claims and the record, when one is needed |
| [Substrate](https://github.com/OpenReplicant/Substrate) | the default distribution: a harness set up with the kernel and Morphogen, plus optional parts (S-211 to S-214) | where MetaSoar's agents can run; not required |

## Status

Soar 9.6.5 plays BabyAI (Minigrid) through one generic adapter, starting from four rules that pick actions at
random (success 5 to 55% by level, `trials/baseline`). Morphogen judges every change to the agent's rules on 60
held-out episodes (M-05). Next: the hook, sending a stuck step to the improver, and the System 1 skills
experiments (M-19).

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
