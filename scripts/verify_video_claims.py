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

GUIDE = ROOT / "deliverables" / "RECORDING-CHEAT-SHEET.md"
SLIDES = ROOT / "deliverables" / "video-slides.html"
JPEG = ROOT / "deliverables" / "video-assets" / "bird_jpeg_q30.png"
BCLEAN = ROOT / "deliverables" / "video-assets" / "board_clean.png"
BJPEG = ROOT / "deliverables" / "video-assets" / "board_jpeg_q70.png"

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

    for p in (JPEG, BCLEAN, BJPEG):
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
    print("\n\033[1mMoment 2 — the easy case (board_clean)\033[0m")
    bc = plain(analyze_image(str(BCLEAN), svc)[0])
    for claim in ("0.9625", "0.7070"):
        check(f"UI shows {claim!r}", claim in bc, f"card={bc[:170]}")
        check(f"sheet quotes {claim!r}", claim in guide)
    check("easy case does NOT defer", "DEFERRED" not in bc, bc[:170])

    print("\n\033[1mMoment 3 — the confident win (board_jpeg_q70)\033[0m")
    bj = plain(analyze_image(str(BJPEG), svc)[0])
    for claim in ("0.0993", "0.9062", "0.927", "JPEG compression (91% confidence)"):
        check(f"UI shows {claim!r}", claim in bj, f"card={bj[:200]}")
        check(f"sheet quotes {claim!r}", claim in guide)
    check("MOMENT 3 MUST NOT DEFER — the first example is a clean win",
          "DEFERRED" not in bj, bj[:200])

    print("\n\033[1mMoment 6 — the deferral, shown later on purpose\033[0m")
    card = plain(analyze_image(str(JPEG), svc)[0])
    for claim in ("0.9458", "0.788", "DEFERRED"):
        check(f"UI shows {claim!r}", claim in card, f"card={card[:180]}")
        check(f"sheet quotes {claim!r}", claim in guide)

    # ---------- the stress panel ----------
    print("\n\033[1mScene 4 — the stress panel\033[0m")
    s = stress_test_image(str(BJPEG), svc)
    cert = plain(s[0])
    for claim in ("18 / 20", "MEDIUM", "94.9%"):
        check(f"certificate shows {claim!r}", claim in cert, f"cert={cert[:200]}")
    check("guide says 18 / 20", "18 / 20" in guide or "Eighteen out of twenty" in guide)
    check("guide says MEDIUM", "MEDIUM" in guide or "medium confidence" in guide)
    check("guide says 94.9%", "94.9" in guide)

    flips = [plain(r).split()[0] for r in re.findall(r"<tr>(.*?)</tr>", s[2], re.DOTALL)
             if "FLIPPED" in r]
    check("exactly 2 conditions flip", len(flips) == 2, f"got {flips}")
    check("they are resize_0.25 and bright_+20", set(flips) == {"resize_0.25", "bright_+20"},
          f"got {flips}")
    for f in ("resize_0.25", "bright_+20"):
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
    # the COUNT is on screen in Moment 10, so it is a claim like any other.
    # It was wrong once: the sheet said 4 while the folder held 3, and checking
    # only "0 failed" let that through.
    n_png = len(list((ROOT / "deliverables" / "video-assets").glob("*.png")))
    combined = r.stdout + r.stderr
    check(f"infer_dir.py finds exactly {n_png} image(s)",
          f"found {n_png} image(s)" in combined, combined[:160])
    check(f"sheet's EXPECT says found {n_png} image(s)",
          f"found {n_png} image(s)" in guide)
    check(f"sheet's EXPECT says {n_png} scored", f"{n_png} scored, 0 failed" in guide)
    out.unlink(missing_ok=True)

    r = subprocess.run([sys.executable, "scripts/run_eval.py", "--config", "configs/frozen.yaml"],
                       cwd=ROOT, capture_output=True, text=True, check=False)
    check("run_eval --config exits 0", r.returncode == 0, r.stderr[-200:])
    check("run_eval reports 0 drifted", "0 drifted" in r.stdout, r.stdout[-200:])

    # ---------- slide EXPECT phrases must exist in the deck ----------
    print("\n\033[1mSlide EXPECT phrases vs the deck\033[0m")
    slide_phrases = [
        "Canonical decode", "Frozen expert", "Damage descriptors",
        "Reliability router", "Verdict + confidence grade",
        "We handicapped ourselves, and still report the smaller number",
        "On the organizers' own data, it beat our own numbers",
        "It holds up. And when it can't, it says so.",
        "21,814,571 parameters", "+49.2 points",
    ]
    for ph in slide_phrases:
        check(f"deck contains {ph[:44]!r}", ph in slides)

    # ---------- every MOMENT has all three parts ----------
    print("\n\033[1mCheat-sheet structure\033[0m")
    moments = re.findall(r"\n## MOMENT (\d+)[^\n]*\n(.*?)(?=\n## |\n# POST)", guide, re.DOTALL)
    check("eleven moments", len(moments) == 11, f"found {len(moments)}")
    for num, body in moments:
        for part in ("**DO:**", "**SAY:**", "**EXPECT"):
            has = part in body or (part == "**SAY:**" and "**SAY (" in body)
            check(f"moment {num} has {part.strip('*:')}", has)

    # ---------- overlays must be short and artifact-backed ----------
    print("\n\033[1mPost-production overlays\033[0m")
    rows = re.findall(r"\| *\d+ *\| *[^|]+\| *`([^`]+)` *\| *([^|]+)\|", guide)
    check("17 overlays defined", len(rows) == 17, f"found {len(rows)}")
    for text, src in rows:
        check(f"overlay <=8 words: {text[:34]!r}", len(text.split()) <= 8,
              f"{len(text.split())} words")
        check(f"overlay cites a source: {text[:28]!r}", src.strip() != "")

    # ---------- runtime budget ----------
    print("\n\033[1mRuntime budget\033[0m")
    # only the SAY blocks are spoken; EXPECT notes are also blockquotes and must not count
    words = sum(sum(len(x[1:].split()) for x in m.group(1).splitlines())
                for m in re.finditer(r"\*\*SAY[^*]*\*\*\s*\n((?:>.*\n)+)", guide))
    seconds = words / 145 * 60 + 33      # 33s of measured IN-CLIP waits (splices cut the rest)
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
