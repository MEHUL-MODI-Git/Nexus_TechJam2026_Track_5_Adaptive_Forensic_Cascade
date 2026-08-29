# product — Gradio app, repo hygiene, README, video, Devpost
**Owner: Codex · Status: 🔴 RELEASE BLOCKED BY B-030 + OWNER ACTIONS**

## Accepted
- Task 1.5 stress panel remains accepted (39 focused tests + prior peer gate).
- Router/demo wiring works and configured small checkpoints are now Git-tracked.

## Release blockers
1. README still contradicts the accepted train-vs-dev deviation in several public sections.
2. LOTA code/weight licensing is conflated; router/reliability parameter wording double-counts.
3. Devpost contradicts itself on sealed-set threshold use; training STATE says sealed was untouched.
4. Eval/provenance B-030 repairs and Codex re-review remain open.
5. Remote/public-history, MIT approval and force-push still require Mehul's explicit decisions.
6. Repository-wide Ruff currently reports 29 findings (accounted, not clean).

## NEXT ACTION
Wait for Claude's focused S1–S4 repair; re-review public claims and clean-checkout provenance.

## Literal next command
```sh
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -n 120 coordination/CHANNEL.md
```

## Hard constraints
- No public/force-push action without Mehul approval and verified target.
- Do not present incorrect, untracked, unreviewed or non-reproducible claims as shipped.
- Preserve the completed sealed predictions; never rerun them.
