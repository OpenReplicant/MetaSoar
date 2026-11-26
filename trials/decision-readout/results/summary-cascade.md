# E-04a cascade: d1-2B first, Inkling when unsure

Offline, on the 1400 cases both models read; choices made on `fit` (621 cases), measured on `eval` (779 cases).
Slices routed straight to Inkling (d1-2B more than 10% below it on `fit`): atbench500, medmcqa, medqa_usmle, mmlu_pro, prompt_injections.

| Policy | Accuracy | Against Inkling alone [95% CI] | Sent to Inkling | Mean s per decision | Median s |
|---|---|---|---|---|---|
| d1-2B alone | 0.633 | -0.177 [-0.217, -0.134] | 0% | 0.30 | 0.15 |
| Inkling alone | 0.810 | +0.000 [+0.000, +0.000] | 100% | 9.42 | 4.67 |
| threshold (t = 0.542) | 0.769 | -0.041 [-0.066, -0.016] | 38% | 3.44 | 0.30 |
| routed + threshold (t = 0.000) | 0.810 | +0.000 [-0.020, +0.019] | 58% | 7.16 | 3.41 |
| oracle | 0.865 | +0.055 [+0.040, +0.074] | 37% | 4.53 | 0.23 |
| Jev 1.13 (reference) | 0.843 | | | | |

Threshold sweep on `eval` (no routing), for the shape of the trade-off:

| t | Sent to Inkling | Accuracy | Mean s per decision |
|---|---|---|---|
| 0.5 | 31% | 0.748 | 2.18 |
| 0.6 | 44% | 0.786 | 4.26 |
| 0.7 | 56% | 0.807 | 6.40 |
| 0.8 | 67% | 0.820 | 7.93 |
| 0.9 | 77% | 0.818 | 8.59 |
| 0.95 | 83% | 0.813 | 8.87 |
| 0.99 | 92% | 0.810 | 9.28 |

Per slice on `eval`, routed + threshold policy:

| slice | n | d1-2B | Inkling | cascade | sent to Inkling |
|---|---|---|---|---|---|
| aegis2 | 55 | 0.818 | 0.745 | 0.818 | 0% |
| aegis2_response | 54 | 0.833 | 0.667 | 0.833 | 0% |
| atbench500 | 59 | 0.559 | 0.966 | 0.966 | 100% |
| jailbreak_classification | 55 | 0.945 | 0.982 | 0.945 | 0% |
| medmcqa | 108 | 0.426 | 0.796 | 0.796 | 100% |
| medqa_usmle | 114 | 0.491 | 0.842 | 0.842 | 100% |
| mmlu_pro | 118 | 0.339 | 0.551 | 0.551 | 100% |
| prompt_injections | 51 | 0.725 | 0.902 | 0.902 | 100% |
| pubmedqa | 51 | 0.667 | 0.745 | 0.667 | 0% |
| scienceqa_text | 114 | 0.921 | 0.982 | 0.921 | 0% |
