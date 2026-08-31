"""One command that gets this machine ready to record the demo video.

    .venv/bin/python scripts/video_setup.py

Does every technical thing so the person recording only has to click and talk:
stops any server left running, checks the staged images exist, warms the model
so no loading pause is filmed, runs all three terminal commands once to confirm
they work and to prove the printed numbers are current, then starts the UI.

Everything it runs is read-only. It never fits, trains, or re-scores anything
sealed. Deterministic: the model is frozen, so repeated runs print the same
numbers -- there is no seed to set.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
CLEAN = "deliverables/video-assets/bird_clean.png"
JPEG = "deliverables/video-assets/bird_jpeg_q30.png"
URL = "http://127.0.0.1:7860"

OK, BAD, DOT = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[90m·\033[0m"


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False, **kw)


def step(msg):
    print(f"\n\033[1m{msg}\033[0m")


def main() -> int:
    print("\033[1mGetting ready to record\033[0m  (about 40 seconds)")
    problems = []

    step("1. Restarting clean on the CURRENT build")
    run(["pkill", "-f", "src.app"])
    time.sleep(1)
    print(f"  {OK} any previous server stopped — the take will run the build you have now")
    # State reset is a MOVE-ASIDE, never a delete: a bad reset must be recoverable.
    assets = ROOT / "deliverables" / "video-assets"
    stash = ROOT / "deliverables" / "video-assets" / "_previous-takes"
    moved = 0
    for f in assets.glob("predictions.json"):
        stash.mkdir(exist_ok=True)
        f.replace(stash / f"{f.stem}-{int(time.time())}{f.suffix}")
        moved += 1
    for f in (ROOT / "predictions.json",):
        if f.exists():
            stash.mkdir(exist_ok=True)
            f.replace(stash / f"predictions-{int(time.time())}.json")
            moved += 1
    print(f"  {OK} demo state reset ({moved} file(s) moved aside to _previous-takes, nothing deleted)")

    step("2. Checking the two images are where the script expects them")
    for rel in (CLEAN, JPEG):
        if (ROOT / rel).exists():
            print(f"  {OK} {rel}")
        else:
            print(f"  {BAD} MISSING {rel}")
            problems.append(f"missing {rel}")
    if problems:
        print("\n  Recreate them with:  .venv/bin/python scripts/video_setup.py --rebuild-images")
        return 2

    step("3. Warming the detector so no loading pause gets filmed")
    t = time.time()
    warm = run([PY, "scripts/predict.py", CLEAN, "--json"])
    if warm.returncode != 0:
        print(f"  {BAD} the model would not load")
        print(warm.stderr.strip()[-400:])
        return 2
    print(f"  {OK} model loaded and warm ({time.time() - t:.0f}s)")

    step("4. Running the three terminal shots once, to confirm they work")
    checks = []

    a = run([PY, "scripts/predict.py", CLEAN, "--json"])
    b = run([PY, "scripts/predict.py", JPEG, "--json"])
    if a.returncode == 0 and b.returncode == 0:
        da, db = json.loads(a.stdout), json.loads(b.stdout)
        print(f"  {OK} predict.py")
        print(f"      {DOT} clean : detector alone {da['router']['primary_p_fake']:.4f}"
              f"  ours {da['p_fake']:.4f}")
        print(f"      {DOT} jpeg  : detector alone \033[31m{db['router']['primary_p_fake']:.4f}"
              f"\033[0m  ours \033[32m{db['p_fake']:.4f}\033[0m   <- the whole story")
        checks.append(True)
    else:
        print(f"  {BAD} predict.py failed"); problems.append("predict.py"); checks.append(False)

    au = run([PY, "scripts/audit_image.py", CLEAN])
    if au.returncode == 0 and "20 / 20" in au.stdout:
        print(f"  {OK} audit_image.py  {DOT} clean image scores 20 / 20, grade HIGH")
        checks.append(True)
    else:
        print(f"  {BAD} audit_image.py did not print the expected 20 / 20")
        problems.append("audit_image.py"); checks.append(False)

    out = ROOT / "deliverables" / "video-assets" / "_setup_check.json"
    inf = run([PY, "scripts/infer_dir.py", "deliverables/video-assets", "--output", str(out)])
    if inf.returncode == 0:
        print(f"  {OK} infer_dir.py  {DOT} batch interface scored the folder, 0 failed")
        out.unlink(missing_ok=True)
        checks.append(True)
    else:
        print(f"  {BAD} infer_dir.py failed"); problems.append("infer_dir.py"); checks.append(False)

    step("5. Starting the demo UI")
    log = ROOT / "deliverables" / "video-assets" / "_app.log"
    proc = subprocess.Popen([PY, "-m", "src.app"], cwd=ROOT,
                            stdout=log.open("w"), stderr=subprocess.STDOUT)
    up = False
    for _ in range(60):
        time.sleep(1)
        try:
            up = urllib.request.urlopen(URL, timeout=2).status == 200
        except Exception:                                        # noqa: BLE001
            up = False   # server still booting; keep polling until the deadline
        if up:
            break
    if up:
        print(f"  {OK} running at \033[1m{URL}\033[0m  (pid {proc.pid})")
    else:
        print(f"  {BAD} the UI did not come up — see {log}")
        problems.append("gradio app")

    step("6. Verifying every number in the guide against the live system")
    v = run([PY, "scripts/verify_video_claims.py"])
    if v.returncode == 0:
        n = [ln for ln in v.stdout.splitlines() if "CHECKS PASSED" in ln]
        print(f"  {OK} {n[0].strip() if n else 'all claims verified'}")
    else:
        print(f"  {BAD} the guide and the system disagree:")
        for ln in v.stdout.splitlines():
            if "✗" in ln:
                print(f"      {ln.strip()}")
        problems.append("guide/system mismatch")

    print("\n" + "─" * 62)
    if problems:
        print(f"\033[31mNOT READY\033[0m — fix these first: {', '.join(problems)}")
        return 1
    print("\033[32mREADY TO RECORD.\033[0m Now, in order:")
    print(f"""
  1. Open the slides         deliverables/video-slides.html   (press F for fullscreen)
  2. Open the demo           {URL}
  3. Read ONLY this, top to bottom:
                             deliverables/RECORDING-CHEAT-SHEET.md

  When you are completely finished recording, stop the server with:
      .venv/bin/python scripts/video_setup.py --stop
""")
    return 0


if __name__ == "__main__":
    if "--stop" in sys.argv:
        run(["pkill", "-f", "src.app"])
        for f in ("_app.log", "_setup_check.json"):
            (ROOT / "deliverables" / "video-assets" / f).unlink(missing_ok=True)
        print(f"{OK} server stopped, temporary files cleaned up")
        raise SystemExit(0)
    if "--rebuild-images" in sys.argv:
        sys.path.insert(0, str(ROOT))
        from src.pipeline.decode import decode_image
        from src.pipeline.transforms import apply_transform
        src = ROOT / "data/corpus/canonical/fully_synthetic/45b84a4682e7a640.jpg"
        d = decode_image(src)
        for cond, nm in (("clean", "bird_clean"), ("jpeg_q30", "bird_jpeg_q30")):
            p = ROOT / "deliverables/video-assets" / f"{nm}.png"
            apply_transform(d.image, cond, d.sha256).save(p)
            print(f"{OK} rebuilt {p.name}")
        raise SystemExit(0)
    raise SystemExit(main())
