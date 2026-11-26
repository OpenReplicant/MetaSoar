# The handler ladder (M-26)

The owner's idea: "a system could be defined as components by intent, which is morphogen's system blueprint, then
an LLM would handle the first raw inputs and write handlers to supercede it, remaining as an edge-case fallback and
error-correction, now also optimization via morphogen". This note puts that idea together with the published work
that each covers part of it, and with System 1's design (`docs/system1-skills.md`, M-21 and M-22). The first test
is E-17 (`docs/experiments.md`).

## Why this, after E-04

E-04a to E-04c showed two things. Local models read by their probabilities are calibrated enough to gate on. A gate
between two models gains little (+1.8 points over Inkling alone, from a table by question type), and a smarter gate
gains nothing more. Routing between models is not a dual system. Nothing was compiled, and JevBench has no repetition
to compile. The work that shows large gains (below) gets them from what is compiled from System 2's experience. A
better gate is not where those gains come from.

## What each piece of work contributes

| Work | Its piece | Its result | What it lacks |
| --- | --- | --- | --- |
| **Agentic Plan Caching** (Zhang et al., NeurIPS 2025, arXiv 2506.14852) | the intent as an exact cache key (one keyword from a small model); a plan template stripped of specifics, adapted by a small model | cost -50%, latency -27%, 96.6% of accuracy; GAIA $69 to $16 at 37.6% to 37.0% | still a model at run time; no judge; no demotion; no official code |
| **Agent Workflow Memory** (Wang et al., ICML 2025, arXiv 2409.07429) | workflows induced online from runs an evaluator judged successful | WebArena +51% relative success; up to 22.5 points within tens of examples | no saving in model calls; an LLM judge, so it can learn its mistakes; workflows used in 18.5% of tasks |
| **Program Distillation** (Zheng et al., arXiv 2611.19461) | a program written and revised by a model against scores, run with no model | 0.728 normalised on 27 Gymnasium tasks, PPO 0.656 | no fallback, no error correction; builds of 5 to 67 hours |
| **AnyS1** (Li et al., arXiv 2611.23751) | decisions as choices among options; a gate set on measured agreement with System 2 (95% or more on 50 runs); labels from two option orders | episode cost -75% to -91% | a 4B fine-tune (deferred on cost, M-26); thresholds not adapted online |
| **E-04** (here) | calibrated local readers (d1-2B, Inkling); gates kept simple | a gate by type beats Inkling alone by +1.8 [+0.3, +3.4] | nothing compiled |
| **Morphogen** | held-out judgment of every change; optimisation of what may change | (its own record) | |

## The loop, per intent

```
input
  ─► ELABORATE   the intent: an exact key (as APC); an unknown key goes to the nearest known intent
                 or a typed question; plus the state's other features
  ─► PROPOSE     the policies this intent has, cheapest first:
                   handler (a program, no model)
                   template (a plan, adapted by a small model)
                   workflow (in the large model's prompt)
                   the large model, raw
  ─► DECIDE      each policy's measured precision (its agreement with the large model on held-out
                 cases), preferences, constraints; the cheapest policy over its threshold wins
  ─► APPLY       with a check: the answer's type, constraints, the policy's own `expects:`
                 a failed check or an error: the large model answers; its answer corrects the case
  ─► RETAIN      every case kept per intent: state, policy, answer, check, the large model's answer
  ─► COMPILE     enough cases of one intent: induce a workflow, then a template, then a handler
  ─► JUDGE       a compiled policy is promoted only by Morphogen, on that intent's held-out cases
  ─► LIFECYCLE   shadow (proposes, does not act) → active → audited (a share still sent to the large
                 model); demoted when its surprises rise; thresholds re-set from audits
```

In System 1's terms the intent classifier is an elaborator. Matching intent to policy is a proposer, and the
decision weighs the proposals by preferences over features and predictions. The ladder is the skill ladder of
`docs/cognitive-model.md` (improvised, saved, chosen, automatic, demoted), with the rungs made concrete.

## What none of them does

- **A held-out judge for every promotion.** AWM's own LLM evaluator decides what it learns from.
- **The model kept as fallback and corrector.** Program Distillation deploys the program alone.
- **Demotion.** A policy that starts failing goes back down.
- **The rung chosen per intent** by measured precision and cost, not one rung for everything.
- **Thresholds adapted online** from audits. AnyS1 names this as future work.

## Costs and order

No fine-tuning comes first: every rung is memory, prompts or code on the local models. A fine-tuned fast model
(an AnyS1-style pointer, or a small T5 as in SwiftSage) is for intents with volume enough to pay for it.

## Experiments

- **E-17** (registered): the intent elaborator, templates, handlers, fallback and promotion by agreement with the
  large model, on a stream of TabMWP cases. TabMWP is templated, so intents recur by construction. It tests the
  mechanism, not its reach.
- **Next, if E-17 holds:** workflows as a rung; demotion and audits (E-07); unknown intents; a task family that is
  not templated (agent tool use from a recorded log, E-01).

## The research process uses the same discipline

The experiments here are registered before they run (M-24). The field now argues for the same discipline. POPPER (Huang et
al., ICML 2025) turns a hypothesis into falsification tests and combines their evidence while bounding false
positives. 2026 position papers (arXiv 2605.08956, 2608.05179) argue for machine-readable preregistration of AI
research. Two steps for this repository follow from them:
- **Registration as structured cards,** with a check that the registration's commit comes before its results'
  commit. E-04c's were in one commit.
- **POPPER's way of combining evidence in Morphogen's judge,** for verdicts over many related tests.
