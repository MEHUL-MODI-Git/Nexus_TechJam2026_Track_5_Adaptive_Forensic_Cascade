# Webinar question plan — Thu 28 Aug, 5:00–5:45pm (task 1.7, joint)

Q&A time is limited, so questions are ranked by **how much our build changes
depending on the answer**, not by curiosity. Each carries the action we take on
each possible answer, so an answer can be applied the same evening.

The full unranked list of 13 lives in `docs/08-risks-kill-criteria-open-questions.md`.

---

## Tier 1 — ask these first; each one can invalidate measured work

### Q1. Is Gaussian-noise `sigma` measured on a [0,1] pixel scale or 0–255?
**Why it is first:** we assumed [0,1]. If the organizers mean 0–255, our noise
conditions are **255× too weak** and every noise result we have is meaningless.
Noise is already our worst family (fake recall 0.165 pooled, 0.015 at σ=0.10),
so this single answer decides whether that finding is real or an artifact of a
unit assumption.
**If [0,1]:** no change; our conditions stand.
**If 0–255:** bump `PIPELINE_VERSION`, regenerate goldens and the cache, rerun
the grid (167 s), and re-examine every noise conclusion.

### Q2. Are abstentions permitted, and how are they scored?
**Why:** our original contribution is a reliability/abstention layer. If
abstention is scored as an error, the layer becomes an internal diagnostic and
a demo feature rather than a scoring strategy, and we should not optimize
coverage against the hidden metric.
**If allowed and scored selectively:** abstention stays a first-class output.
**If not allowed / scored as wrong:** we keep forced binary output as the
headline path and present reliability as explainability (still in scope — the
brief lists explainability explicitly).

### Q3. What is the hidden judging metric — accuracy, balanced accuracy, AUROC/AP, or something else?
**Why:** it determines our frozen threshold objective. A ranking metric (AUROC)
makes threshold choice almost irrelevant; an accuracy-style metric makes it
decisive. On our data that gap is worth roughly 30 points of fake recall.
**If ranking-based:** de-emphasize threshold selection, emphasize score quality.
**If accuracy-based:** threshold selection is the highest-leverage work we have.

### Q4. Does "crop 80%" mean 80% of each side, or 80% of the area?
**Why:** we assumed 80% per side (= 64% area), which is the more severe reading.
**If area:** the condition weakens; bump the pipeline version, regenerate
goldens, rerun. Cheap to fix, but only if we know.

---

## Tier 2 — ask if time remains

### Q5. Are transformations applied singly, or chained?
Our grid is single-transform, matching the published table. Chaining would
expand the evaluation space substantially and change what "worst condition"
means. We keep an unofficial chained suite in a separate namespace either way.

### Q6. Which JPEG encoder and chroma subsampling will be used?
We use PIL, quality as listed, 4:2:0, no optimize, no progressive, and we state
this in our manifest. Different encoder settings shift absolute numbers but not
our conclusions; we are parameterized to match on request.

### Q7. Does the reference subset ship as exact files whose hashes we can deny-list?
We already hash-deny-list it and abort any fitting job on a single hit. A
canonical hash list from the organizers would let us prove non-contamination
rather than assert it.

### Q8. Is `<2B parameters` per component, per loaded model, or total pipeline?
Low stakes for us — our full pipeline is ~21.8M — but we would like to document
the inventory against the correct definition.

---

## Deliberately not asking
- Resize interpolation (Q4 in doc 08): the brief's "downscale then upscale"
  wording is unambiguous enough, and we state bilinear+antialias explicitly.
- Colour-jitter composition: we implement the six single-property endpoints and
  say so; a joint variant would be an additive suite, not a correction.
- Commercial API detectors: we are fully local and reproducible regardless.

## After the webinar
1. Record answers in `docs/09-webinar-answers-2026-08-28.md` (verbatim where possible).
2. Any answer contradicting a stated assumption ⇒ CHANNEL message + `DECISIONS.md`
   entry + `PIPELINE_VERSION`/golden/cache bump **before** any retained measurement.
3. Re-run the 167-second grid; it is deliberately cheap so a protocol correction
   is not a schedule event.
