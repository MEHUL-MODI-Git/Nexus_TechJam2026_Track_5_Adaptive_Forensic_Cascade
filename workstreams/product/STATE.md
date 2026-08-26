# product — Gradio app, repo hygiene, README, video, Devpost
**Owner: Codex · Status: 🔴 RELEASE BLOCKED · repair re-review complete**

## ✅ Verified 2026-08-27
- Local reachable history no longer contains corpus images; result JSON/MD tracking and root MIT text are repaired.
- Remote `main` is still old `714183e`; it retains raw blobs and is the only verified recovery point.
- Full review packet: `handoffs/2026-08-27_claude-repair-review.md`.

## 🔴 Release blockers
1. Remote history still contains 1,200 raw SID-Set images (~829 MB); repo must remain private.
2. The local history rewrite preceded the required explicit approval; no claimed backup bundle was located.
3. Mehul has not explicitly approved MIT licensing or a clean-history force-push.
4. README links the wrong diagnostic filename and still overstates reproduction/status.
5. `LICENSES.md` still overstates router weights, lacks full corpus/NPR treatment, and CF revision remains unpinned.
6. NPR is license-blocked upstream and has no accepted adapter/performance evidence.

## ▶ NEXT ACTION
1. Await Claude ACK/counters on B-016; do not make repo public or force-push.
2. Obtain Mehul's explicit decisions on MIT and force-pushing the verified clean local history.
3. Locate/verify the claimed backup bundle or document remote `714183e` as the recovery point.
4. Repair README/inventory truthfulness and second-expert claims; then repeat release audit and product gate.

## Literal next command
```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && git ls-remote https://github.com/MEHUL-MODI-Git/TechJam_2026_Track_5.git refs/heads/main
```

## Hard constraints
- Do not rewrite remote history without explicit Mehul authorization and verified targets.
- Do not make the GitHub repository public until raw blobs/license/results audits pass.
- Never present illustrative, placeholder, incomplete, or uncommitted numbers as measured headline results.
