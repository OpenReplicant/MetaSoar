# A catalog of patterns: language learned as templates, filled by deterministic processes (M-23)

A research spec, proposed 2026-11-25. Its decision is M-23. It is built on M-22's parts: the `fill` applier, typed
questions and the anti-unification compiler (`docs/system1-skills.md`).

## The idea

The owner (2026-11-25), on M-22's templates: "it could apply very broadly, to all sort of things and reminded me of
an idea i has around a language-learner that builds a catalog of rhetorical patterns as templates that can be filled
by symbolic/deterministic processes".

So: System 1 for producing language. The model writes freely only at an impasse. What it writes is recorded. Where
outputs recur in shape, the shape is compiled into a pattern: a template with typed slots. Next time, a proposer
chooses the pattern, and its slots are filled by handlers: facts by deterministic processes, choices by typed
questions, and only what nothing else can fill by a small model writing a bounded span.

## A pattern

| Part | What it is | Example |
| --- | --- | --- |
| **move** | what the pattern does, as a typed label | `concede-then-rebut`, `problem-cause-fix`, `claim-evidence-qualifier` |
| **when** | the situation it fits: features and the goal, as for any policy | the reader disagreed; the goal is to keep them |
| **template** | text with typed slots | "You're right that {concession}. {rebuttal}, because {evidence}." |
| **slots** | each one a handler, with its type | `evidence`: a query over the record; `concession`: a bounded span |
| **expects** | the predicted effect (M-22) | no follow-up asking the same thing |
| **cases** | the outputs it was learned from, and how each went | |

A slot may hold another pattern. So the catalog is a grammar of moves, not a list: an argument's `evidence` slot can
be filled by a `comparison` pattern, whose slots are facts.

## How it learns

1. **Record.** Every free output at an impasse is kept with its situation, its goal and, later, its outcome.
2. **Label the move.** A typed question names the move an output makes, from the catalog's labels plus `new`.
3. **Generalise.** Outputs with the same move are aligned, and anti-unification keeps what they share and makes
   what differs into slots. Each slot's type comes from what filled it across the cases: always a number from the
   record means a fact slot; one of a few phrasings means a choice slot; anything else means a free slot.
4. **Discriminate.** Where a pattern's outcomes split, near-miss mining (M-22) finds what differs between the cases
   that went well and those that did not, and that becomes a condition in `when`.
5. **Judge.** As every policy: held-out cases, shadow, then active (M-21).

A pattern with mostly free slots has learned little. The share of the output filled by deterministic and choice
slots is the measure of what was compiled.

## Lineage

Construction grammar (pairings of form and meaning at every size, from words to whole moves); Rhetorical Structure
Theory (how the parts of a text relate: concession, evidence, elaboration); the classic generation pipeline
(choosing content, planning the document, then realising it through templates); Schank's scripts. All of them were
short of examples to generalise from and of a way to fill the hard slots. A language model supplies both.

## Experiments

1. **Mining.** Take the agent's own replies on one recurring task (support answers, status reports, code-review
   comments). Run steps 2 and 3. Measure coverage (the share of held-out replies a pattern fits) and the compiled
   share of each fitted reply.
2. **Filled against free.** On held-out situations, a filled pattern against the model writing freely. Measure the
   outcome the task has (the reader's follow-up, edits a person made), factual errors, and cost. Blind preference
   by a judge model as a second measure, never the first.
3. **Nesting.** Allow slots to hold patterns. Does coverage rise without the outcomes falling?

**What would falsify it:**

- Text that is correct but stilted or repetitive, so outcomes fall even as errors do.
- Patterns that fit a situation's surface and miss its intent (M-22's tie and blocked impasses should catch
  these; if they do not, the `when` conditions are too thin).
- Coverage too low to pay for the catalog: if most situations still go to free writing, nothing was compiled.
