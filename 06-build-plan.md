# 06 — Build Plan: Phases & Stages

> **Status: EXECUTION PLAN**
> Written 26 Aug 2026 (evening). Deadline: **Devpost submission Mon 1 Sept, 12:00pm** (~5.5 days).
> Finalists announced 8 Sept; Grand Final 11 Sept (TikTok Singapore). Demo video: 3 minutes, public YouTube.
> Official webinar: **28 Aug, 5:00–5:45pm** — attend with protocol questions from `docs/08-risks-kill-criteria-open-questions.md`.

## What we are building

The **Adaptive Forensic Cascade** decided in `docs/03-recommended-architecture.md`:

```text
input image
  -> canonical decode + quality descriptors
  -> Community Forensics 384 (primary, 21.8M, HF: OwensLab/commfor-model-384, MIT)
  -> LOTA (cheap local/bit-plane expert, 23.6M, github.com/hongsong-wang/LOTA)
  -> 3 mild self-probes on primary (JPEG 92, crop ~97%, resize 0.90)
  -> OUR trained reliability/fusion router (tiny MLP, two heads)
       reliable  -> calibrated verdict
       uncertain -> WaRPAD behavioral rescue (RIGID backup) -> rescued fusion
  -> temperature+bias calibration -> REAL / AI-GENERATED / UNCERTAIN + reliability + evidence
```

The **trained router + reliability/abstention layer is our original contribution** — it maps directly onto Technical Execution (35%) and Innovation & Problem Insight (20%). Downloaded checkpoints stay frozen.

## Strategy principles

1. **Always submittable.** Every phase exit is a state that could be shipped. The fallback ladder (bottom of this file) says exactly what gets submitted if time dies mid-phase.
2. **Demo-ready in ~24h** (Phase 1 exit). Gradio first; UI polish is a Phase-5 stretch.
3. **Evidence over narrative.** Every component obeys the kill criteria in doc 08. A reported negative ablation is a strength, not a failure.
4. **Never touch the sealed WildFake reference subset** (COCO val2017 4,998 + DALL-E Advanced 8,843) for any fitting. Hash denylist enforced in code before every training job.
5. **Parameter compliance is trivial** (~22M + ~24M + router ≪ 2B) — document per-component counts anyway.

## Environment facts

- Local: Apple M4 Pro, 24 GB RAM, 166 GB free disk, Python 3.12, `uv` available. PyTorch MPS runs the frozen experts fine.
- Compute escalation (Colab/cloud GPU) decided at **Phase 2 entry** from measured caching throughput (threshold: if effective throughput < ~10 img/s for the feature cache, move extraction to GPU; local stays dev + demo).
- Two agents build in parallel (Claude Code + Codex); coordination system to be set up by Mehul (~1h from plan time). Interim assumption: shared git repo + `STATUS.md` handoffs. **Division of labor once live:** Agent A = pipeline/experts/training/eval (long compute jobs); Agent B = Gradio/app, repo hygiene, docs, video assets. Both read this file + docs 00–08 as ground truth.

---

## Phase 0 — Skeleton & First Signal (tonight, ~4–6h)

**Goal: an image goes in, a verdict comes out, end to end.**

| # | Task | Notes |
|---|---|---|
| 0.1 | Repo scaffold | `git init`, `uv` project; `src/{pipeline,experts,router,eval,app}`, `scripts/`, `configs/`, `tests/`, `results/`. Public GitHub from day 1. |
| 0.2 | Canonical decode module | PIL decode, EXIF orientation, RGB convert, record original mode/size/format, SHA-256 + perceptual hash. Never silently recompress (doc 03 step 1). |
| 0.3 | Official transform pipeline | All 20 grid conditions (clean + 19 from `docs/05-evaluation-and-ablations.md` stress matrix) as deterministic seeded functions. Written implementation manifest: JPEG encoder + subsampling, resize interpolation (down then up), blur kernel truncation, noise in [0,1] with clipping, six color-jitter endpoints, 80% center-crop geometry. Parameterized so webinar answers can adjust without rewrites. |
| 0.4 | Golden tests | Fixed tiny input set → expected transformed hashes/pixel summaries. CI-style script. |
| 0.5 | Community Forensics adapter | Download HF checkpoint; exact official preprocessing; map class order → P(fake); ExpertOutput contract from doc 03 (expert_id, raw_logit, prob, embedding?, inference_ms, warnings); deterministic; MPS. |
| 0.6 | Sanity check | ~20 known real + ~20 known fake → scores separate. |
| 0.7 | Smoke dataset | ~200 real (COCO **train** subset — never val2017) + ~200 fake (GenImage or SID-Set slice), with manifest + hashes. |
| 0.8 | Gradio v0 | Upload → decode → CF score → verdict card. Ugly is fine. |

