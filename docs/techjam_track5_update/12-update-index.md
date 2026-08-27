# Track 5 Post-LOTA Update Pack

This update pack should be read **after** the original Track 5 documentation.

It records the complete strategy update after the LOTA pretrained checkpoint became inaccessible through Baidu Netdisk.

## Files

### `09-lota-blocker-and-model-replacements.md`

Read first.

Contains:

- the LOTA checkpoint-access problem;
- why Baidu should not block the project;
- option to reproduce LOTA ourselves;
- why LOTA becomes optional;
- PGC as an accessible complementary/local candidate;
- GAPL as a primary-detector challenger;
- continuing role of Community Forensics;
- continuing role of WaRPAD;
- revised safe cascade after the blocker.

### `10-degradeprint-alternative-solution.md`

Contains the complete new alternative architecture:

**DegradePrint — Transformation-Response Forensics**

Includes:

- hypothesis;
- relationship to RIGID / WaRPAD / robustness-asymmetry work;
- stable-evidence branch;
- response-signature branch;
- outer corruption + inner diagnostic probes;
- frozen backbone choice;
- training strategy;
- cheap logistic-regression validation experiment;
- kill criteria;
- optional WaRPAD rescue;
- judging-rubric fit;
- risks;
- relationship to the existing cascade.

### `11-revised-strategy-and-integration-plan.md`

Read last.

Contains the current recommendation:

- Adaptive Forensic Cascade remains the safe primary path;
- DegradePrint is the high-upside parallel experiment;
- Community vs GAPL primary shootout;
- PGC as LOTA replacement candidate;
- WaRPAD as selective rescue;
- LOTA reproduction as optional;
- implementation order;
- decision gates;
- success criteria;
- final hybrid if DegradePrint works;
- exact instructions for the existing planning/build agent.

## Current decision in one paragraph

Do not restart the Track 5 project because LOTA weights are inaccessible. Keep the working Community Forensics baseline and exact TechJam evaluation harness. Benchmark GAPL as a possible stronger primary and PGC as an accessible complementary local expert. Preserve WaRPAD as selective behavioral rescue. In parallel, test a new architecture idea called **DegradePrint**, which uses a frozen primary detector plus mild transformed views to learn a transformation-response signature from changes in logits and embeddings. The safest submission path is still the revised Adaptive Forensic Cascade; DegradePrint should first be tested cheaply with logistic regression. If its response features materially improve held-out worst-transform fake recall or reduce fake-to-real flips, integrate them into the cascade router and make that response signature the central innovation. If not, kill DegradePrint and keep the proven cascade.

## Current architecture hierarchy

Safe main path:

```text
Primary detector
Community OR GAPL
      |
      +---- PGC complementary local evidence
      |
      v
Reliability router
      |
  +---+---+
  |       |
return  WaRPAD rescue
```

Parallel experiment:

```text
DEGRADEPRINT

Primary detector
      |
original + mild probes
      |
logit/embedding response signature
      |
tiny classifier
```

Potential final hybrid:

```text
Primary global evidence
        +
PGC local evidence
        +
DegradePrint response signature
        |
        v
Reliability router
        |
   +----+----+
   |         |
return     WaRPAD
```

## Binding principle

> **No component is kept because the paper is impressive or because it appeared in an earlier architecture diagram. Every component must earn its slot through measured robustness, complementarity, calibration, latency, and ablation evidence.**
