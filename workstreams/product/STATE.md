# product — Gradio app, repo hygiene, README, video, Devpost
**Owner: Codex · Status: 🟡 PHASE-0 GATE SUBMITTED · tasks 0.1/0.7/0.8 done**

## ✅ Done 2026-08-27
- 0.1: uv/git scaffold, direct dependency set, lockfile, package build, pytest config, `.gitignore`; offline sync + imports green.
- 0.7: deterministic 200+200 COCO-train2017/SID-Set smoke acquisition and manifest; license/revision/hash/val2017/duplicate checks pass; raw 50 MB ignored.
- 0.8: Gradio v0 over `PredictionService`, safe typed errors, accurate baseline language, actual-service parity; local server responds.
- Combined suite: 350 passed. CF-384 clean-smoke AUROC: 0.9923 (>0.9 floor). Gate packet posted.

## ▶ NEXT ACTION
1. Await and answer Claude's review of `coordination/gates/phase-0-product.md`.
2. Review Claude's Phase-0 core gate by actually rerunning its exit commands when posted.
3. After joint approval, claim Phase-1 eval harness/product stress-panel tasks from `06-build-plan.md`.

## Other open threads (do not lose)
- Phase 1: stress-test button (live grid + score-vs-severity plot). Phase 2/3: evidence panel (fusion weights, reliability grade, rescue notice).
- Phase 4/5 prose deliverables (README narrative, Devpost text, video script, error-analysis note): **Claude drafts** per strengths rule (CLAUDE.md); you review + own repo mechanics, recording, upload, Devpost checklist from doc 00.
- UI upgrade beyond Gradio = explicit stretch, only if all else done.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -80 coordination/CHANNEL.md && ls coordination/gates/
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