**Exit test:** `scripts/predict.py image.jpg` prints score; Gradio runs locally; golden tests pass.

## Phase 1 — Baseline Robustness + Demo-Ready (Day 1, Wed 27 Aug)

**Goal: measured clean-vs-transformed baseline + a demo you could film today.**

| # | Task | Notes |
|---|---|---|
| 1.1 | Eval harness | Per class × transform family × severity: balanced acc, fake recall, FPR, clean→transformed drop, worst-transform, fake-to-real / real-to-fake flip rates, AUROC/AP; source-level bootstrap CIs. Single frozen protocol → JSON + auto-markdown tables (templates in doc 05). |
| 1.2 | LOTA adapter | Same ExpertOutput contract; preserve original bytes/decode path (doc 08 risk 6). **Kill cap: ~4h** — if integration stalls, park and continue single-expert. |
| 1.3 | Mini shootout | CF-384 vs LOTA on smoke set × full grid. OmniAID gets one bounded ≤3h attempt only if schedule is green; otherwise future-work citation. Pick primary per doc 03 selection rule (worst-family fake recall, FPR, flips, calibration, latency). |
| 1.4 | Quality descriptors | Variance-of-Laplacian blur proxy, JPEG blockiness proxy, noise estimate, resolution/aspect/contrast/luminance stats. |
| 1.5 | Gradio v1 | Verdict + probability + per-expert evidence rows + **"Stress-test this image" button**: runs the official grid live, plots score-vs-severity stability. This is the demo money-shot. |
| 1.6 | Repo hygiene | README stub, license inventory (checkpoints + datasets), push. |
| 1.7 | **28 Aug 5pm webinar** | Ask doc-08 protocol questions (param limit scope, JPEG encoder, noise range, crop semantics = 80% of side vs area, chained transforms, metric, abstention scoring). Adjust transform manifest params if answered. |

**Exit test:** full-grid baseline table for the chosen primary on the smoke set; Gradio stress panel works; repo is public.

## ⚠️ POST-LOTA REVISION — Phases 2R–5R supersede Phases 2–5 (PROPOSED 2026-08-27)

**Proposed by Claude in `A-023`; NOT ADOPTED until Codex ACKs and `coordination/DECISIONS.md`
carries both names.** Phases 2–5 below are preserved unedited as the record of what was
planned; where 2R–5R disagree, 2R–5R win once ACKed.

Trigger: Mehul's update pack `docs/techjam_track5_update/` (docs 09–12) after the LOTA
checkpoint proved Baidu-gated. Evidence packet: `handoffs/2026-08-27_post-lota-replan.md`.

### The three measurements this revision rests on

1. **DegradePrint's response signature fails its own kill criterion.** The pack's cheap test
   (doc 10 §11, bar ~+2 pt) was runnable at zero compute on the existing pilot cache.
   Dev worst-family fake recall over 3 seeds at a fixed 5% clean FPR:
   primary alone **0.211** → +quality **0.604** → +quality+response **0.612** → response-without-quality **0.254**.
   Response-over-quality is **+0.8 pt with unstable sign**. Reproduce:
   `.venv/bin/python scripts/diagnostics/degradeprint_probe.py [seed]`.
   Measures the logit-space half only; embedding drift is untested and costs a cache rebuild.
2. **Quality descriptors (task 1.4, already shipped) are the largest measured gain in the
   project** — +39.3 pt on the worst family, at a *lower* clean FPR, for zero new compute.
