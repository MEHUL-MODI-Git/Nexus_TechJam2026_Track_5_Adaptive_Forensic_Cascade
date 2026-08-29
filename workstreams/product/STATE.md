# product — Gradio app, repo hygiene, README, video, Devpost
**Owner: Codex · Status: 🔴 RELEASE BLOCKED BY B-029 + OWNER ACTIONS**

## Accepted
- Task 1.5 stress panel remains accepted (39 focused tests + prior peer gate).
- Router/demo wiring works in the current local workspace.

## Release blockers
1. Configured `router_reliability.pt` is ignored/untracked; clean checkout cannot serve abstention.
2. Degradation reporter `classifier.pt` is ignored/untracked; clean checkout silently omits it.
3. Parameter-cap math is wrong by 1000× and reporter parameters are omitted.
4. README/Devpost contradict actual shipped state and overstate peer-gate completion.
5. Eval/training B-029 repairs and Codex re-review remain open.
6. Remote/public-history, MIT approval and force-push still require Mehul's explicit decisions.
7. Repository-wide Ruff currently reports 62 findings.

## NEXT ACTION
Wait for Claude's batched R1–R8 repair; re-review from a clean-checkout artifact perspective.

## Literal next command
```sh
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -n 120 coordination/CHANNEL.md
```

## Hard constraints
- No public/force-push action without Mehul approval and verified target.
- Do not present incorrect, untracked, unreviewed or non-reproducible claims as shipped.
- Preserve the completed sealed predictions; never rerun them.
