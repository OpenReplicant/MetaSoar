# E-18 summary

450 cases, chunks of 50.

## Per chunk

| chunk | n | fine handler | class handler | template | large | fallback | accuracy | Inkling calls/case | Inkling s/case | small s/case |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 50 | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 76.0% | 1.10 | 57.5 | 0.9 |
| 2 | 50 | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 70.0% | 1.18 | 63.6 | 2.8 |
| 3 | 50 | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 82.0% | 1.14 | 49.8 | 4.6 |
| 4 | 50 | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 76.0% | 1.00 | 45.2 | 3.0 |
| 5 | 50 | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 76.0% | 1.16 | 73.4 | 3.9 |
| 6 | 50 | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 80.0% | 1.20 | 55.9 | 7.3 |
| 7 | 50 | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 78.0% | 1.04 | 47.1 | 5.4 |
| 8 | 50 | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 86.0% | 1.12 | 54.6 | 4.7 |
| 9 | 50 | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 80.0% | 1.02 | 49.8 | 5.3 |

## Cases 301 to 450

- coverage by templates and handlers: 0.0%
- accuracy of the stream: 81.3%
- Inkling alone on the same cases: 81.3%
- paired difference, stream minus Inkling alone: +0.0 points [+0.0, +0.0]
- cheap answers the exact shape would have admitted: 0, accuracy n/a
- cheap answers only the loose shape admitted: 0, accuracy n/a

## E-18 verdict lines

- classes with 9 or more cases in the first 300: 10; lookup and other: 13.3%
- coverage below 30%? YES (0.0%)
- accuracy more than 2 points below Inkling alone (interval's upper end below -2)? NO
- refutation condition met: YES

## Classes

| class | cases | cheap answers | accuracy | class handler | fine intents | withdrawn |
| --- | --- | --- | --- | --- | --- | --- |
| count | 128 | 0 | 68.8% | 0/10 discarded v1 | 52 | 0 |
| filter | 63 | 0 | 82.5% | 2/7 discarded v2 | 20 | 1 |
| superlative | 57 | 0 | 87.7% | 3/10 discarded v2 | 24 | 4 |
| other | 34 | 0 | 73.5% | none | 20 | 0 |
| ordinal | 32 | 0 | 93.8% | 1/3 shadow v1 | 7 | 5 |
| neighbour | 31 | 0 | 80.6% | 0/1 shadow v1 | 6 | 4 |
| comparison | 30 | 0 | 86.7% | 2/10 discarded v2 | 21 | 1 |
| lookup | 26 | 0 | 88.5% | 1/7 discarded v2 | 15 | 2 |
| sum | 19 | 0 | 78.9% | 2/10 discarded v2 | 9 | 1 |
| difference | 13 | 0 | 30.8% | 0/4 shadow v1 | 7 | 2 |
| list | 12 | 0 | 83.3% | 0/4 shadow v1 | 6 | 1 |
| yes_no | 4 | 0 | 75.0% | 0/0 shadow v1 | 4 | 0 |
| average | 1 | 0 | 100.0% | none | 1 | 0 |

Routes: {'new': 192, 'merged': 211, 'd1': 47}