3. **No heavy expert fits the training cache.** 15k sources × 20 conditions = 300,000 rows at a
   measured 7.83 rows/s = 10.6 h against the 12 h cap. PGC ≈ 311M and GAPL ≈ 305M params
   (~1.2 GB each) are ~14× CF-384; base-view-only pushes the run over cap, base+probes far past it.

### The architecture change

> **The router head becomes a CORRECTION head over the primary logit conditioned on quality +
> reliability features — not a convex FUSION head over experts.**

`results/router-pilot/training.json` shows all four rungs identical and
`router_earns_its_complexity: false`. The recorded reason (one expert ⇒ softmax weight 1.0) is
true but incomplete: the router was degenerate **because fusion was its only lever**, not because
its features are weak. Its 43 features already carry the 39-point signal in (2) with no way to
apply it. Fusion re-enters only if a second always-on expert ever earns its slot.
Consequence: `fusion_comparison_degenerate` becomes obsolete rather than merely inaccurate
(resolves B-018 item 3 by deleting the claim, not the bias head).

### Model slots after verification

| slot | occupant | evidence |
|---|---|---|
| primary | **CF-384** (challengers measured, not assumed) | 21.8M, MIT, pinned-able |
| complementary evidence | **quality descriptors + self-probes** (no second checkpoint) | +39.3 pt measured |
| primary challenger | **PGC** (Apache-2.0, HF, 311M) · **GAPL** (MIT *on the model card only*, HF, 305M) | shootout on the existing 8,000-row grid, ~20–40 min each |
| selective rescue | shootout winner, 6 h hard cap | scored by P(rescue correct \| primary wrong) |
| killed | LOTA reproduction · DegradePrint response branch · PGC-as-always-on-expert | see packet §4 |

### Phase 2R — Unblock, freeze, cache (Thu 27 Aug)

| # | Task | Owner | Notes |
|---|---|---|---|
| 2R.1 | **Clear B-016 (E1–E5) and B-018; review B-017/B-019** | both | **No 2R work starts while blocks are open.** The cache run must not launch on blocked code. |
| 2R.2 | Freeze feature + probe set; router head fusion → correction; embeddings **out** | Claude | The 10.6 h run is affordable once. Codex's cache requests due **~17:00 today**. |
| 2R.3 | Cache-key bump **once**, golden + denylist re-verified fail-closed | Claude | Two bumps = two 10.6 h runs = no submission. |
| 2R.4 | **Full 15k feature-cache run, ~18:00 Thu → ~05:00 Fri** | Claude | **Hard critical path.** Not started Thursday evening ⇒ no trained router. |

**Exit test:** manifest completes with `denylist_protected: true`, cache key matches the frozen
key object, zero sealed-reference hits, row count = sources × 20.

### Phase 3R — Correction head + shootout (Fri 28 Aug, parallel)

| # | Task | Owner | Notes |
|---|---|---|---|
| 3R.1 | Train correction-head ladder (static → logistic → MLP → +worst-group) on the frozen objective | Claude | Every rung an ablation row; negative results reported, not buried. |
| 3R.2 | Calibration + threshold on held-out dev; one threshold across all conditions | Claude | Existing `calibration.py`; no per-condition tuning. |
| 3R.3 | Ablation arms A/B/C/D from the diagnostic promoted to first-class rows | Claude | The DegradePrint negative result ships as a finding. |
| 3R.4 | **Primary shootout: CF-384 vs PGC vs GAPL** on the existing 8,000-row grid | **Codex** | **Licence gate first** — GAPL's card-only MIT needs a decision. 3 h cap each. |

**Exit test:** correction head beats static baseline on worst-family fake recall with clean BAcc
regression ≤1 pt and FPR increase ≤1 pt — or the strongest simpler variant ships, stated honestly.

### Phase 4R — Selective rescue, freeze, evaluation (Sat 29 – Sun 30 Aug)

