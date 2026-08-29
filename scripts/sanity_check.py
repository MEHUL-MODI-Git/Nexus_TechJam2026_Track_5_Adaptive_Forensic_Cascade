"""CF-384 sanity check (task 0.6, core spec v2 §5 DoD).

Two independent checks, both of which must pass before we trust any number the
adapter produces:

1. MPS-vs-CPU consistency. MPS correctness for this architecture is unverified
   upstream, so we score the same images on both backends and require
   |logit_mps - logit_cpu| < 1e-2. Failure means fall back to CPU, not "ship it
   and hope" -- a silently wrong backend would corrupt every measurement.
2. Clean-smoke separation. >=20 real + >=20 fake images, reporting per-class
   mean p_fake and AUROC. AUROC <= 0.9 HALTS for diagnosis: it is a
   preprocessing alarm, NOT an automatic model rejection, because smoke-source
   composition can move the value (Codex review, non-blocking note 2).

Usage:
    python scripts/sanity_check.py --manifest data/manifests/smoke_v1.json
    python scripts/sanity_check.py --mps-only     # backend check alone
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch

from src.experts.commfor import CommForExpert
from src.pipeline.decode import DecodeError, decode_image

MPS_CPU_TOLERANCE = 1e-2
AUROC_FLOOR = 0.9


def auroc(scores: list[float], labels: list[int]) -> float:
    """Rank-based AUROC with tie correction (positive class = 1 = AI-generated)."""
    pairs = sorted(zip(scores, labels))
    ranks: list[float] = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # average rank over the tie block, 1-indexed
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    n_pos = sum(1 for _, y in pairs if y == 1)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("AUROC needs both classes present")
    rank_sum = sum(r for r, (_, y) in zip(ranks, pairs) if y == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def check_mps_cpu(expert: CommForExpert, paths: list[Path]) -> bool:
    if not torch.backends.mps.is_available():
        print("MPS unavailable; running on CPU -- consistency check not applicable.")
        return True
    print(f"\nMPS-vs-CPU consistency ({len(paths)} images, tolerance {MPS_CPU_TOLERANCE}):")
    worst = 0.0
    for path in paths:
        decoded = decode_image(path)
        d_mps = expert.logit_on_device(decoded, "mps")
        d_cpu = expert.logit_on_device(decoded, "cpu")
        delta = abs(d_mps - d_cpu)
        worst = max(worst, delta)
        print(f"  {path.name:<28} mps={d_mps:+.5f}  cpu={d_cpu:+.5f}  |d|={delta:.2e}")
    ok = worst < MPS_CPU_TOLERANCE
    print(f"  worst |delta| = {worst:.2e} -> {'PASS' if ok else 'FAIL (fall back to CPU)'}")
    return ok


def check_separation(expert: CommForExpert, manifest_path: Path) -> bool:
    rows = json.loads(manifest_path.read_text())
    rows = rows["images"] if isinstance(rows, dict) else rows
    root = manifest_path.resolve().parents[2]

    scores: list[float] = []
    labels: list[int] = []
    failed = 0
    for row in rows:
        path = Path(row.get("relative_path") or row["image_path"])
        if not path.is_absolute():
            path = root / path
        try:
            out = expert.predict(decode_image(path))
        except DecodeError:
            failed += 1
            continue
        scores.append(out.p_fake)
        labels.append(int(row["label"]))

    n_real = labels.count(0)
    n_fake = labels.count(1)
    print(f"\nClean-smoke separation: {n_real} real / {n_fake} fake scored"
          f"{f', {failed} undecodable' if failed else ''}")
    if n_real < 20 or n_fake < 20:
        print("  INSUFFICIENT: DoD requires >=20 per class (task 0.7 supplies them)")
        return False

    mean_real = sum(s for s, y in zip(scores, labels) if y == 0) / n_real
    mean_fake = sum(s for s, y in zip(scores, labels) if y == 1) / n_fake
    value = auroc(scores, labels)
    print(f"  mean p_fake  real={mean_real:.4f}  fake={mean_fake:.4f}")
    print(f"  AUROC = {value:.4f} (floor {AUROC_FLOOR})")
    if value <= AUROC_FLOOR:
        print("  HALT: investigate preprocessing/decode before proceeding.\n"
              "  This is a preprocessing alarm, not an automatic model rejection --\n"
              "  smoke-source composition can move this number.")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="CF-384 adapter sanity check.")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/smoke_v1.json"))
    parser.add_argument("--mps-only", action="store_true",
                        help="run only the backend-consistency check")
    parser.add_argument("--mps-images", type=int, default=5)
    args = parser.parse_args()

    expert = CommForExpert()
    print(f"expert={expert.expert_id}  device={expert.device}  "
          f"params={expert.param_count/1e6:.2f}M  license={expert.license}")
    print(f"checkpoint={expert.model_version}")

    root = Path(__file__).resolve().parents[1]
    pool = sorted((root / "tests" / "golden" / "sources").glob("*.png"))
    if args.manifest.exists():
        rows = json.loads(args.manifest.read_text())
        rows = rows["images"] if isinstance(rows, dict) else rows
        pool = [root / r["relative_path"] for r in rows[: args.mps_images]] or pool
    ok = check_mps_cpu(expert, pool[: args.mps_images])

    if not args.mps_only:
        if not args.manifest.exists():
            print(f"\nsmoke manifest {args.manifest} not found -- separation check skipped.\n"
                  f"It arrives with task 0.7 (Codex). Backend check above still applies.")
            return 0 if ok else 1
        ok = check_separation(expert, args.manifest) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
