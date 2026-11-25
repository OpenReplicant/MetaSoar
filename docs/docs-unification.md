# The four projects' docs: what is already unified, what is stale, and MetaSoar as the experimental branch

A proposal, 2026-11-25. The owner asked whether the docs of Morphogen, the kernel and Substrate need tidying or
unifying, with MetaSoar as the experimental branch. Read from each repository's main on that date. Nothing outside
this file is changed by it.

## Already unified

The shape was settled on 2026-11-24, and the four repositories agree on it:

| Where | What it says |
| --- | --- |
| Substrate `docs/framework.md`, `docs/repos.md` (S-209 to S-214) | the hub: two products (Morphogen, the kernel), one distribution (Substrate), the research (MetaSoar); every dependency a contract, no cycles |
| Morphogen `README.md`, `BRIEF.md` ("Where it sits") | the kit; the kernel optional above it; Substrate installs its plugin; MetaSoar's System 1 skills a planned consumer of the judge |
| kernel `README.md`, `CLAUDE.md` (D-130) | Morphogen and Substrate as neighbours, neither a dependency |
| MetaSoar `README.md` ("Where MetaSoar sits", M-20) | the same table, from MetaSoar's side |

So the docs do not need a new structure. Substrate's `docs/framework.md` is the hub, and each repository has a
"where it sits" section pointing to it.

## What is missing: MetaSoar as the experimental branch

No document says that new mechanisms are tried in MetaSoar before they move into the kit, the kernel or the
distribution. The kernel's docs do not mention MetaSoar at all. Proposed wording, one sentence in each "where it sits"
section and a row in Substrate's `docs/repos.md`:

> **MetaSoar is the experimental branch.** New mechanisms are tried there as trials, each judged by Morphogen. One
> that passes moves to the repository that owns its role (the kit, a kernel module, or the distribution) by a pull
> request that links the trial and its verdict.

With it, a graduation path:
- **A trial** in MetaSoar (`trials/<name>/`, registered in `docs/experiments.md`).
- **A verdict** from Morphogen's judge, in its evidence log; the kernel's `encoder-morphogen` (D-99) can ingest it.
- **A pull request to the owner** that cites the verdict. For example, E-04a's readout settings would go to
  whatever runs typed questions, and the observed-state encoders to the kernel.

## Overlaps to resolve before building

**Observed state and document ingestion are already planned in the kernel.** Its milestone 6 lists:
- a self encoder, a git and pull-request encoder, and session hooks, so sessions "use the kernel as their own memory";
- a documents encoder on Docling (MIT), keeping sections and quotes;
- structured data through RML.

D-67's `verifier-quotes` already checks that each extracted claim's quote occurs in its source. `encoder-compose`
and `decoder-compose` (D-125) already carry compose files into the kernel and back.

So `docs/on-substrate.md`'s background observers, and the research system's paper ingestion, should be kernel
encoders. For Morphogen users without a kernel, a thin file-based version in the kit is still worth having. Which one
comes first is the owner's call.

## Stale in MetaSoar

| Item | Now | Fix |
| --- | --- | --- |
| `.morphogen/policy.json` | Morphogen's old `morphogen.policy/v1` format | migrate to `spec.morphogen` (v1) on entities in `catalog-info.yaml`, the format Morphogen reads now: a code and config change, to be judged like any other |
| `docs/architecture.md`, `docs/cognitive-model.md` | cite `envkit/...` | each already carries a note that envkit was retired (Substrate S-196); leave as history, or move both to `docs/archive/` |
| `docs/spec.md` | mentions the voice head and the companion | both removed from Substrate (S-195); mark the passages as history |
| `docs/handoff-2026-11-25.md` | says the cell definition was read from `.morphogen/policy.json` and is unverified | answered by `docs/on-substrate.md`, from Morphogen's own repository |
| `docs/handoff-2026-11-20.md` | superseded by the 2026-11-25 handoff | move to `docs/archive/` |

## Conventions worth adopting everywhere

- **Cite another repository's decisions with its name:** `Substrate S-169`, `kernel D-67`, `Morphogen #104`, as
  MetaSoar mostly does already. A bare `S-169` inside MetaSoar is ambiguous.
- **One "now" page per repository:** Substrate `docs/plan.md`, MetaSoar `docs/next.md`, Morphogen `PLAN.md`, the
  kernel's current milestone. Handoffs are dated and archived once a newer one or the "now" page covers them.

## Proposed order

1. Add the "experimental branch" sentence to the four "where it sits" sections and to Substrate's `docs/repos.md`.
   That means one small pull request in each repository.
2. Archive MetaSoar's superseded docs and mark its stale passages.
3. Migrate `.morphogen/policy.json` to Morphogen's current format, as MetaSoar's first judged change on the current
   kit.