| # | Task | Owner | Notes |
|---|---|---|---|
| 4R.1 | Selective rescue with the shootout winner | Codex | **6 h hard cap**, then cut and report the negative ablation (doc 11 §13). |
| 4R.2 | Rescue metrics: invocation / correction / harm rate, p50-p95 latency | Codex | Most inputs invoking rescue ⇒ the adaptive-compute story failed; say so. |
| 4R.3 | **Freeze.** Architecture, threshold, calibration. No further tuning. | both | Joint gate. |
| 4R.4 | Full ablation matrix + **one** sealed WildFake run | Claude | Phase-4 only; denylist evidence attached. |
| 4R.5 | Robustness Evaluation Summary + Error Analysis Note (**required deliverables**) | Claude drafts, Codex reviews | Include the JPEG-30 limitation and the DegradePrint negative. |

### Phase 5R — Ship (Sun 30 evening → Tue 1 Sept 09:00)

Unchanged from Phase 5 below, plus two items that are now blocking:
**repo must go public** (needs Mehul's explicit MIT approval *and* force-push approval — remote
`main` still carries ~829 MB of raw SID-Set blobs), and the README must carry the
reproducibility-as-a-design-constraint argument: three unobtainable artifacts (LOTA Baidu-gated,
NPR unlicensed, GAPL licence card-only) against one clean counter-example (PGC).

### Fallback ladder (revised)

| time dies during… | what gets submitted |
|---|---|
| 2R (cache run fails) | CF-384 + correction head trained on the **24,000-row pilot** — already +39 pt on the worst family |
| 3R | Correction head + calibration + full robustness table + stress demo |
| 4R | Everything minus rescue, rescue reported as a negative ablation |
| 5R | Everything; polish level varies |

---

## Phase 2 — Router Corpus + Trained Fusion (Days 2–3, Thu 28 – Fri 29 Aug)

**Goal: our trained layer beats the best single detector on robustness.**

| # | Task | Notes |
|---|---|---|
| 2.1 | Compute decision | Measure Phase-1 caching throughput → local vs Colab call. |
| 2.2 | Router corpus | 20–40k balanced images: GenImage subset + filtered SID-Set (real + fully-synthetic only; exclude tampered). Grouped splits by generator/source/lineage (doc 04). Same source's clean+transformed views stay in one split. |
| 2.3 | Contamination controls | SHA-256 + perceptual-hash denylist built from sealed WildFake subset; reject matches; versioned manifest. Denylist check runs automatically before every training job. |
| 2.4 | Feature cache | One row per (source × view): expert logits/probs/entropies, |pA−pL| + agreement, 3 self-probe stability features (mean/std/range/max-delta/flip), quality descriptors, runtimes, checkpoint hashes + preprocessing version. Sampling: 20% clean / 80% one transform, families uniform (doc 04). |
| 2.5 | Fusion ladder (each an ablation row) | static average → regularized logistic stacker → small MLP router (fusion-weights head + reliability head) → + smooth worst-group loss (log-sum-exp over class×family groups). **Keep the simplest model that wins** (doc 08 router kill criteria). |
| 2.6 | Calibration + abstention | Temperature+bias on held-out dev; reliability head → REAL/AI/UNCERTAIN policy; one threshold across all conditions (no per-transform tuning); risk-coverage table. |
| 2.7 | Gradio v2 | Evidence panel shows fusion weights, probe stability, reliability grade (HIGH/MED/LOW), abstention behavior. |

**Exit test (acceptance gates, doc 05):** on held-out sources, cascade ≥ best single expert on worst-transform fake recall, clean balanced-acc regression ≤1pt, FPR increase ≤1pt. If gates fail → ship the strongest simpler variant honestly.

## Phase 3 — Selective Rescue + Complementarity Story (Day 4, Sat 30 Aug)

**Goal: adaptive-compute rescue + the analysis that makes judges believe the design.**

| # | Task | Notes |
|---|---|---|
| 3.1 | WaRPAD adapter | **Hard 6h integration cap** (doc 08); RIGID is the drop-in backup — if substituted, say so and rerun ablations. Run on dev + stratified hard/easy train subset only (needs negative examples). |
| 3.2 | Rescue trigger | Learned rescue probability from router head, validated against heuristic OR-rules baseline. Metrics: rescue rate (target well <40%), correction rate, harm rate, p50/p95 latency common vs rescued. |
| 3.3 | Complementarity analysis | P(B correct \| A wrong) by class×family×severity; joint-failure; error correlation; oracle-ensemble upper bound. This becomes the core insight chart for Devpost/video. |
| 3.4 | Gradio v3 | Escalation visible: "behavioral rescue invoked — evidence unstable under probes". |

