# LOTA weights replan — bounded candidate proposal

## Trigger and evidence

Mehul supplied the root update `techjam_track5_lota_update.md` and both files in
`LOTA weights/`. This supersedes only the prior availability assumption; it does
not authorize an architecture change or cache admission.

The official repository main currently resolves to
`de2f70a5acc195cbb3cfedb1909d75343b1bd023`. Its README links both weight files,
but does not state a separate weight license. The repository code is MIT; the
checkpoint-use/redistribution license remains ambiguous. Public pretrained use
is allowed only if the applicable license permits it. Ask the author for an
explicit checkpoint-use/redistribution license before final adoption. Never
commit the weights.

The `.gitignore` was narrowly amended by the heavy owner to ignore `*.pth`,
`*.pt`, and `*.ckpt`; the weight files are unchanged and untracked.

## Safe checkpoint audit

Both files loaded successfully with `.venv/bin/python` and exactly
`torch.load(path, map_location="cpu", weights_only=True)`:

| | `sdv4_scaling_patch32.pth` | `sdv5_scaling_patch32.pth` |
|---|---:|---:|
| Size | 94,361,483 bytes | 94,361,483 bytes |
| SHA-256 | `1a9cb5cc53b9a04588900d290eafadda559bdebd516a9c2049a2369b1af46197` | `66892fc25915043dc784de1182381b9d543e5bea05c54b3e4367db4027f7c5f9` |
| Top-level | `OrderedDict`, 320 keys | `OrderedDict`, 320 keys |
| State-dict form | direct | direct |
| Tensors / elements | 320 / 23,563,254 | 320 / 23,563,254 |
| Dtypes | `float32`, `int64` | `float32`, `int64` |
| Tensor bytes | 94,253,228 | 94,253,228 |
| NaN / Inf | 0 / 0 | 0 / 0 |
| Non-tensor entries | none | none |

Representative first keys are `disc.conv1.weight`, `disc.bn1.weight`,
`disc.bn1.bias`, `disc.bn1.running_mean`, `disc.bn1.running_var`; final keys
are `disc.layer4.2.bn3.running_mean`, `disc.layer4.2.bn3.running_var`,
`disc.layer4.2.bn3.num_batches_tracked`, `disc.fc.weight`, `disc.fc.bias`.
Key sets, shapes, and dtypes are equal. Float tensors have 23,563,201
elements, of which 23,476,445 differ; max absolute difference is
`353.2534713745117`, mean absolute difference `0.03177842410522104`.

Each file is a 322-member ZIP checkpoint. Member names match; `zipfile` CRC
validation passed for both. The first member is `Network_best/data.pkl`
(CRC `03571caf`) and the last is `Network_best/version` (CRC `55679ed1`).
Only 2/322 member CRCs match across files, consistent with distinct weights.

## Heavy proposal: bounded LOTA preflight

LOTA gets the first bounded candidate preflight, ahead of PGC, while CF-384
stays primary until evidence supports a change. Claude owns the heavy
adapter/preprocessing specification and heavy verification; a lighter model
implements the agreed routine.

The canonical adapter must:

1. negate the official real-positive logit so `raw_logit` is fake-positive;
2. compute `p_fake = sigmoid(raw_logit)` exactly once;
3. reproduce low-3-bit scaling, 64 random 32x32 crops with max roughness,
   resize to 256, `ToTensor`, and ImageNet normalization;
4. resolve the official stochastic `RandomCrop` with an explicit deterministic
   per-image policy and parity test, never an unrecorded behavior change.

Verification must include strict `weights_only` loading, hashes and state-key
checks, no ImageNet predownload, CPU/MPS parity, polarity, determinism,
latency, and memory. Verify both checkpoints on a bounded balanced sanity set,
then run the exact 20-condition diagnostic grid and CF complementarity through
the repaired eval harness. Checkpoint triage may use diagnostic evidence, but
adoption/selection must use protected fitting/dev data, never the internal test
or sealed reference subset.

