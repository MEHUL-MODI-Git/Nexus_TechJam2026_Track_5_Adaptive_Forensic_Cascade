# product — Gradio app, repo hygiene, README, video, Devpost
**Owner: Codex · Status: 🔴 RELEASE BLOCKED BY B-032 + OWNER ACTIONS**

## Accepted
- Task 1.5 stress panel remains accepted.
- S1/S3 public wording and probe-parity disclosures are accepted.
- README/Devpost now separate LOTA MIT code from unlicensed Baidu weights and correct parameter/
  sealed-control wording.
- A-036 proves the configured cascade runs in a fresh clone: 756 passed / 14 skipped / 0 failed,
  both CLIs rc=0, six images scored, cold 87.3 MB checkpoint download.

## Remaining release blockers
1. The live CF-384 revision is unpinned, so a future clone may serve different expert bytes.
2. README current status contradicts its shipped-system sections; checklist and shareable handoff
   remain stale. Perform one current-state sweep.
3. Eval's B-032 frozen-reproduction/internal/sealed reporter blockers must close before release.
4. Remote/public-history force-push, root MIT approval, repo-public and video/trademark decisions
   remain Mehul's explicit owner actions.

## NEXT ACTION
Wait for Claude's B-032 repair, then re-review frozen reproduction and release truthfulness.

## Literal next command
```sh
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && tail -n 100 coordination/CHANNEL.md
```

## Hard constraints
- No public/force-push action without Mehul approval and verified target.
- Do not present incorrect, untracked, unreviewed or non-reproducible claims as shipped.
- Preserve the completed sealed predictions; never rerun them.
