# WTQ recurrence: can E-18 test the ladder? (no models)

Made by `wtq_recurrence.py` on `problems_test1k.json` (1,000 questions sampled with `random.Random(18)` from WTQ's
`pristine-unseen-tables`; see `wtq.py`), read through `stream.load_cases` in the runner's fixed order (sorted ids,
`random.Random(17)` shuffle). The first 300 and the first 600 questions are measured. Gold answers are not read.

## Table size (what the large model reads)

| | median | 90th percentile | maximum |
|---|---|---|---|
| rows | 15 | 40 | 517 |
| columns | 6 | 9 | 21 |
| characters of `table` | 1214 | 3890 | 26534 |

At about 4 characters a token, the median table is about 303 tokens and the 90th percentile about 972. `stream.show` puts a table in as JSON, in each of 3 examples of a handler prompt, so handler prompts are several times longer than that.

## Table shapes (`stream_v2.shape`)

| First n cases | Same table as an earlier case | Distinct shapes | Shapes seen once | Shapes seen 9+ times | Cases whose shape was seen before | Largest shape |
|---|---|---|---|---|---|---|
| 300 | 29.3% | 156 | 89 | 5 | 48.0% | 15 cases |
| 600 | 47.8% | 221 | 80 | 6 | 63.2% | 33 cases |

A looser shape (number of columns, and for each column whether every cell looks numeric or blank): first 300: 87 shapes, 7 seen 9+ times, 71.0% of cases repeat one; first 600: 117 shapes, 12 seen 9+ times, 80.5% of cases repeat one.

## Operation classes by rules

Rules (`RULES` in `wtq_recurrence.py`, first match wins) were written from `problems_dev1k.json`, a sample of the training split, and then run on the stream.

| Class | First 300 | Share | First 600 | Share | Example (from the stream) |
|---|---|---|---|---|---|
| count | 101 | 33.7% | 220 | 36.7% | how many total derivatives are cold water soluble? |
| superlative | 45 | 15.0% | 90 | 15.0% | which nation earned the most gold medals in the 2004 summer paralympics? |
| ordinal | 37 | 12.3% | 66 | 11.0% | what year was the last diesel built? |
| lookup | 33 | 11.0% | 63 | 10.5% | which la metro green line station also connects to the silver line? |
| neighbour | 21 | 7.0% | 50 | 8.3% | after what year no 100 kroooni issued |
| comparison | 18 | 6.0% | 32 | 5.3% | is anastasija katriova more or less than 1.8m tall? |
| difference | 8 | 2.7% | 21 | 3.5% | what is the difference in length between the amvets memorial highway and the horseneck beach connector? |
| list | 13 | 4.3% | 18 | 3.0% | name an athlete from the same country as schroder. |
| sum | 9 | 3.0% | 16 | 2.7% | what is the total amount of engines with a power of 142 kw? |
| other | 9 | 3.0% | 15 | 2.5% | position one is vacant, but who holds the officer position of number two? |
| yes_no | 5 | 1.7% | 7 | 1.2% | are there any years in which he did not use a dallara chassis? |
| average | 1 | 0.3% | 2 | 0.3% | what is the average index of the oscar de la hoya amino charter school? |

## Recurrence of classes

