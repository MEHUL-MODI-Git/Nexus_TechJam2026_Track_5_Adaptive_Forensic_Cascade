"""LOTA format sensitivity: does the LSB signal survive JPEG re-encoding?

DIAGNOSTIC ONLY. Reuses `scripts/diagnostics/lota_preflight.py`'s exact model
construction, preprocessing (`third_party/LOTA/bit_patch.py`), and polarity
handling (`sigmoid` is P(REAL); `p_fake = 1 - sigmoid`).

Hypothesis under test: LOTA's signal lives entirely in the low 3 bits of each
RGB channel. Our corpus reals are natively JPEG and our corpus fakes are
natively PNG (verified by file magic bytes, not extension -- every manifest
row uses a `.jpg` filename regardless of the real container format). If
LOTA's apparent skill on that corpus disappears once both classes are pushed
through the same JPEG Q95 container, the skill was a file-format artifact of
JPEG quantizing away the low bits, not genuine AI-detection signal.

For each sampled image we decode the original bytes to RGB once, then build
three variants from those SAME decoded pixels:
  A. native   -- the decoded pixels themselves (no re-encode)
  B. jpeg_q95 -- those pixels re-encoded to JPEG quality 95 in memory, then
                 re-decoded (so LOTA sees exactly what a JPEG Q95 codec keeps)
  C. png      -- those pixels re-encoded losslessly to PNG in memory, then
                 re-decoded (round-trip control: same operation as B minus
                 the lossy quantization)
B and C share pixels going in; only the container/compression differs, which
isolates the JPEG-quantization effect from any other confound.
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.pipeline.hf_cache import use_repo_local_torch_cache

# LOTA's model factory calls resnet50(pretrained=True), which downloads
# ImageNet weights through torch.utils.model_zoo -- set before importing it.
use_repo_local_torch_cache()

sys.path.insert(0, str(ROOT / "third_party" / "LOTA"))

from bit_patch import bit_patch  # LOTA's own preprocessing
from model import model as LotaModel  # LOTA's own module
from torchvision import transforms

IMG_HEIGHT, PATCH_SIZE = 256, 32
BIT_MODE, PATCH_MODE = "scaling", "max"
NORMALIZE = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
VARIANTS = ("native", "jpeg_q95", "png")


def make_variants(path: Path) -> dict[str, Image.Image]:
    """Decode the on-disk bytes once, then derive jpeg_q95/png from those pixels."""
    native = Image.open(path).convert("RGB")

    jpeg_buf = io.BytesIO()
    native.save(jpeg_buf, format="JPEG", quality=95)
    jpeg_buf.seek(0)
    jpeg_q95 = Image.open(jpeg_buf).convert("RGB")

    png_buf = io.BytesIO()
    native.save(png_buf, format="PNG")
    png_buf.seek(0)
    png = Image.open(png_buf).convert("RGB")

    return {"native": native, "jpeg_q95": jpeg_q95, "png": png}


def preprocess(img: Image.Image) -> torch.Tensor:
    patch = bit_patch(img, IMG_HEIGHT, BIT_MODE, PATCH_SIZE, PATCH_MODE)
    return NORMALIZE(transforms.ToTensor()(patch))


def auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Rank-based AUROC (Mann-Whitney U), no extra dependencies."""
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    pos, neg = labels == 1, labels == 0
    if not pos.any() or not neg.any():
        return float("nan")
    return float(
        (ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * neg.sum())
    )


