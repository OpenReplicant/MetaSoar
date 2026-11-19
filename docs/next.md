# Where the work stands, and what is next (2026-11-19)

A handoff for the next session, local or in the cloud. Read `README.md`, `docs/spec.md` and `DECISIONS.md` first.

## State

- `main`: Soar 9.6.5 unchanged, the adapter (`metasoar/`), the hook, and Morphogen as the judge
  (`.github/workflows/morphogen.yml`, pinned to `judge.yml@21b347f`). BabyAI rules merged in PRs #1 and #2. The
  policy's scope includes the agent's perception (`agent/perception/**/*.py`, PR #3).
- PR #4 (branch `claude/exciting-wozniak-0sof8t`, `ce9ca28`): ARC-AGI-3 perception and a map of states learned by
  playing (M-12). **Passed** by the judge on `arc3-heldout`: levels 0.083 to 0.25 a case (9 better, 1 worse, 38 tied,
  p = 0.011); `wall_seconds` 1.08 to 3.09 s. Waiting for the owner to merge. It has used 2 of the case set's 200 verdicts.
- Training games, seeds 0 to 19, 500 steps: VC33 31 levels, S5I5 9, the other 7 games 0 or 1 between them.

## Next

1. **Learn what a level asks, not only where it has not been.** The agent covers LS20's maze in about 100 steps but never
   learns that the key it carries must match the door. Candidates, all game-agnostic:
   - progress signals other than a level: a change that persists across steps, or that matches part of the scene
     elsewhere (the key's shape against the door's);
   - remembering, across attempts and levels, the kinds of steps that came before a level was completed.
2. **VC33 stops at 2 levels.** Attempts there last 50 steps. Find out whether level 3 needs a longer sequence than
   one attempt explores, or something the rules forbid (points are ruled out for a level after doing nothing once).
3. **Keep the time bound in view.** The bound is 5 s worse a case than `main`; PR #4 is about 2 s worse on held-out
   games, BP35 about 4 s on training. Soar's joins hash on the identifier: put new memory under a node or as a single
   symbol, never as a flat set that a negated conjunction scans.

Later:
- the three-way comparison: plain Soar, Soar with the hook, and Haiku 5.5 as the plain LLM player, on the
  owner's subscription;
- ARC-AGI-1 as the next suite.

## How to measure

In the sandbox image (`docker run --rm -v $PWD:/work:ro <image> sh -c '...'`), one episode:

    echo '{"env": "arc3:VC33", "seed": 0, "max_steps": 500}' | python3 -m metasoar.play

The judge plays 500 steps a held-out case; measure training games at 500 too, on at least 10 seeds a game: with 3
seeds, the noise is as large as most changes. `trials/baseline/run.py` covers BabyAI only.

## Rules for whoever builds here

- **Never read the held-out cases.** That covers `OpenReplicant/morphogen-judge`, held-out seeds and the
  source of held-out games. A cloud session gets GitHub access to this repository only.
- **Learn ARC games by playing them.** Only the 9 training games may be played: SK48, S5I5, TR87, BP35,
  RE86, DC22, LS20, VC33 and SB26 (`deploy/sandbox/fetch_arc3.py`). Never read their source.
- **Each push to a judged PR spends a held-out verdict** (200 a case set). Push when the training games show a clear
  gain, not to probe the held-out set.
- **Pinned versions:** Soar 9.6.5 from the release zip (its sha256 is in `deploy/sandbox/Containerfile`),
  gymnasium 1.4.0, minigrid 3.2.0, arc-agi 0.9.9 and arcengine 0.9.3. The sandbox image is
  `ghcr.io/openreplicant/metasoar-sandbox@sha256:846875ecea32834ee9d44635128d382502086362341cf91c559a1b195ab1033d`.
  Without a container engine, install these exact versions directly.
- **No secrets are needed to build.** The judge's secrets live in the repository's `morphogen-judge`
  environment.
- **Don't edit a judged PR's description**; doing so re-triggers the judge. Merging is the owner's.
