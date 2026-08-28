"""STAGE 2: fit the reliability/abstention head against the FROZEN threshold.

The two-stage ordering (Codex R22) exists because the reliability target is
*correctness at the operating point*, which is undefined until the operating
point is frozen. Stage 1 fitted the classifier under a placeholder threshold and
deliberately left `reliability_head_fitted: False`. The threshold is now a
validated artifact, so stage 2 can run.

The invariant this script must not break: **no shipped decision may move.** Only
`reliability_head.*` parameters are trainable here; every classifier parameter is
frozen, and the script asserts that dev `p_fake` is bit-identical before and
after. A reliability head that changed the verdicts it describes would be
describing a different system.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.protocol import load_frozen_threshold
from src.router.model import reliability_targets
from src.router.train import (
    build_batch,
    load_cache_rows,
    load_checkpoint,
    validate_cache_rows,
)


def auroc(scores: np.ndarray, positive: np.ndarray) -> float:
    """Rank-based AUROC; ties averaged. No sklearn dependency in this repo."""
    pos, neg = scores[positive == 1], scores[positive == 0]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(scores.size, dtype=float)
    ranks[order] = np.arange(1, scores.size + 1, dtype=float)
    s = np.sort(scores)
    i = 0
    while i < s.size:                      # average ranks within tie groups
        j = i
        while j + 1 < s.size and s[j + 1] == s[i]:
            j += 1
        if j > i:
            ranks[np.isin(scores, s[i])] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return float((ranks[positive == 1].sum() - pos.size * (pos.size + 1) / 2.0)
                 / (pos.size * neg.size))


def selective_risk(reliability: np.ndarray, correct: np.ndarray,
                   coverages=(1.0, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5)) -> list[dict]:
    """Accuracy on the images we would KEEP, as we abstain on the least reliable.

    This is the number abstention has to justify itself with: if accuracy does
    not rise as coverage falls, the head is not ranking its own errors and the
    abstention is theatre.
    """
    order = np.argsort(-reliability, kind="mergesort")   # most reliable first
    out = []
    for cov in coverages:
        k = max(1, round(cov * reliability.size))
        kept = order[:k]
        out.append({
            "coverage": round(float(k / reliability.size), 4),
            "accuracy_on_kept": round(float(correct[kept].mean()), 4),
            "n_kept": int(k),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("data/feature_cache/fitting-v2"))
    ap.add_argument("--checkpoint", type=Path,
                    default=Path("results/router-fitting-v2/router.pt"))
    ap.add_argument("--threshold-artifact", type=Path,
                    default=Path("results/router-fitting-v2/threshold-artifact.v1.json"))
    ap.add_argument("--out", type=Path,
                    default=Path("results/router-fitting-v2/router_reliability.pt"))
    ap.add_argument("--report", type=Path,
                    default=Path("results/router-fitting-v2/reliability.json"))
    ap.add_argument("--epochs", type=int, default=3000)
    ap.add_argument("--lr", type=float, default=1e-2)
    ap.add_argument("--seed", type=int, default=20260828)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    frozen = load_frozen_threshold(args.threshold_artifact)
    thr = float(frozen.value)
    loaded = load_checkpoint(args.checkpoint)
    model = loaded.model
    print(f"frozen threshold {thr:.10f}  rung {loaded.payload['rung']}", file=sys.stderr)

    rows = load_cache_rows(args.cache / "rows.jsonl")
    expert_ids = tuple(loaded.spec.expert_ids)
    usable = validate_cache_rows(rows, expert_ids)["usable_rows"]
    train_rows = [r for r in usable if r["dataset_split"] == "train"]
    dev_rows = [r for r in usable if r["dataset_split"] == "dev"]
    # Features are derived at the FROZEN threshold, matching what the serving
    # path and the one-shot evaluator do (probe_flip is threshold-dependent).
    tb = build_batch(train_rows, loaded.spec, loaded.standardizer, thr)
    db = build_batch(dev_rows, loaded.spec, loaded.standardizer, thr)
    print(f"train={len(train_rows)} dev={len(dev_rows)}", file=sys.stderr)

    with torch.no_grad():
        before = model(db.features, db.expert_logits, db.available).p_fake.clone()

    if not any(n.startswith("reliability_head") for n, _ in model.named_parameters()):
        print("ERROR: this rung has no reliability head", file=sys.stderr)
        return 2
    for name, p in model.named_parameters():
        p.requires_grad = name.startswith("reliability_head")
    trainable = [p for p in model.parameters() if p.requires_grad]
    print(f"trainable params (reliability only): {sum(p.numel() for p in trainable)}",
          file=sys.stderr)

    opt = torch.optim.Adam(trainable, lr=args.lr)
    lossf = nn.BCEWithLogitsLoss()
    with torch.no_grad():
        t_out = model(tb.features, tb.expert_logits, tb.available)
        t_target = reliability_targets(t_out.p_fake, tb.labels, thr)
    print(f"train correctness base rate: {float(t_target.mean()):.4f}", file=sys.stderr)

    for ep in range(args.epochs):
        model.train()
        opt.zero_grad()
        out = model(tb.features, tb.expert_logits, tb.available)
        loss = lossf(out.reliability_logit, t_target)
        loss.backward()
        opt.step()
        if (ep + 1) % max(1, args.epochs // 8) == 0:
            print(f"  epoch {ep+1:5d}  loss {float(loss.detach()):.5f}", file=sys.stderr)

    model.eval()
    with torch.no_grad():
        after_out = model(db.features, db.expert_logits, db.available)
        after = after_out.p_fake
        rel = after_out.reliability.numpy()

    # THE INVARIANT. Stage 2 must not move a single verdict.
    max_shift = float((after - before).abs().max())
    if max_shift != 0.0:
        print(f"ABORT: classifier output moved by {max_shift:.3e}; stage 2 must "
              "leave every decision untouched", file=sys.stderr)
        return 3
    print(f"classifier output unchanged: max |delta p_fake| = {max_shift:.1e}",
          file=sys.stderr)

    with torch.no_grad():
        tr_out = model(tb.features, tb.expert_logits, tb.available)
        tr_rel = tr_out.reliability.numpy()
        tr_target = reliability_targets(tr_out.p_fake, tb.labels, thr).numpy()
    train_auroc = auroc(tr_rel, tr_target)
    const_loss = float(nn.BCELoss()(
        torch.full_like(t_target, float(t_target.mean())), t_target))
    print(f"\nconstant-predictor loss at the base rate: {const_loss:.5f}"
          f"   (final train loss {float(loss.detach()):.5f})", file=sys.stderr)
    print(f"TRAIN reliability AUROC vs correctness: {train_auroc:.4f}", file=sys.stderr)

    dev_target = reliability_targets(after, db.labels, thr).numpy()
    a = auroc(rel, dev_target)
    curve = selective_risk(rel, dev_target)
    print(f"\ndev reliability AUROC vs correctness: {a:.4f}"
          f"   (base accuracy {dev_target.mean():.4f})", file=sys.stderr)
    print(f"{'coverage':>10}{'accuracy':>10}{'n':>9}", file=sys.stderr)
    for pt in curve:
        print(f"{pt['coverage']:>10.2f}{pt['accuracy_on_kept']:>10.4f}{pt['n_kept']:>9d}",
              file=sys.stderr)

    # ---- PRE-REGISTERED abstention policy, selected on DEV, frozen here ----
    # Rule, fixed before looking at the internal test: take the SMALLEST
    # abstention rate whose accuracy-on-kept beats full coverage by >= 2 points.
    # Smallest, because abstention has a real cost -- every deferred image is
    # work for a human -- so we buy the least of it that clears the bar.
    base_acc = float(dev_target.mean())
    policy = None
    for pt in curve:
        if pt["coverage"] < 1.0 and (pt["accuracy_on_kept"] - base_acc) >= 0.02:
            policy = pt
            break
    if policy is None:
        print("no coverage level clears the +2 point bar; abstention NOT adopted",
              file=sys.stderr)
        abstention = {"adopted": False,
                      "rule": "smallest coverage with >= +2 points accuracy on kept"}
    else:
        # The frozen artifact is a reliability VALUE, not a percentile: a
        # percentile recomputed on new data would silently re-tune the policy
        # to whatever arrived, which is exactly the leakage we forbid elsewhere.
        rel_threshold = float(np.quantile(rel, 1.0 - policy["coverage"]))
        abstention = {
            "adopted": True,
            "rule": "smallest coverage with >= +2 points accuracy on kept",
            "selected_on": "dev split of the fitting cache",
            "reliability_threshold": rel_threshold,
            "dev_coverage": policy["coverage"],
            "dev_accuracy_on_kept": policy["accuracy_on_kept"],
            "dev_accuracy_full_coverage": round(base_acc, 4),
            "dev_gain_points": round(policy["accuracy_on_kept"] - base_acc, 4),
        }
        print(f"\nABSTENTION POLICY (frozen on dev): abstain when reliability < "
              f"{rel_threshold:.6f}\n  dev coverage {policy['coverage']:.2f}, "
              f"accuracy {base_acc:.4f} -> {policy['accuracy_on_kept']:.4f}",
              file=sys.stderr)

    payload = dict(loaded.payload)
    payload["state_dict"] = model.state_dict()
    payload["reliability_head_fitted"] = True
    payload["abstention"] = abstention
    payload["reliability_provenance"] = {
        "stage": "2 — fitted after threshold freeze (R22)",
        "threshold": thr,
        "threshold_artifact_sha256": frozen.artifact_sha256,
        "fitted_on": "fitting cache train split only",
        "classifier_frozen": True,
        "classifier_output_max_shift": max_shift,
        "dev_reliability_auroc": a,
        "epochs": args.epochs, "lr": args.lr, "seed": args.seed,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, args.out)

    code_rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=False).stdout.strip() or "unknown"
    args.report.write_text(json.dumps({
        "schema_version": "reliability-fit.v1",
        "NOT_A_HEADLINE_RESULT": "dev-split diagnostic; abstention policy is chosen here "
                                 "and only then reported once on the internal test",
        "threshold": thr,
        "classifier_output_max_shift": max_shift,
        "dev_reliability_auroc": a,
        "train_reliability_auroc": train_auroc,
        "constant_predictor_loss": const_loss,
        "final_train_loss": float(loss.detach()),
        "dev_base_accuracy": float(dev_target.mean()),
        "selective_risk_dev": curve,
        "abstention_policy": abstention,
        "n_train_rows": len(train_rows), "n_dev_rows": len(dev_rows),
        "code_revision": code_rev,
    }, indent=2) + "\n")
    print(f"\nwrote {args.out} and {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
