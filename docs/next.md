# Where the work stands, and what is next (2026-11-18)

A handoff for the next session, local or in the cloud. Read `README.md`, `docs/spec.md` and `DECISIONS.md` first.

## State

- `main`: Soar 9.6.5 unchanged, the adapter (`metasoar/`), the hook, and Morphogen as the judge
  (`.github/workflows/morphogen.yml`, pinned to `judge.yml@21b347f`). BabyAI rules merged in PRs #1 and #2,
  both passed by the judge on held-out seeds.
- Branch `agent/arc3` (`b73b42e`, not yet judged):
  - perception: `agent/perception/main.py` turns frames into objects and effects;
  - exploring rules: `agent/explore.soar`.
  - Training games (9 games, 3 seeds, 1000 steps): random rules completed 0 levels. The exploring rules
    completed 2 levels on VC33 on every seed and 0 on the other 8 games.
  - RE86 ran at 0.86 s per step because its `^visited` memory reached about 10M WMEs. Memory is now keyed by
    colour and size; this has not been re-measured.

## Next

1. **Re-measure `agent/arc3`** on the training games: RE86's time per step and VC33's levels
   (`trials/baseline/run.py`, inside the sandbox image).
2. **Widen the scope, alone, on `main`:** add `agent/perception/**/*.py` to `.morphogen/policy.json`'s
   scope. A change to the policy never goes in the same PR as the work it judges.
3. **Open `agent/arc3` as a PR** for `arc3-heldout`. The card scope must match the policy.
4. **Check the judge's log:** "artifact … removed (204)" should appear twice, and only the `admission` and
   `verdict` artifacts should be left.

Later:
- the three-way comparison: plain Soar, Soar with the hook, and Haiku 5.5 as the plain LLM player, on the
  owner's subscription;
- ARC-AGI-1 as the next suite.

## Rules for whoever builds here

- **Never read the held-out cases.** That covers `OpenReplicant/morphogen-judge`, held-out seeds and the
  source of held-out games. A cloud session gets GitHub access to this repository only.
- **Learn ARC games by playing them.** Only the 9 training games may be played: SK48, S5I5, TR87, BP35,
  RE86, DC22, LS20, VC33 and SB26 (`deploy/sandbox/fetch_arc3.py`). Never read their source.
- **Pinned versions:** Soar 9.6.5 from the release zip (its sha256 is in `deploy/sandbox/Containerfile`),
  gymnasium 1.4.0, minigrid 3.2.0, arc-agi 0.9.9 and arcengine 0.9.3. The sandbox image is
  `ghcr.io/openreplicant/metasoar-sandbox@sha256:846875ecea32834ee9d44635128d382502086362341cf91c559a1b195ab1033d`.
  Without a container engine, install these exact versions directly.
- **No secrets are needed to build.** The judge's secrets live in the repository's `morphogen-judge`
  environment.
- **Don't edit a judged PR's description**; doing so re-triggers the judge. Merging is the owner's.
