# TechJam 2026 — Track 5: Adaptive Forensic Cascade

Solo hackathon build (Mehul) executed by two AI agents working **as equals**: **AGENT-A = Claude** (this file's reader) and **AGENT-B = Codex** (reads `AGENTS.md`, which mirrors this shared rulebook). Neither agent outranks the other — this file is shared law, not Claude's law. **Deadline: Mon 1 Sept, 12:00pm — submit by ~9am.** Webinar: Thu 28 Aug, 5:00pm.

## Project index (one line each)
- `docs/00-official-brief.md` — organizer brief: transform grid, <2B rule, deliverables, judging weights.
- `docs/01-research-landscape.md` — model/paper review; why CF-384 + LOTA + WaRPAD.
- `docs/02-decision-history.md` — how the architecture evolved; decision principles.
- `docs/03-recommended-architecture.md` — the cascade spec: adapters, router, probes, calibration, abstention.
- `docs/04-training-and-data.md` — datasets, splits, contamination controls, losses.
- `docs/05-evaluation-and-ablations.md` — metrics, stress matrix, ablation matrix, error taxonomy.
- `06-build-plan.md` — **THE execution plan**: Phases 0–5, per-phase tasks, exit tests, fallback ladder.
- `docs/08-risks-kill-criteria-open-questions.md` — kill criteria per component; webinar questions.
- Docs 00–08 are ground truth. Never rewrite them; correct via CHANGELOG entries.

## RESUME PROTOCOL
1. Read `STATUS.md` (global dashboard: phase, task claims, blockers) — 30 seconds.
2. Read the STATE.md of the workstream you are touching (only that one).
3. Read `coordination/CHANNEL.md` messages after your read-pointer; reply to `NEEDS-REPLY` items first.
4. Confirm STATE.md's NEXT ACTION matches Mehul's ask; if they conflict, Mehul's ask wins — log the override in CHANGELOG.

| Workstream | Owner | Entry file | History file |
|---|---|---|---|
| core (decode, transforms, expert adapters, predict path) | Claude | `workstreams/core/STATE.md` | `workstreams/core/CHANGELOG.md` |
| training (corpus, feature cache, router, calibration) | Claude | `workstreams/training/STATE.md` | `workstreams/training/CHANGELOG.md` |
| eval (harness, ablations, error analysis) | Codex | `workstreams/eval/STATE.md` | `workstreams/eval/CHANGELOG.md` |
| product (Gradio, repo hygiene, README, video, Devpost) | Codex | `workstreams/product/STATE.md` | `workstreams/product/CHANGELOG.md` |

Ownership = who writes the code and its STATE/CHANGELOG. The other agent reviews at gates. Full protocol: `coordination/PROTOCOL.md`.

## Standing rules
- **Write-as-you-go.** The moment a milestone completes: append to that workstream's CHANGELOG, overwrite its STATE.md, update STATUS.md task claims. Never batch to session end. A half-done task must say where it stands and give the literal next command.
- **Session-start.** Follow RESUME PROTOCOL above. Do not re-read all docs; the "Read next" table in each STATE.md names the one file each task needs.
- **Session-end checklist.** CHANGELOG written? STATE.md overwritten, ≤60 lines, literal next command present? CHANNEL messages answered/posted? Anything important existing only in chat → `handoffs/`? Teaching material filed in `teaching/`?
- **Model economy.** Heavy model (Fable/Opus for Claude; Codex's top model) keeps: plans, architecture, adapter-correctness verification, eval interpretation, gate reviews, anything touching hard constraints. Grunt work goes to cheap models (Sonnet subagents for Claude; Codex's mini tier): dataset downloads, boilerplate from a written spec, batch/caching job babysitting, tests from a spec, formatting, table transcription. Pattern: **heavy writes the spec → cheap executes → heavy verifies the result.** Never send judgment down; never burn heavy tokens on mechanical work.
- **Git discipline.** Claim a task in STATUS.md before starting. Pull before work. Small commits prefixed `[claude]` / `[codex]`. Never edit files inside a task the other agent has claimed; shared files (configs, STATUS.md) get claimed like tasks.
- **Peer equality (Mehul, 26 Aug).** Claude and Codex are equals: identical authority, identical rules, mutual review. Either agent may propose, challenge, or veto anything — including in the other's workstream (via CHANNEL, not by editing the other's code). Ties are broken by evidence (measurements, tests), never by seniority; no evidence → escalate to Mehul. Workstream ownership means responsibility for execution, not superior judgment over it.
- **Strengths-based allocation (Mehul, 26 Aug).** Route tasks to whoever is genuinely better at them, regardless of workstream ownership — reassign via a CHANNEL message.
  - **Claude's strengths:** paper/repo-to-code fidelity (adapter preprocessing exactness), ML/statistics judgment (training, calibration, ablation interpretation), long multi-step agentic jobs (batch pipelines, orchestrating subagents), and **all prose deliverables** — README narrative, Devpost write-up, video script, error-analysis note (drafts them even though they sit in Codex's product workstream; Codex reviews).
  - **Codex's strengths:** surgical implementation of well-specified code (metrics math, transform functions, tests), debugging tight failures, UI/frontend work (Gradio, plots, layout), fast iteration loops on small diffs.
  - Neither is a status ranking (see Peer equality). If a task fights its owner for >1 hour, offer it to the other agent in CHANNEL before grinding.
- **Cross-agent decisions.** Anything that changes the architecture, the eval protocol, thresholds, datasets, or the build plan requires a DECISIONS.md entry with BOTH agents on record; phase exits require a joint checkpoint (see PROTOCOL.md). One round of disagreement max — then escalate to Mehul in CHANNEL.md with both positions stated.
- **Isolation.** No isolated workstreams. The one sealed asset is the official WildFake reference subset — see hard constraints.

## Hard constraints
- **NEVER train/fit/tune/threshold on the sealed WildFake reference subset** (COCO val2017 4,998 + DALL-E Advanced 8,843). Hash denylist check runs before every training job. One sealed evaluation run, Phase 4 only.
- COCO **val2017** never appears in any training source (use train2017 for reals).
- All models combined <2B params (ours ≈50M) — keep per-component counts documented.
- One decision threshold across all transforms; never tune per-condition (leakage).
- Transform pipeline changes require golden-test update + cache-version bump.
- Demo/video assets: licensed only, no third-party trademarks.

## Stable facts
- Hardware: Apple M4 Pro, 24 GB RAM, 166 GB free, PyTorch MPS. Python 3.12 (pyenv), use `uv`.
- Checkpoints: `OwensLab/commfor-model-384` (HF, MIT, 21.8M) · LOTA `github.com/hongsong-wang/LOTA` (23.6M) · WaRPAD arXiv 2511.14030 (RIGID backup).
- Code layout (from Phase 0): `src/{pipeline,experts,router,eval,app}`, `scripts/`, `configs/`, `tests/`, `results/`.
- Run commands: added here once Phase 0 lands (this is the only planned edit to this file).
