# CHECKPOINT "NIMS" — the guaranteed-submission baseline

**Frozen:** 2026-08-28 · **Commit:** `2f6d83beac49d2c5abddc758c45da861960489e8`
**Git tag:** `checkpoint-nims`

> **Purpose.** This is the fallback and the yardstick. Everything built after this point is an
> experiment. If a later change is worse, ambiguous, or simply doesn't feel right, we ship THIS.
> "Compare with checkpoint Nims" means: compare against the numbers on this page.
>
> **This state is validated, frozen, and complete as a submission.** Nothing below depends on any
> work that comes after it.

## The product at this checkpoint

Single-stage cascade: CF-384 primary → quality descriptors + 3 self-probes → 1,827-param MLP
(worst-group loss) correction head → 17-param reliability head → verdict + reliability + DEFER.

- **21,814,571 parameters** shipped (**1.09%** of the 2B cap)
- Single frozen threshold **0.4667367651127279** across all 20 conditions
- Frozen abstention threshold **0.866080** (reliability value, chosen on dev)
- Served on the live path: Gradio, `scripts/infer_dir.py`, eval harness all share one
  `PredictionService`; **cache/live parity** verified with **0 verdict disagreements** on 60,000
  cache rows and on 25 images end-to-end from pixels — i.e. the offline cache and the live service
  agree under *serving* semantics. That is not the same claim as training/serving feature parity,
  which is **not** zero: `probe_flip` was trained at threshold 0.5 and is served at 0.4667367651,
  which moves 550 of those 60,000 feature rows, 2 verdicts, and p_fake by at most 0.298885
  (`tests/test_probe_flip_semantics.py`; worst-family recall is unchanged at 0.8258)

## The numbers that define this checkpoint

Untouched internal test, 3,000 sources x 20 conditions = 60,000 rows:

| metric | value |
|---|---|
| worst-family fake recall | **0.8258** |
| vs primary @0.5 | 0.1227 |
| vs primary @ test-fitted FPR-matched (conservative) | **+0.4916** CI95 [+0.475, +0.508] |
| clean fake recall | 0.9613 |
| clean FPR | 0.0833 (breaches our own 0.0756 cap — reported, not re-tuned) |
| overall accuracy | 0.9090 |
| fake->real flip rate | 0.0530 (primary: 0.2664) |
| dev -> test generalisation | 0.8144 -> 0.8258 (went up) |

With abstention (defer least-reliable 20%):

| | coverage | accuracy | worst-family |
|---|---|---|---|
| decide everything | 1.000 | 0.9090 | 0.8258 |
| **defer 20%** | 0.799 | **0.9317** | **0.9136** |

Latency p50 **127.9 ms** (baseline CF alone 18.8 ms); peak RSS ~1.24 GB.

## Deliverables complete at this checkpoint

- README §7 results, §8 limitations, §9 parameters + ops evidence
- `deliverables/error-analysis-note.md` — regenerated on protected data
- `deliverables/devpost-draft.md` — no `[PENDING]`, all numbers protected
- `deliverables/video-script.md` — v2, fully numbered, numbers->artifact table
- `tests/test_published_numbers.py` — binds every published number to its artifact
- **Suite: 699 passing**

## Known state / caveats at this checkpoint

- Sealed reference run IN FLIGHT (~20k of 174,380 rows). Result unknown; will be reported as-is.
- Codex (AGENT-B) has not peer-reviewed the 28 Aug work.
- Owner actions outstanding: repo public, MIT approval, clean-history push, video recording.
- One-stage system: no second expert, no adaptive compute (both built, both failed on evidence).

## Rollback

```
git checkout checkpoint-nims        # or: git diff checkpoint-nims HEAD
```

The shipped checkpoint file at this state is
`results/router-fitting-v2/router_reliability.pt` with
`results/router-fitting-v2/threshold-artifact.v1.json`.
