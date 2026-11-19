# Where the work stands, and what is next (2026-11-19, evening)

A handoff for the next session, local or in the cloud. Read `README.md`, `docs/spec.md` and `DECISIONS.md` first.

## State

- `main`: Soar 9.6.5 unchanged, the adapter (`metasoar/`), the hook, and Morphogen as the judge
  (`.github/workflows/morphogen.yml`, pinned to `judge.yml@21b347f`).
  - BabyAI rules: PRs #1 and #2.
  - ARC-AGI-3: perception and a map of states learned by playing, #4 (M-12), passed on `arc3-heldout`.
  - The judge runs `metasoar.arm` (#7): ARC-AGI-3 cases go to `atlas.play` if the tree has `atlas/`, everything else
    to `metasoar.play`. `main` has no `atlas/`, so the Soar agent plays everything.
  - The policy's scope: `agent/**/*.soar`, `agent/perception/**/*.py`, `atlas/**`.
- Refused and closed: #6, curiosity rules (M-13; 2 better, 0 worse); #8, the atlas arm (M-14; 0 better, 12 worse).
  Both gained on the training games through rules read off them, and neither carried to the held-out games.
- The atlas prototype: branch `claude/atlas-prototype` (`atlas/`, `docs/atlas.md`). 70 levels on the training games.
- 4 of `arc3-heldout`'s 200 verdicts used.

## What the verdicts say

Rules written by the author after watching training games fail do not generalise, however general they are
written: of four ARC-AGI-3 verdicts, one passed. The pass (#4) was broad exploration with a map; the
two refusals added targeted behaviour on top or in its place. A rule the agent did not find for itself is one
more thing for the held-out games to break.

## Next

1. **The model tier of the atlas** (`docs/atlas.md`, "The first experiment"): where the enumerated outcomes do not
   explain an observation (a surprise), a model proposes a claim (a transition rule, a latent variable, a goal), and
   the agent tests it by playing. First test: with the dial and lock deleted from `atlas/agent.py`, does it recover
   that rule on LS20? Then the five training games where nothing has scored (SK48, RE86, DC22, SB26, TR87).
2. **Exploration as the floor.** Whatever is built on claims keeps the Soar agent's coverage of actions and points
   underneath: claims may order what to try, not cut what gets tried.
3. **Spend verdicts only on mechanisms.** Open a judged PR when a training gain comes from claims the agent made, not
   from rules written against the training games.

Later:
- the store: claims with evidence and status in Substrate's Postgres once a model proposes them (provenance,
  retraction), not before;
- the three-way comparison: plain Soar, Soar with the hook, and Haiku 5.5 as the plain LLM player;
- ARC-AGI-1 as the next suite.

## How to measure

In the sandbox image (`docker run --rm -v $PWD:/work:ro <image> sh -c '...'`), one episode:

    echo '{"env": "arc3:VC33", "seed": 0, "max_steps": 500}' | python3 -m metasoar.play

`python3 -m metasoar.arm` is what the judge runs (the atlas for ARC-AGI-3 when `atlas/` is present);
`python3 -m atlas.play` runs the atlas alone.

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
