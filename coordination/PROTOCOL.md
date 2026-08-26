# Coordination Protocol — Claude (AGENT-A) ⇄ Codex (AGENT-B)

The filesystem/git is the only shared medium between the two agents. Everything below exists so that parallel work never collides, decisions are joint, and either agent can die mid-step and lose at most that step.

## 1. The channel — `coordination/CHANNEL.md`
- Append-only, chronological, monotonically numbered messages.
- Format:
  ```
  ## MSG-007 | claude → codex | 2026-08-27 14:30 | NEEDS-REPLY | subject
  body (short; link files instead of pasting content)
  ```
- Tags: `NEEDS-REPLY` (blocking question — answer before starting new work), `FYI` (no reply needed), `GATE` (checkpoint packet posted), `ESCALATE` (for Mehul).
- Read-pointers live at the top of CHANNEL.md (`claude last-read: MSG-nnn`, `codex last-read: MSG-nnn`). Update your pointer every session.
- Session rule: read everything past your pointer **before** writing code; answer `NEEDS-REPLY` first.

## 2. Parallel work without collisions
- Task claims in `STATUS.md` (task id from `06-build-plan.md`, owner, state). Claim before starting; release when done or parked.
- Directory ownership: Claude = `src/pipeline`, `src/experts`, `src/router`; Codex = `src/eval`, `src/app`. Shared (`configs/`, `scripts/`, `STATUS.md`, root docs) = claim like a task.
- Interfaces are contracts: the ExpertOutput schema (doc 03), the feature-cache row schema (doc 04), and the eval-results JSON schema are frozen once both agents ACK them in CHANNEL. Changing a contract = DECISIONS.md entry + version bump.
- Git: pull → work → small commits (`[claude]`/`[codex]` prefix) → push often. Merge conflicts on STATE/STATUS: newest wins, log it.

## 3. Checkpoints (joint review of done work + next steps)
Cadence: **every phase exit** (Phases 0–5 of `06-build-plan.md`) — which is roughly daily — plus an ad-hoc checkpoint whenever a kill-criterion decision (doc 08) is triggered.

Procedure:
1. **Owner posts a gate packet** at `coordination/gates/phase-<n>-<workstream>.md`: what was built, evidence (test output, metrics tables, file paths), exit-test result vs `06-build-plan.md`, known gaps, proposed next-phase task split. Announce with a `GATE` message in CHANNEL.
2. **The other agent reviews** at its next session start (heavy model, not delegated): verify the exit test actually passes (run it, don't trust prose), check hard constraints, challenge weak evidence. Post verdict in CHANNEL: `APPROVE`, `APPROVE-WITH-NOTES`, or `BLOCK: <reason>`.
3. **Joint next-step discussion** happens as a short CHANNEL exchange (proposal → counter → agreement), then:
4. **Record in `coordination/DECISIONS.md`**: what was decided, who proposed, who approved, evidence file, and what observation would reverse it. Update both agents' STATE.md files with the agreed next actions.
5. `BLOCK` unresolved after one exchange round → `ESCALATE` message summarizing both positions for Mehul. Never silently override the other agent.

## 4. Decision rights — the agents are EQUALS
- Neither agent outranks the other. Identical authority, identical rules, mutual review in both directions. Ownership = responsibility for execution, not superior judgment; either agent may propose, challenge, or veto anything in either workstream (through CHANNEL, never by editing the other's code). Ties are broken by evidence — a measurement, a failing test, a doc citation — never by who said it first. No evidence available → ESCALATE to Mehul.
- Inside your own workstream, decide freely within docs 00–08 and the build plan; log in your CHANGELOG.
- Cross-cutting (architecture, datasets, thresholds, eval protocol, schedule/scope changes, dropping a component per kill criteria) → joint decision via §3, recorded in DECISIONS.md.
- Mehul outranks everything; quote his instruction in the DECISIONS/CHANGELOG entry when a decision was his.

## 5. Model economy (both sides)
- Heavy models: plans, specs, reviews, judgment, constraint-sensitive code (preprocessing exactness, eval math, calibration), gate verdicts.
- Cheap models (Claude → Sonnet subagents; Codex → mini tier): mechanical execution of a written spec — downloads, boilerplate, batch-job babysitting, test scaffolds, formatting, plots/tables.
- Invariant: **heavy spec → cheap execute → heavy verify.** A cheap model's output never lands unverified in `src/pipeline`, `src/experts`, `src/router`, `src/eval`, or `configs/`.

## 6. Limit-relay fallback (degraded mode)
Default operation is parallel peers. If one agent hits usage limits / becomes unavailable (Mehul announces it, or a claimed task sits untouched with no CHANNEL activity for >3 hours during active hours):
- The available agent posts a `FYI relay-mode ON` message, then may claim the unavailable agent's in-flight tasks — following that workstream's STATE.md literal-next-command, not reinventing the approach.
- Cross-review is suspended for relay work but every relay change is logged in the owning CHANGELOG with tag `[relay]`; the returning agent's FIRST action is reviewing the `[relay]` entries and posting APPROVE/BLOCK per item.
- Relay mode ends the moment the other agent posts again; ownership reverts.
- Efficiency guardrails (always, not just relay): max one ACK round per decision; batch multiple small items into one message; only contracts, gates, and kill-criteria events need ACKs — everything else is FYI.

## 7. Continuity invariants (session death safety)
- STATE.md is overwritten the moment a milestone lands (≤60 lines, literal next command always present).
- CHANGELOG.md is append-only, newest first; corrections are new entries, never edits.
- Long in-context analyses that must survive → `handoffs/YYYY-MM-DD_<topic>.md` + one row in the owning STATE.md "Read next" table; archive after consumption.
- Gate evidence lives in `coordination/gates/` — a decision must remain auditable after both sessions die.
- Teaching/explanations Mehul asks for → `teaching/`, numbered folders, never scattered.
