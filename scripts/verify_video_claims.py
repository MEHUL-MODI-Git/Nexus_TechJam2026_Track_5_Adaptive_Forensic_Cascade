"""Check every number the video says against what the system actually produces.

    .venv/bin/python scripts/verify_video_claims.py

Written after a real failure: the script told the presenter to say "you can't see any
difference" over an image whose added noise was plainly visible on screen, and quoted
certificate values from a different image than the one it told him to upload. Eyeballing
does not catch that. This does.

It runs the REAL UI functions and the REAL CLIs, then asserts that each figure quoted in
`RECORD-THE-VIDEO.md` and `video-slides.html` appears in that live output, or matches the
committed artifact it is sourced from. Any mismatch is a hard failure.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GUIDE = ROOT / "deliverables" / "RECORD-THE-VIDEO.md"
SLIDES = ROOT / "deliverables" / "video-slides.html"
CLEAN = ROOT / "deliverables" / "video-assets" / "bird_clean.png"
JPEG = ROOT / "deliverables" / "video-assets" / "bird_jpeg_q30.png"

ok, fail = [], []


def check(name, condition, detail=""):
    (ok if condition else fail).append(name)
    mark = "\033[32m✓\033[0m" if condition else "\033[31m✗\033[0m"
    print(f"  {mark} {name}" + (f"   {detail}" if detail and not condition else ""))


def plain(html):
    return " ".join(re.sub("<[^>]+>", " ", html)
                    .replace("&rarr;", "->").replace("&#9888;", "!").split())


def main() -> int:
    print("\033[1mVerifying every video claim against the live system\033[0m\n")

    for p in (CLEAN, JPEG):
        check(f"asset exists: {p.name}", p.exists())
    if fail:
        return 1

    from src.app.app import _default_service, analyze_image, stress_test_image
    svc = _default_service()
    if callable(svc) and not hasattr(svc, "predict_image"):
        svc = svc()

    guide = GUIDE.read_text()
    slides = SLIDES.read_text()

    # ---------- the hook image, as the guide instructs him to upload it ----------
    print("\n\033[1mScene 1 — the compressed image in the UI\033[0m")
    card = plain(analyze_image(str(JPEG), svc)[0])
    for claim in ("0.0191", "0.9458", "JPEG compression (99% confidence)", "DEFERRED"):
        check(f"UI card shows {claim!r}", claim in card, f"card={card[:160]}")
        check(f"guide quotes {claim!r}", claim in guide)

    clean_card = plain(analyze_image(str(CLEAN), svc)[0])
    check("clean image reads 0.9995 for the raw detector", "0.9995" in clean_card)

    # ---------- the stress panel ----------
    print("\n\033[1mScene 4 — the stress panel\033[0m")
    s = stress_test_image(str(JPEG), svc)
    cert = plain(s[0])
    for claim in ("18 / 20", "MEDIUM", "94.9%"):
        check(f"certificate shows {claim!r}", claim in cert, f"cert={cert[:200]}")
    check("guide says 18 / 20", "18 / 20" in guide or "Eighteen out of twenty" in guide)
    check("guide says MEDIUM", "MEDIUM" in guide or "medium confidence" in guide)
    check("guide says 94.9%", "94.9" in guide)

    flips = [plain(r).split()[0] for r in re.findall(r"<tr>(.*?)</tr>", s[2], re.DOTALL)
             if "FLIPPED" in r]
    check("exactly 2 conditions flip", len(flips) == 2, f"got {flips}")
    check("they are blur_s2.0 and resize_0.25", set(flips) == {"blur_s2.0", "resize_0.25"},
          f"got {flips}")
    for f in ("blur_s2.0", "resize_0.25"):
        check(f"guide names {f}", f in guide)

    # ---------- claims that must NOT appear any more ----------
    print("\n\033[1mRemoved content must stay removed\033[0m")
    for banned, why in (("0.0166", "old noise-image score"),
                        ("0.9986", "old noise-image score"),
                        ("17 / 20", "old certificate"),
                        ("84.9", "old certificate"),
                        ("can't see any difference", "false claim over visible grain"),
                        ("JPEG and every fake", "format-confound disclosure, cut"),
                        ("format alone predicted", "format-confound disclosure, cut")):
        check(f"guide is free of {why}", banned not in guide, f"found {banned!r}")
        check(f"slides free of {why}", banned not in slides, f"found {banned!r}")

    # ---------- slide figures against committed artifacts ----------
    print("\n\033[1mSlide figures vs committed artifacts\033[0m")
    it = json.loads((ROOT / "results/internal-test/results.json").read_text())
    sealed = json.loads((ROOT / "results/sealed/reference-results.json").read_text())
    ops = json.loads((ROOT / "results/ops/ops-evidence.json").read_text())
    d = sealed["conventions"]["deduplicated"]

    figures = [
        ("71.1%", round(it["primary_at_0.5"]["clean_fake_recall"] * 100, 1) == 71.1),
        ("0.7% at noise s0.10",
         round(it["primary_at_0.5"]["per_condition"]["noise_s0.10"]["fake_recall"] * 100, 1) == 0.7),
        ("12% worst-family primary",
         round(it["primary_at_0.5"]["worst_family_fake_recall"] * 100) == 12),
        ("83% worst-family ours",
         round(it["router"]["worst_family_fake_recall"] * 100) == 83),
        ("33% FPR-matched baseline",
         round(it["primary_at_matched_clean_fpr"]["worst_family_fake_recall"] * 100) == 33),
        ("90.9% overall accuracy", round(it["router"]["overall_accuracy"] * 100, 1) == 90.9),
        ("87.9% sealed worst-family",
         round(d["worst_family_fake_recall"] * 100, 1) == 87.9),
        ("1.58% sealed clean FPR", round(d["clean"]["fpr"] * 100, 2) == 1.58),
        ("0.9964 sealed clean AUROC", round(d["clean"]["auroc"], 4) == 0.9964),
        ("174,380 sealed rows", sealed["n_rows"] == 174380),
        ("21,814,571 parameters", ops["parameters"]["shipped_total"] == 21814571),
        ("1.09% of the cap", round(ops["parameters"]["percent_of_limit"], 2) == 1.09),
        ("1,827 router parameters", ops["parameters"]["router_head"] == 1827),
    ]
    for label, cond in figures:
        check(f"artifact backs {label}", cond)
    for txt in ("71.1", "0.7", "12", "83", "33", "90.9", "87.9", "1.58", "0.9964",
                "174,380", "21,814,571", "1.09", "1,827"):
        check(f"slides quote {txt}", txt in slides)

    # ---------- the two terminal commands he runs on camera ----------
    print("\n\033[1mScene 7 — terminal commands\033[0m")
    out = ROOT / "deliverables" / "video-assets" / "_verify.json"
    r = subprocess.run([sys.executable, "scripts/infer_dir.py",
                        "deliverables/video-assets", "--output", str(out)],
                       cwd=ROOT, capture_output=True, text=True, check=False)
    check("infer_dir.py exits 0", r.returncode == 0, r.stderr[-200:])
    check("infer_dir.py reports 0 failed", "0 failed" in r.stdout + r.stderr)
    out.unlink(missing_ok=True)

    r = subprocess.run([sys.executable, "scripts/run_eval.py", "--config", "configs/frozen.yaml"],
                       cwd=ROOT, capture_output=True, text=True, check=False)
    check("run_eval --config exits 0", r.returncode == 0, r.stderr[-200:])
    check("run_eval reports 0 drifted", "0 drifted" in r.stdout, r.stdout[-200:])

    # ---------- runtime budget ----------
    print("\n\033[1mRuntime budget\033[0m")
    words = sum(len(l[1:].split()) for l in guide.split("\n") if l.startswith(">"))
    seconds = words / 145 * 60 + 47      # 47s of measured, unavoidable waits
    check(f"under the 5:00 cap ({seconds:.0f}s, {words} words)", seconds < 300,
          f"{seconds:.0f}s")

    print("\n" + "─" * 64)
    if fail:
        print(f"\033[31m{len(fail)} FAILED\033[0m of {len(ok) + len(fail)}:")
        for f in fail:
            print(f"  - {f}")
        return 1
    print(f"\033[32mALL {len(ok)} CHECKS PASSED.\033[0m The video script matches the system.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