If LOTA passes, run the mandatory simple baselines: LOTA alone, probability
mean, logit mean, fixed weighted average, and logistic stacking before any
learned router comparison.

The proposed admission gate is: load/schema and preprocessing parity; clean
sanity; full diagnostic grid; protected complementarity of at least 15% of
primary errors corrected in an important family or at least a 2-point
constrained robustness gain; acceptable FPR and latency; and clear licensing.

Router B-018 and data gates still block the cache. LOTA is not admitted to the
15k cache until throughput and protected mini-pilot admission are measured.
DegradePrint logit response remains parked; embeddings remain deferred; PGC
is optional after LOTA; GAPL remains license-blocked.

This packet is a proposal, not architecture or cache authorization.

## First measured preflight — sanity gate failed; upstream parity required

Claude's in-flight diagnostic loaded both checkpoints into the official pinned module with zero
missing or unexpected keys and ran each on the same balanced 200-image SID-Set smoke sample. The
results are diagnostic only:

| checkpoint | AUROC as canonical `P(fake)` | mean `P(fake)`, real | mean `P(fake)`, fake | max repeat spread |
|---|---:|---:|---:|---:|
| SD v1.5 | 0.5166 | 0.0070516 | 0.0000305 | 0.3090741 |
| SD v1.4 | 0.4798 | 0.0044387 | 0.00000000046 | 0.0043126 |

Both are effectively chance and overwhelmingly predict real; official random patch sampling is
also non-deterministic. This fails the update pack's clean-sanity prerequisite, so a full
20-condition grid is not yet justified. The next bounded test is upstream-style parity on a small
SD v1.4/v1.5 GenImage validation sample using the official seed/preprocessing. If upstream parity
fails, repair the integration/checkpoint path. If upstream parity passes but the TechJam smoke
result stays near chance, LOTA is a domain-mismatch negative and does not enter the common path or
15k cache. Before treating the diagnostic as gate evidence, use strict state loading, tie-aware
shared AUROC, warmup-aware latency percentiles, and complete checkpoint/repo/data/device/seed
provenance.

## Joint-discussion update after Claude A-026

Claude found the source corpus has a class-perfect codec shortcut: 7,496 JPEG + 4 MPO reals versus
7,500 PNG fakes under misleading `.jpg` paths. A clean-row logistic model using only eight decoded-
pixel quality descriptors reaches AUROC 0.9867; blockiness alone reaches 0.8962. Therefore the prior
quality-correction pilot is confounded and cannot support a forensic claim.

Codex B-027 ACKs stop-the-line and conditionally ACKs a label-blind JPEG-q95 canonicalization
experiment. It is accepted only if three fixed source-held-out audits put worst-seed quality-only and
blockiness-only AUROC and train-threshold accuracy at or below 0.60; otherwise re-source/try another
jointly specified label-blind policy or fall back to CF-only. No sealed-reference statistic may
choose preprocessing. The eval metric path itself was independently checked and does not consume
container, extension, encoded size or filename-derived features.

LOTA remains outside the 15k cache and becomes a bounded, format-controlled challenger ahead of
PGC. Full-grid work waits on upstream GenImage parity and controlled format sensitivity. External
checkpoint licensing remains unspecified by the official README/LICENSE combination, and direct
combined-path timing is required: adding 16.9 ms to the measured 127.7 ms/row gives a naive ~12.0 h,
not 20 h+, but is still too close to the cap without evidence.

## Final Codex position and relay

In B-028 Codex ACKed A-027 with controls: add `quality_only`, compare every claim against both
CF-only and quality-only plus the simple ladder, and retain q95 only as blockiness mitigation. LOTA
stays outside the 15k cache/common path and is a bounded robustness negative/challenger; final use of
the external checkpoints remains licence-gated. Mehul then invoked PROTOCOL §6 because Codex is near
its limit. Claude may continue Codex-owned eval/product work as `[relay]`, review-first on Codex's
return, without weakening router, sealed-data, release or public-history gates.
