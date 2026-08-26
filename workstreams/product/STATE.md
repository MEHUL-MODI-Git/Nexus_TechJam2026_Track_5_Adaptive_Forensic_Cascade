# product — Gradio app, repo hygiene, README, video, Devpost
**Owner: Codex · Status: 🔴 RELEASE BLOCKED · relay review complete**

## ✅ Verified 2026-08-27
- Live Gradio `/stress_test` succeeds on a real smoke image and returns all 20 conditions, SVG, table, and summary.
- Escaping, table fallback, error gaps, and non-color-only flip markers are good.
- Full review packet: `handoffs/2026-08-27_claude-relay-critical-review.md`.

## 🔴 Release blockers
1. 1,200 raw SID-Set images (~829 MB) are tracked and pushed in commit 4046141; repo must remain private.
2. Results ignore rules are broken; remote has no claimed JSON/MD artifacts.
3. Root LICENSE is absent; license inventory omits/incorrectly states dependencies and new corpus redistribution.
4. README overstates trained router/calibration/rescue, pinned model revision, one decision path, and committed artifacts.
5. Stress path accepts NaN/invalid decisions and calls clean-only + 19 failures “stable”; chart theme can be low contrast.

## ▶ NEXT ACTION
1. Await Claude ACK/counters on B-015; do not make repo public.
2. Prepare a clean-history/data-removal plan for Mehul approval before destructive history rewriting.
3. Repair repo tracking/license truthfulness, then stress validation/theme and README.
4. Re-run live E2E and request Claude product gate review.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && git ls-files 'data/corpus/images/**' | wc -l
```

## Hard constraints
- Do not rewrite remote history without explicit Mehul authorization and verified targets.
- Do not make the GitHub repository public until raw blobs/license/results audits pass.
- Never present illustrative, placeholder, incomplete, or uncommitted numbers as measured headline results.
