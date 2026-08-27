# Post-LOTA Model Preflight v1

> **Status:** JOINT PLANNING GATE — A-023/A-024/B-020  
> **Purpose:** Reject inaccessible, unlicensed, incompatible or unaffordable candidates before an
> adapter or long benchmark becomes a dependency.

## Required provenance packet

For every candidate, record before integration:

- official paper and repository URLs;
- immutable repository revision;
- official checkpoint host, resolved revision, filenames, byte sizes and SHA-256 hashes;
- separate code, checkpoint and required-backbone licences;
- exact architecture and measured parameter count, plus aggregate loaded parameter count;
- official preprocessing, class order, output polarity, and whether output is a logit/probability;
- dependency/Python/device requirements and whether MPS is supported;
- peak memory and p50/p95 latency on the intended local path;
- projected cost for the proposed role: full cache, common path, or selective rescue.

Missing or conflicting licence terms fail closed. Do not copy code from a repository without an
explicit licence, even when a separately hosted model card declares a checkpoint licence.

## Adapter smoke gate

Claude owns paper-fidelity and any `src/experts/` adapter. The adapter must:

1. satisfy `ExpertOutput` and apply sigmoid exactly once;
2. load a pinned, hashed checkpoint with strict state-dict validation;
3. reproduce official preprocessing and polarity against a small official-code parity sample;
4. return finite scores in `[0,1]` or a typed failure, never a placeholder;
5. measure parameters, peak memory and p50/p95 latency;
6. pass real/fake separation alarm checks without using the sealed reference set.

Time caps: PGC 4 h; GAPL 3 h after licence clearance. Exceeding a cap parks the candidate.

## Evaluation gate

Codex compares successful adapters in the repaired eval harness. The initial smoke-grid run is
diagnostic only and may triage candidates. Adoption requires protected, source-aligned paired
evidence, complete expected coverage, method-specific calibration learned without test leakage, and
clean-cost constraints.

A candidate earns:

- **primary:** clear paired worst-family/flip improvement over CF with clean BAcc/FPR constraints and
  acceptable common-path latency;
- **always-on expert:** meaningful complementarity plus a measured <=12 h fitting-cache plan;
- **selective rescue:** meaningful `P(candidate correct | common path wrong)`, bounded invocation,
  positive correction-minus-harm, and acceptable rescued latency.

Otherwise it is parked and reported only as a bounded negative/feasibility finding.

## Current candidates

| candidate | verified starting fact | present status |
|---|---|---|
| PGC | Apache-2.0 repo and HF card; three ~1.25 GB checkpoints; DINOv2-Large required | first preflight; not adopted |
| GAPL | HF card MIT and ~1.22 GB checkpoint; official GitHub repo reports no licence | code integration blocked |
| LOTA | MIT code; official weights Baidu-account gated | reproduction removed from schedule |
| NPR | downloadable checkpoint; upstream code has no licence; poor bounded smoke result | excluded |
| WaRPAD/RIGID | role described in original plan; current licence/checkpoint/runtime not verified | no work before common-path gate |