A handler in E-17d is written from 3 labelled cases and promoted after 9 of 9 agreements on later ones, so a class needs about 12 cases before anything is cheap. "Ceiling" is the share of cases that arrive after their class has had 12 cases (counted from `lo`, the first case measured): an upper bound on handler coverage, which assumes every handler is written and promoted on time and is right. With the shape gate (E-17d's rule that a promoted handler answers only a shape it has agreed on), a case counts only if its table shape was already seen among that class's earlier cases.

| Keys | First n | Distinct | Seen once | Seen 9+ times | Cases whose key was seen before | Ceiling, no shape gate | Ceiling, shape gate | Ceiling, loose-shape gate |
|---|---|---|---|---|---|---|---|---|
| operation class | 300 | 12 | 1 | 9 | 96.0% | 61.3% | 15.0% | 30.7% |
| operation class | 600 | 12 | 0 | 10 | 98.0% | 78.5% | 24.2% | 45.8% |
| fine class (second level) | 300 | 15 | 1 | 12 | 95.0% | 51.0% | 11.7% | 24.0% |
| fine class (second level) | 600 | 15 | 0 | 13 | 97.5% | 72.5% | 19.3% | 38.8% |

At the 450 cases a run could use (E-18's draft, in chunks of 50): ceiling by operation class 71.8% with no shape gate, 20.7% with the shape gate, 38.9% with the loose-shape gate; by fine class 63.8%, 15.8% and 31.8%.

Over the last 150 of 450 (cases 301 to 450, where E-17b and E-17d measured), the ceiling is 92.7% / 32.0% / 55.3% by operation class (no gate / exact-shape gate / loose-shape gate) and 89.3% / 24.0% / 47.3% by fine class.

Classes with 9 or more cases, by n:

- first 300: count 101, superlative 45, ordinal 37, lookup 33, neighbour 21, comparison 18, list 13, sum 9, other 9
- first 600: count 220, superlative 90, ordinal 66, lookup 63, neighbour 50, comparison 32, difference 21, list 18, sum 16, other 15

Fine classes with 9 or more cases:

- first 300: count:plain 70, ordinal 37, superlative:max 35, lookup 33, count:condition 31, comparison 18, list 13, neighbour:after 11, superlative:min 10, neighbour:before 10, sum 9, other 9
- first 600: count:plain 160, superlative:max 70, ordinal 66, lookup 63, count:condition 60, comparison 32, neighbour:after 29, neighbour:before 21, difference 21, superlative:min 20, list 18, sum 16, other 15

### Class and shape together

A handler promoted for a (class, shape) pair would need that pair 9+ times:

- first 300: 248 pairs, 0 seen 9+ times, 215 seen once
- first 600: 445 pairs, 2 seen 9+ times, 361 seen once

## What the rules are and are not

The classes are rough. They are regular expressions on the question, with no model and no table, so a class is a guess at the operation, not a measured intent. The `lookup` class is a catch-all for who/what/when/where questions with no other cue and holds many different operations (a column read, a row filter, a join of two cells); it is not one operation and no one handler would serve it. `count` mixes row counts with counts under a condition, and `sum` is rarer than its share of 'total' questions suggests, since "total number of films" is a row count. The check below is the author's reading of 30 questions, not a measurement of agreement: 27 look plausible and 3 are doubtful ("by what number of votes did nixon lose to brown" is a difference, labelled count; "what is the total number of wins" is a sum or a row count; "each callsign in this list begins with..." is not a question). The reading is of the sample as generated at the time of writing.

| Question (random 30 of the first 300) | Class | Fine class |
|---|---|---|
| which ship had a greater amount of lives lost, charles s. price or plymouth? | comparison | comparison |
| what was the total number of goals scored by johnson and stewart? | sum | sum |
| what yacht had the longest loa? | superlative | superlative:max |
| what is the total number of wins? | sum | sum |
| is maramoros larger or smaller than jasmund? | comparison | comparison |
| how many medals in total did the netherlands take home for speed skating in the 1972 olympics? | count | count:plain |
| name an athlete from the same country as schroder. | list | list |
| each callsign in this list begins with... | other | other |
| how long did daniel tovar play arturo? | lookup | lookup |
| was the porpoise seized before or after the independence | comparison | comparison |
| which award is listed the most on this chart? | superlative | superlative:max |
| which was the only year to only compete in one type of tournament? | lookup | lookup |
| who has more points, popov or aquaro? | comparison | comparison |
| who did this player face before he faced david wheaton in coral springs, florida in 1993? | neighbour | neighbour:before |
| what was the result of the only award given in 2012? | lookup | lookup |
| who was ranked last among this group? | ordinal | ordinal |
| what is the total amount of engines with a power of 142 kw? | sum | sum |
| who was the only person from the us to earn less than $65,000 on june 18, 1995? | lookup | lookup |
| how many players wore the number 25? | count | count:plain |
| how many presidenta have been the oldest living president at one pont? | count | count:plain |
| how many locations is the aini found in? | count | count:plain |
| did episode 8 or episode 9 have a better bbc three weekly ranking? | comparison | comparison |
| what is the total number of wins listed for the united states? | sum | sum |
| what is the gene function of cytoplasmich (tyrosine kinases?) | lookup | lookup |
| how many consecutive years has olga tereshkova competed? | count | count:plain |
| when did devo first release "beautiful world"? | ordinal | ordinal |
| which song has the most featured guests? | superlative | superlative:max |
| how many singles from the chart were played overall? | count | count:condition |
| which nation earned the most gold medals in the 2004 summer paralympics? | superlative | superlative:max |
| by what number of votes did nixon lose to brown in the county of sacramento? | count | count:plain |

## Reading

- Operation classes recur: by rules there are 12 classes, none seen once after 600 questions, and 9 or 10 of them seen 9 or more times. Recurrence of the class is not the limit.
- Table shapes do not recur: the exact shape of E-17d's gate is new for about half the cases at 300 and a third at 600, and no (class, shape) pair reaches 9 cases in the first 300. With that gate, no run of 300 to 600 cases can have a handler answer much more than the ceilings above (the exact-shape rows), and E-17d's own falsifier (under 30% answered) would be met by the gate, whatever the handlers do.
- The ceilings are upper bounds. They assume the handler is written and promoted on time and is right. Handler accuracy on WTQ is not measured here.
- The rules cannot say which classes one handler could serve. `lookup`, `list`, `other` and `yes_no` together are about a fifth of the stream and are not one operation each.

