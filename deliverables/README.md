# Deliverables

The four written deliverables the brief asks for, plus the artifacts behind their
numbers.

| File | Deliverable |
|---|---|
| `devpost-description.md` | **#1 — Written project description.** The text submitted to Devpost: how the solution addresses the problem statement, development tools, models, libraries, datasets and assets. |
| `robustness-summary.md` | **#4 — Robustness evaluation summary.** Clean images versus transformed images: headline comparison, all seven transformation families, all twenty individual conditions, the fair comparison against a baseline given our operating point, results on three sets we never fitted on, compute cost, and limits. Generated from the committed artifacts by `scripts/build_robustness_summary.py`, so it cannot drift from the results. |
| `error-analysis-note.md` | **#5 — Error analysis note.** Representative false positives and false negatives with their scores and conditions, the measured mechanism behind each failure mode, the blind spot in our own abstention policy, and the trade-offs we accepted. |

Deliverable **#2** is this repository. Deliverable **#3** is the demo video:
<https://youtu.be/KUedfboxC-Q>

Every figure in these documents is reproducible with:

```bash
.venv/bin/python scripts/run_eval.py --config configs/frozen.yaml
```
