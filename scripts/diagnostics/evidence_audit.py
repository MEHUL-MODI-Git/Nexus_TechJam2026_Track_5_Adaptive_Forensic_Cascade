"""Forensic Evidence Survival Audit — validation experiment ONLY.

Question: where does the detector's evidence live, is it concentrated or spread,
and does it survive degradation? Built as a bounded test, not a UI.

THE GUARD THAT COMES FIRST. Occlusion attribution perturbs a patch and reads the
score change. But this detector reads HIGH-FREQUENCY forensic traces -- that is
the most established fact in this project, and it is why LOTA and PGC both died.
Masking a patch CREATES high-frequency artefacts, so `score(x) - score(x_masked)`
may be measuring how much the mask confused the detector rather than what the
patch contributed. So every map is computed under TWO different occlusion
operators (local-mean fill, heavy blur). If the two disagree, the method is
measuring its own artefacts and the audit is void -- reported as such, not
patched around.

Only if the guard passes do we ask the question that would justify shipping this:
does evidence concentration or survival separate CORRECT from CONFIDENTLY WRONG
predictions? That is the documented blind spot of the reliability head.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.experts.commfor import CommForExpert
from src.pipeline.decode import decode_image
from src.pipeline.transforms import apply_transform
from src.router.train import build_batch, load_cache_rows, load_checkpoint

GRID = 4


def occlude(img: Image.Image, box, mode: str) -> Image.Image:
    out = img.copy()
    patch = out.crop(box)
    if mode == "mean":
        mean = tuple(int(c) for c in np.asarray(patch, dtype=np.float64).mean(axis=(0, 1))[:3])
        out.paste(Image.new("RGB", patch.size, mean), box)
    elif mode == "blur":
        out.paste(patch.filter(ImageFilter.GaussianBlur(radius=8)), box)
    else:
        raise ValueError(mode)
    return out


def evidence_map(expert, decoded, mode: str) -> tuple[np.ndarray, float]:
    """|score change| per patch under one occlusion operator."""
    base = expert.predict(decoded).p_fake
    w, h = decoded.image.size
    imp = np.zeros(GRID * GRID)
    for k in range(GRID * GRID):
        r, c = divmod(k, GRID)
        box = (c * w // GRID, r * h // GRID, (c + 1) * w // GRID, (r + 1) * h // GRID)
        view = replace(decoded, image=occlude(decoded.image, box, mode))
        view = replace(view, width=view.image.width, height=view.image.height)
        imp[k] = abs(base - expert.predict(view).p_fake)
    return imp, base


def concentration(imp: np.ndarray) -> dict:
    total = imp.sum()
    if total <= 0:
        return {"top1_fraction": float("nan"), "effective_patches": float("nan")}
    p = imp / total
    ent = -np.sum(np.where(p > 0, p * np.log(p), 0.0))
    return {"top1_fraction": float(np.max(p)),
            "effective_patches": float(np.exp(ent))}   # perplexity: 1=one patch, 16=uniform


def corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.std() < 1e-12 or b.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=220)
    ap.add_argument("--guard-n", type=int, default=40)
    ap.add_argument("--out", type=Path,
                    default=Path("results/evidence-audit/validation.json"))
    ap.add_argument("--seed", type=int, default=20260828)
    args = ap.parse_args()

    rows = load_cache_rows(Path("data/feature_cache/internal-test-v2/rows.jsonl"))
    loaded = load_checkpoint(Path("results/router-fitting-v2/router_reliability.pt"))
    thr, REL = 0.4667367651127279, 0.866079568862915
    clean = [r for r in rows if r["condition_id"] == "clean"]
    b = build_batch(clean, loaded.spec, loaded.standardizer, thr)
    with torch.no_grad():
        o = loaded.model(b.features, b.expert_logits, b.available)
    p, rel = o.p_fake.numpy(), o.reliability.numpy()
    lab = np.array([r["label"] for r in clean])
    ok = (p >= thr) == (lab == 1)

    rng = np.random.default_rng(args.seed)
    root = Path(__file__).resolve().parents[2]
    expert = CommForExpert()

    # ---- GUARD: do two occlusion operators agree? -------------------------
    idx = rng.choice(len(clean), size=min(args.guard_n, len(clean)), replace=False)
    agree = []
    for i in idx:
        d = decode_image(root / clean[i]["relative_path"])
        m1, _ = evidence_map(expert, d, "mean")
        m2, _ = evidence_map(expert, d, "blur")
        agree.append(corr(m1, m2))
    agree = np.asarray(agree, float)
    median_agreement = float(np.nanmedian(agree))
    print(f"OCCLUSION GUARD over {len(idx)} images: median map correlation "
          f"between mean-fill and blur = {median_agreement:.3f}", file=sys.stderr)
    guard_passed = median_agreement >= 0.5
    if not guard_passed:
        print("GUARD FAILED: the two occlusion operators disagree, so the maps "
              "measure occlusion artefacts rather than evidence. Audit VOID.",
              file=sys.stderr)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "schema_version": "evidence-audit.v1", "guard_passed": False,
            "median_operator_agreement": median_agreement,
            "verdict": "VOID - occlusion attribution measures its own artefacts",
            "n_guard": len(idx),
        }, indent=2) + "\n")
        return 0

    # ---- the question worth answering -------------------------------------
    pick = rng.choice(len(clean), size=min(args.n, len(clean)), replace=False)
    recs = []
    for n, i in enumerate(pick, 1):
        d = decode_image(root / clean[i]["relative_path"])
        m0, base = evidence_map(expert, d, "mean")
        surv = {}
        for cond in ("jpeg_q30", "noise_s0.10"):
            img = apply_transform(d.image, cond, d.sha256)
            dv = replace(d, image=img, width=img.width, height=img.height)
            mc, _ = evidence_map(expert, dv, "mean")
            surv[cond] = corr(m0, mc)
        recs.append({"correct": bool(ok[i]), "reliability": float(rel[i]),
                     "would_abstain": bool(rel[i] < REL), "base_p_fake": float(base),
                     "total_evidence": float(m0.sum()), **concentration(m0),
                     **{f"survival_{k}": v for k, v in surv.items()}})
        if n % 50 == 0:
            print(f"  {n}/{len(pick)}", file=sys.stderr)

    def summarise(subset, name):
        if not subset:
            return None
        g = lambda k: float(np.nanmean([r[k] for r in subset]))
        return {"name": name, "n": len(subset), "top1_fraction": g("top1_fraction"),
                "effective_patches": g("effective_patches"),
                "total_evidence": g("total_evidence"),
                "survival_jpeg_q30": g("survival_jpeg_q30"),
                "survival_noise_s0.10": g("survival_noise_s0.10")}

    groups = {
        "correct": [r for r in recs if r["correct"]],
        "wrong": [r for r in recs if not r["correct"]],
        "confidently_wrong": [r for r in recs if not r["correct"] and not r["would_abstain"]],
        "confidently_correct": [r for r in recs if r["correct"] and not r["would_abstain"]],
    }
    summary = {k: summarise(v, k) for k, v in groups.items()}
    print(f"\n{'group':<22}{'n':>5}{'top1':>9}{'eff.patch':>11}"
          f"{'evidence':>10}{'surv jpeg':>11}{'surv noise':>12}", file=sys.stderr)
    for s in summary.values():
        if s:
            print(f"{s['name']:<22}{s['n']:>5}{s['top1_fraction']:>9.3f}"
                  f"{s['effective_patches']:>11.2f}{s['total_evidence']:>10.3f}"
                  f"{s['survival_jpeg_q30']:>11.3f}{s['survival_noise_s0.10']:>12.3f}",
                  file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "schema_version": "evidence-audit.v1",
        "NOT_A_HEADLINE_RESULT": "dev-style exploratory audit on internal-test clean rows",
        "guard_passed": True, "median_operator_agreement": median_agreement,
        "grid": GRID, "n_audited": len(recs), "groups": summary, "records": recs,
    }, indent=2) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
