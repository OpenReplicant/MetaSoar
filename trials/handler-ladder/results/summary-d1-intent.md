# d1-2B as the intent elaborator (offline, the E-17 stream's 300 questions)

| Grouping | Groups | Seen once | Purity (1 - misroutes) | Inverse purity (1 - fragmentation) | Pairwise F1 |
|---|---|---|---|---|---|
| reference (operation rules) | 22 | 0 | 1.000 | 1.000 | 1.000 |
| LFM3 keys (the stream) | 54 | 23 | 0.760 | 0.613 | 0.479 |
| embedding shortlist + d1-2B, t = 0.3 | 65 | 27 | 0.917 | 0.630 | 0.604 |
| embedding shortlist + d1-2B, t = 0.5 | 138 | 104 | 0.967 | 0.497 | 0.448 |
| embedding shortlist + d1-2B, t = 0.7 | 217 | 200 | 0.997 | 0.327 | 0.263 |