**Exit test:** rescue improves worst-case fake recall or selective risk by ≥2pts at bounded rescue rate — else **cut it and report the negative ablation** (still a strength).

## Phase 4 — Freeze, Full Evaluation & Error Analysis (Day 5, Sun 31 Aug)

**Goal: frozen numbers, sealed-set run, both required deliverable artifacts.**

| # | Task | Notes |
|---|---|---|
| 4.1 | Freeze | Architecture, thresholds, calibration frozen. No further tuning of anything. |
| 4.2 | Full ablation matrix | Single experts / static avg / stacker / router±probes / ±worst-group / ±rescue on internal held-out test (doc 05 templates). |
| 4.3 | Sealed reference run | **One** run on official WildFake subset; document that it never influenced fitting (denylist evidence). Report as reference benchmark, not final score. |
| 4.4 | Robustness Evaluation Summary (required) | Compact clean-vs-transformed table + one degradation chart. |
| 4.5 | Error Analysis Note (required) | Representative FPs (denoised photos, CGI, screenshots), FNs (JPEG 30, modern generators), router errors, per doc-05 taxonomy. Include ≥1 honest limitation case (JPEG 30). |
| 4.6 | Ops evidence | Latency/memory profile, rescue-rate, per-component + aggregate parameter counts (<2B statement). |
| 4.7 | Video script + insurance recording | Write the 3-min script; screen-record one full Gradio pass as backup footage. |

**Exit test:** `scripts/run_eval.py --config configs/frozen.yaml` reproduces every reported table from the feature cache; both required notes drafted.

## Phase 5 — Ship (Sun 31 Aug evening → Mon 1 Sept morning)

**Goal: submitted by ~9:00am Sept 1, three hours of buffer.**

| # | Task | Notes |
|---|---|---|
| 5.1 | Demo polish | Gradio styling pass. Thin polished front-end **only** if literally everything else is done (explicit stretch). |
| 5.2 | README final | Quickstart, architecture diagram, results tables, limitations + what we'd improve with more time, solo-contribution note, full license inventory. |
| 5.3 | 3-min video | Problem (15s) → live demo incl. stress-test panel + one abstention case (90s) → robustness chart + honest limitation (45s) → architecture + closing (30s). No third-party trademarks/copyrighted content. Public YouTube. |
| 5.4 | Devpost | Approach, tools (VSCode, Claude Code, Codex), models/APIs, libraries (PyTorch, HF, scikit-learn, pandas, Gradio), datasets/assets; link video + repo. Run the doc-00 deliverable acceptance checklist item by item. |
| 5.5 | **Submit by ~9am** | Not 11:59am. |

---

## Fallback ladder

| Time dies during… | What gets submitted |
|---|---|
| Phase 2 | CF-384 + calibrated threshold + full robustness table + Gradio stress demo |
| Phase 3 | Two-expert trained router + reliability/abstention (already a strong, original entry) |
| Phase 4 | Full cascade minus rescue, or rescue reported as negative ablation |
| Phase 5 | Everything; polish level varies |

## Verification (continuous)

- Golden tests on the transform pipeline (deterministic hashes) — run on every change to decode/transforms; cache-version bump if they change.
- End-to-end `scripts/predict.py` + Gradio smoke on fresh images (both classes) at every phase exit.
- One-command reproduction of all reported numbers from the frozen config.
- Denylist check precedes every training job.
- Day-5 video dry-run as insurance.

## Open items

- [ ] Compute choice (local vs Colab) — decide at Phase 2 entry from measured throughput.
- [ ] Webinar answers (28 Aug) → possible transform-manifest parameter updates.
- [ ] Dual-agent coordination system — Mehul sets up (~1h); until then this file + docs 00–08 + `STATUS.md` are the shared ground truth.
