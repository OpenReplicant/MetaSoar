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

Step 1 of the spec: Soar 9.6.5 runs in a container, driven from Python, and its impasses are seen from outside the
agent.

```sh
podman build -t localhost/metasoar-soar:9.6.5 -f deploy/soar/Containerfile .
podman run --rm -v "$PWD:/app:ro,Z" -v "$PWD/.state/run:/out:Z" --userns=keep-id \
  localhost/metasoar-soar:9.6.5 python3 -m metasoar.run water-jug-look-ahead/water-jug-look-ahead.soar 2000 /out
```

## Parts

| Part | Where |
| --- | --- |
| Soar 9.6.5, from its release, digest-checked | `deploy/soar/` |
| A run, with the goal stack read after every decision | `metasoar/run.py` |

Soar is under the BSD licence (its `LICENSE.md`); MetaSoar's own licence is not chosen yet.
