# Decisions

Append-only: a decision changes by a new row that supersedes it. Substrate's rows S-154 to S-161 led here.

| ID | Decision | Status |
| --- | --- | --- |
| M-01 | **MetaSoar is the original Soar with one hook to Substrate; its spec is `docs/spec.md`** (2026-11-18; carried from Substrate's `docs/soar.md` at S-161). | decided |
| M-02 | **Soar 9.6.5 from its release zip, not yet built from source** (2026-11-18). `SoarSuite_9.6.5-Multiplatform.zip` (the asset re-uploaded 2026-05-11), sha256 `cf5ef7d3b143fc049e8b118fb005867c69c6aeccb9451f5eab95c8a40517ca1d`, the digest GitHub's API reports for it, checked at build. It ships Linux x86-64 binaries (`libSoar.so`, `soar`) and Python SML bindings on the stable ABI (`_Python_sml_ClientInterface.abi3.so`), built for glibc 2.34+ (its release notes); the image is `python:3.13.17-slim-bookworm` (glibc 2.36). Eaters and TankSoar are not packaged in this release; its 38 demo agents are. Building from source comes when the architecture lineage starts. | decided |
| M-03 | **The watcher reads the goal stack after every decision cycle, from outside the agent** (2026-11-18). `metasoar/run.py` registers for SML's after-decision-cycle event and runs `print --stack`. First run: `water-jug-simple` solves the puzzle with no substate (7 and 95 decisions on two runs: its operator choices are random among indifferent ones); `water-jug-look-ahead` solves it in 399 decisions, 378 of them in substates (operator ties, evaluated in operator no-change substates), at most 31 deep, in 0.07 s. So a tie is normal problem solving there, as the spec says: the hook's trigger must be no progress, depth reached or recurrence, not any substate. | decided |
