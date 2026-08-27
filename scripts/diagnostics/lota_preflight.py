"""LOTA preflight: does the checkpoint work, which way does it point, how fast (2R/3R).

DIAGNOSTIC ONLY. Uses LOTA's OWN code (`third_party/LOTA`) for preprocessing and
model construction, so nothing here is a reimplementation that could silently
drift from the paper. Answers, with measurements rather than assumptions:

  1. does the checkpoint load strictly into the official module;
  2. which direction is the score -- `loader.py:103` labels NATURAL as 1, so the
     official sigmoid is P(real), the OPPOSITE of our P(fake) convention;
  3. clean separability on our smoke set;
  4. per-image latency, which decides whether it can ever sit in the 15k cache;
  5. how much the mandatory RandomCrop patch selection makes the score wobble
     run-to-run, since the update pack requires deterministic inference.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.pipeline.hf_cache import use_repo_local_torch_cache

# LOTA's model factory calls resnet50(pretrained=True), which downloads ImageNet
# weights through torch.utils.model_zoo -- set before importing its module.
use_repo_local_torch_cache()

sys.path.insert(0, str(ROOT / "third_party" / "LOTA"))

from bit_patch import bit_patch  # LOTA's own preprocessing
from model import model as LotaModel  # LOTA's own module
from torchvision import transforms

IMG_HEIGHT, PATCH_SIZE = 256, 32
BIT_MODE, PATCH_MODE = "scaling", "max"
NORMALIZE = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])


def preprocess(path: Path) -> torch.Tensor:
    img = Image.open(path).convert("RGB")
    patch = bit_patch(img, IMG_HEIGHT, BIT_MODE, PATCH_SIZE, PATCH_MODE)
    return NORMALIZE(transforms.ToTensor()(patch))


def auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    pos, neg = labels == 1, labels == 0
    if not pos.any() or not neg.any():
        return float("nan")
    return float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2)
                 / (pos.sum() * neg.sum()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", type=Path, default=Path("LOTA weights/sdv5_scaling_patch32.pth"))
    ap.add_argument("--manifest", type=Path, default=Path("data/manifests/smoke_v1.json"))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--repeats", type=int, default=3, help="determinism probe repeats")
    ap.add_argument("--out", type=Path, default=Path("results/lota/preflight.json"))
    args = ap.parse_args()

    net = LotaModel(pretrain=False)
    state = torch.load(args.weights, map_location="cpu", weights_only=True)
    missing, unexpected = net.load_state_dict(state, strict=False)
    print(f"load_state_dict: {len(missing)} missing, {len(unexpected)} unexpected",
          file=sys.stderr)
    if missing or unexpected:
        print(f"  missing={missing[:5]} unexpected={unexpected[:5]}", file=sys.stderr)
    net.eval().to(args.device)
    n_params = sum(p.numel() for p in net.parameters())

    rows = json.loads(args.manifest.read_text())["images"]
    reals = [r for r in rows if r["label"] == 0][: args.limit // 2]
    fakes = [r for r in rows if r["label"] == 1][: args.limit // 2]
    sample = reals + fakes

    labels, raw_logits, latencies = [], [], []
    torch.manual_seed(0)
    for row in sample:
        path = ROOT / row["relative_path"]
        started = time.perf_counter()
        tensor = preprocess(path).unsqueeze(0).to(args.device)
        with torch.no_grad():
            logit = float(net(tensor).flatten()[0])
        latencies.append(time.perf_counter() - started)
        labels.append(row["label"])
        raw_logits.append(logit)

    labels_arr = np.array(labels)
    logits_arr = np.array(raw_logits)
    p_real_official = 1.0 / (1.0 + np.exp(-logits_arr))
    p_fake_ours = 1.0 - p_real_official

    # Determinism: RandomCrop picks the candidate patches, so the same image can
    # score differently on consecutive runs. The update pack REQUIRES determinism.
    probe = sample[:20]
    repeat_scores = []
    for _ in range(args.repeats):
        scores = []
        for row in probe:
            tensor = preprocess(ROOT / row["relative_path"]).unsqueeze(0).to(args.device)
            with torch.no_grad():
                scores.append(float(torch.sigmoid(net(tensor)).flatten()[0]))
        repeat_scores.append(scores)
    spread = np.max(np.array(repeat_scores), axis=0) - np.min(np.array(repeat_scores), axis=0)

    result = {
        "schema_version": "lota-preflight.v1",
        "weights": str(args.weights),
        "n_parameters": n_params,
        "state_dict_missing_keys": len(missing),
        "state_dict_unexpected_keys": len(unexpected),
        "n_images": len(sample),
        "auroc_as_p_fake": auroc(labels_arr, p_fake_ours),
        "auroc_if_polarity_flipped": auroc(labels_arr, p_real_official),
        "mean_p_fake_real_images": float(p_fake_ours[labels_arr == 0].mean()),
        "mean_p_fake_ai_images": float(p_fake_ours[labels_arr == 1].mean()),
        "latency_ms_mean": float(np.mean(latencies) * 1000),
        "latency_ms_p95": float(np.percentile(latencies, 95) * 1000),
        "throughput_img_per_sec": float(1.0 / np.mean(latencies)),
        "determinism": {
            "repeats": args.repeats, "n_probe_images": len(probe),
            "max_score_spread": float(spread.max()),
            "mean_score_spread": float(spread.mean()),
            "deterministic": bool(spread.max() < 1e-6),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