def sample_rows(manifest: dict, per_class: int, seed: int) -> list[dict]:
    rows = manifest["images"]
    reals = [r for r in rows if r["label"] == 0]
    fakes = [r for r in rows if r["label"] == 1]
    rng = random.Random(seed)
    picked_reals = rng.sample(reals, per_class)
    picked_fakes = rng.sample(fakes, per_class)
    return picked_reals + picked_fakes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", type=Path, default=Path("LOTA weights/sdv5_scaling_patch32.pth"))
    ap.add_argument("--manifest", type=Path, default=Path("data/manifests/router_corpus_v2.json"))
    ap.add_argument("--per-class", type=int, default=100)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("results/lota/format_sensitivity.json"))
    args = ap.parse_args()

    net = LotaModel(pretrain=False)
    state = torch.load(args.weights, map_location="cpu", weights_only=True)
    missing, unexpected = net.load_state_dict(state, strict=False)
    print(f"load_state_dict: {len(missing)} missing, {len(unexpected)} unexpected",
          file=sys.stderr)
    net.eval().to(args.device)

    manifest = json.loads(args.manifest.read_text())
    sample = sample_rows(manifest, args.per_class, args.seed)
    labels = np.array([row["label"] for row in sample])

    torch.manual_seed(args.seed)
    random.seed(args.seed)

    # per_image_scores[variant] -> list of mean-over-repeats p_fake, one per image
    per_image_scores: dict[str, list[float]] = {v: [] for v in VARIANTS}
    per_image_spread: dict[str, list[float]] = {v: [] for v in VARIANTS}
    latencies: list[float] = []
    native_container_flags: list[str] = []

    for row in sample:
        path = ROOT / row["relative_path"]
        with open(path, "rb") as fh:
            head = fh.read(8)
        native_container_flags.append("JPEG" if head[:2] == b"\xff\xd8" else
                                       ("PNG" if head[:8] == b"\x89PNG\r\n\x1a\n" else "OTHER"))

        started = time.perf_counter()
        variants = make_variants(path)
        for name, img in variants.items():
            repeat_scores = []
            for _ in range(args.repeats):
                tensor = preprocess(img).unsqueeze(0).to(args.device)
                with torch.no_grad():
                    logit = float(net(tensor).flatten()[0])
                p_real = 1.0 / (1.0 + np.exp(-logit))
                repeat_scores.append(1.0 - p_real)
            repeat_scores_arr = np.array(repeat_scores)
            per_image_scores[name].append(float(repeat_scores_arr.mean()))
            per_image_spread[name].append(float(repeat_scores_arr.max() - repeat_scores_arr.min()))
        latencies.append(time.perf_counter() - started)

    from collections import Counter
    container_counts_real = Counter(f for f, row in zip(native_container_flags, sample)
                                     if row["label"] == 0)
    container_counts_fake = Counter(f for f, row in zip(native_container_flags, sample)
                                     if row["label"] == 1)

    per_variant = {}
    for name in VARIANTS:
        scores = np.array(per_image_scores[name])
        spread = np.array(per_image_spread[name])
        pred_fake = scores > 0.5
        real_mask, fake_mask = labels == 0, labels == 1
        per_variant[name] = {
            "auroc": auroc(labels, scores),
            "mean_p_fake_real_images": float(scores[real_mask].mean()),
            "mean_p_fake_fake_images": float(scores[fake_mask].mean()),
            "fake_recall_at_0_5": float(pred_fake[fake_mask].mean()),
            "false_positive_rate_at_0_5": float(pred_fake[real_mask].mean()),
            "mean_score_spread_across_repeats": float(spread.mean()),
            "max_score_spread_across_repeats": float(spread.max()),
        }

    native_auroc = per_variant["native"]["auroc"]
    jpeg_auroc = per_variant["jpeg_q95"]["auroc"]
    png_auroc = per_variant["png"]["auroc"]

    def band(x: float) -> str:
        if x >= 0.95:
            return "near-perfect separability"
        if x >= 0.8:
            return "strong separability"
        if x >= 0.65:
            return "moderate separability, clearly above chance"
        if x >= 0.55:
            return "weak separability, modestly above chance"
        return "at chance"

    reading_parts = [
        (
            f"native AUROC={native_auroc:.4f} ({band(native_auroc)}), "
            f"jpeg_q95 AUROC={jpeg_auroc:.4f} ({band(jpeg_auroc)}), "
            f"png AUROC={png_auroc:.4f} ({band(png_auroc)})."
        )
    ]

    # B vs C is the controlled comparison: same decoded pixels in both, only
    # the container/compression differs. This is what actually isolates the
    # JPEG-quantization effect from any "which native container was this"
    # confound -- native alone cannot do that, because on this corpus native
    # container perfectly predicts label (real=JPEG-native, fake=PNG-native).
    if png_auroc >= 0.9 and jpeg_auroc <= png_auroc - 0.3:
        gap = png_auroc - jpeg_auroc
        reading_parts.append(
            f"png stays at {band(png_auroc)} while jpeg_q95 -- built from the "
            f"SAME decoded pixels, only re-encoded lossy -- drops by {gap:.4f} "
            "AUROC. Since the only thing that changed between B and C is the "
            "container, this isolates JPEG quantization as the cause and "
            "confirms the LSB/JPEG hypothesis: LOTA's signal lives in the "
            "low-bit planes that JPEG re-encoding destroys."
        )
        if native_auroc >= png_auroc - 0.05:
            reading_parts.append(
                "native tracks png closely rather than sitting apart from it, so "
                "the high native AUROC is NOT simply a 'which container did this "
                "file arrive in' shortcut (that would have also collapsed under "
                "png, since png forces both classes into the same lossless "
                "container and the score stayed high anyway) -- it is consistent "
                "with a real pixel-level signal, not a naive file-format artifact."
            )
        if jpeg_auroc > 0.55:
            reading_parts.append(
                f"jpeg_q95 AUROC ({jpeg_auroc:.4f}) is closer to chance (0.5) than "
                f"to native/png ({png_auroc:.4f}), but it is not exactly 0.5, so a "
                "small amount of separable signal survives Q95 recompression -- "
                "the collapse is large but not total."
            )
    elif native_auroc <= 0.55 and jpeg_auroc <= 0.55 and png_auroc <= 0.55:
        reading_parts.append(
            "AUROC is at chance in ALL THREE variants, including native. This "
            "does not support the stated hypothesis (there is no native skill "
            "to lose) -- it suggests LOTA has no usable signal on this corpus "
            "at all, format aside."
        )
    else:
        reading_parts.append(
            "Result does not cleanly match the 'native high, png high, jpeg_q95 "
            "collapses' pattern the hypothesis predicts; report the numbers as "
            "measured rather than forcing them into the hypothesis."
        )
    reading = " ".join(reading_parts)

    result = {
        "schema_version": "lota-format-sensitivity.v1",
        "weights": str(args.weights),
        "manifest": str(args.manifest),
        "n_per_class": args.per_class,
        "n_images_total": len(sample),
        "repeats_per_variant": args.repeats,
        "seed": args.seed,
        "native_container_by_label": {
            "real": dict(container_counts_real),
            "fake": dict(container_counts_fake),
        },
        "per_variant": per_variant,
        "latency_ms_per_image_all_variants_mean": float(np.mean(latencies) * 1000),
        "latency_ms_per_image_all_variants_p95": float(np.percentile(latencies, 95) * 1000),
        "reading": reading,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
