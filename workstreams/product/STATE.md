# product — Gradio app, repo hygiene, README, video, Devpost
**Owner: Codex · Status: 🟢 PHASE 1 · task 1.6 claimed**

## ✅ Done 2026-08-27
- 0.1: uv/git scaffold, direct dependency set, lockfile, package build, pytest config, `.gitignore`; offline sync + imports green.
- 0.7: deterministic 200+200 COCO-train2017/SID-Set smoke acquisition and manifest; license/revision/hash/val2017/duplicate checks pass; raw 50 MB ignored.
- 0.8: Gradio v0 over `PredictionService`, safe typed errors, accurate baseline language, actual-service parity; local server responds.
- Claude independently approved the gate and reproduced AUROC 0.9923 on MPS. Codex independently approved core (387 tests).
- Placeholder 0.5 threshold recall is only 0.530 on smoke (diagnostic, never fitted). UI mitigation leads with `BASELINE SIGNAL`/score and demotes the provisional forced verdict; decision recorded.

## ▶ NEXT ACTION
1. Luna performs a read-only repo/license inventory for 1.6; Codex decides policy and reviews any proposed diff.
2. Claim 1.5 only when its UI/behavior spec is written and file ownership is clear.
3. Before public demo, rerun live Gradio upload against Claude's warning-aggregation fix.

## Other open threads (do not lose)
- Phase 1: stress-test button (live grid + score-vs-severity plot). Phase 2/3: evidence panel (fusion weights, reliability grade, rescue notice).
- Phase 4/5 prose deliverables (README narrative, Devpost text, video script, error-analysis note): **Claude drafts** per strengths rule (CLAUDE.md); you review + own repo mechanics, recording, upload, Devpost checklist from doc 00.
- UI upgrade beyond Gradio = explicit stretch, only if all else done.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -60 coordination/CHANNEL.md
```

## Hard constraints
- Public GitHub deferred by Mehul; local git only. No dataset/checkpoint redistribution if license forbids — link instead.
- Video/demo assets licensed, no third-party trademarks.
- Never present illustrative numbers as measured (doc 05 warning).

## Read next
| Task | Read |
|---|---|
| Deliverables checklist | `docs/00-official-brief.md` §5.5 |
| Demo/UI spec | `docs/03-recommended-architecture.md` example outputs + `06-build-plan.md` Gradio v0–v3 |
| Smoke data rules | `docs/04-training-and-data.md` dataset roles + contamination controls |
| Current pre-build proposal | `handoffs/2026-08-26_codex-prebuild-plan.md` |
