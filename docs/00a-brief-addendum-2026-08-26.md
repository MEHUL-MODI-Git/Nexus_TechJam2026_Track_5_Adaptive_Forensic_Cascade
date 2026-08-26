# 00a — Brief Addendum (verified 26 Aug 2026, evening)

> **Status: OFFICIAL — supplements `00-official-brief.md`, does not replace it.**
> Source: updated Track 5 brief page captured in `docs/evidence/2026-08-26_track5-deliverables.png` (repo-safe copy of the Brief screenshot whose original filename contains a narrow no-break space U+202F; sha256 289af3369ab5edc99ed45b89ef7e06a630428caa40bd37070653678028f6ffa1) (section 5.5 Expected Deliverables). Flagged by Codex (MSG-004), visually verified by Claude against the screenshot. Doc 00 is preserved unmodified per standing rules.

The updated §5.5 "Public Code/GitHub Repository" deliverable adds requirements beyond the doc-00 extraction:

1. **Well-structured, commented code covering all components of the solution.**
2. **REQUIRED batch-inference script** — verbatim requirement:
   > A script that takes an image directory as input and outputs a confidence score for each image, indicating the likelihood that it is AIGC-generated. The output should be a JSON file containing `image_path` and `pred` for each image.
   - Implementation: `scripts/infer_dir.py <input_dir> --output preds.json`, emitting a JSON file of `{"image_path": ..., "pred": <float in [0,1], higher = more likely AI-generated>}` per image. `pred` = our final calibrated p_fake. Any abstention/reliability fields go in EXTRA keys; `image_path` and `pred` must always be present for every image (judges may run this on hidden data — never crash on a bad file; emit `pred` with a warning field instead).
3. **README must include:** project overview; setup and installation instructions; steps to reproduce results; limitations/reflection; team contributions (already in doc 00 — first three items are new).

## Planning impact
- `scripts/infer_dir.py` is promoted to a REQUIRED deliverable: built in Phase 1 (thin wrapper over the predict path), kept working from then on, and smoke-tested at every phase gate. This is likely the organizers' scoring entry point — treat its robustness (weird files, huge dirs, deterministic output) as first-class.
- README checklist in Phase 5 gains: overview, setup/install, reproduce-steps sections.
- "Well-commented code" noted for both agents' Definition of Done.

Recorded as a joint decision in `coordination/DECISIONS.md`.
