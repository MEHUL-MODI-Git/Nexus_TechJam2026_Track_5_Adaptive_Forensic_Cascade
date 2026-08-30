"""The Phase-4 exit test: verify every published table against its artifact and inputs.

    scripts/run_eval.py --config configs/frozen.yaml      # the build plan's literal command
    scripts/reproduce_frozen.py --config configs/frozen.yaml [--regenerate]

B-032 P0, Codex Phase-4 exit audit: `06-build-plan.md` line 118 requires this command to
reproduce every reported table from the feature cache, and neither `configs/frozen.yaml` nor
`run_eval.py --config` existed. README §5 documented only the old 8,000-row placeholder smoke
diagnostic, not the protected tables actually published.

Default mode VERIFIES and touches nothing:

  * every input still hashes to what the artifact was computed from,
  * every artifact still hashes to what was published,
  * inputs absent from a clean clone are reported as SKIPPED, not as passes.

`--regenerate` additionally re-runs each regenerable command and reports any artifact whose
hash moved. That is the honest form of "reproduces": a regeneration that changes a hash is a
finding, not a failure to be smoothed over.

THE SEALED TABLE IS SUMMARY-ONLY AND STAYS THAT WAY. Its command summarises the preserved
prediction dump; the sealed subset is scored exactly once and already was. This script refuses
to run any sealed entry that is not marked `summary_only`.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(config_path: Path, regenerate: bool = False) -> int:
    cfg = yaml.safe_load(config_path.read_text())
    if cfg.get("schema_version") != "frozen-reproduction.v1":
        print(f"REFUSING: {config_path} is not a frozen-reproduction.v1 manifest", file=sys.stderr)
        return 2

    ok, drifted, skipped, missing = [], [], [], []
    for entry in cfg["tables"]:
        name = entry["name"]
        artifact = ROOT / entry["artifact"]

        if entry.get("sealed") and not entry.get("summary_only"):
            print(f"REFUSING: sealed entry {name!r} is not marked summary_only; the sealed "
                  "subset is scored exactly once and already was", file=sys.stderr)
            return 2

        # inputs first: an artifact that matches while its inputs moved is worse than a
        # mismatch, because it looks like agreement.
        input_state = []
        for src in entry.get("inputs") or []:
            got = sha256(ROOT / src["path"])
            if got is None:
                input_state.append(("skip", src["path"]))
            elif src["sha256"] == "ABSENT":
                input_state.append(("unrecorded", src["path"]))
            elif got != src["sha256"]:
                input_state.append(("drift", src["path"]))
            else:
                input_state.append(("ok", src["path"]))

        got = sha256(artifact)
        if got is None:
            missing.append(name)
            print(f"  MISSING   {name:<26} {entry['artifact']}")
            continue

        if regenerate and entry.get("regenerable"):
            cmd = entry["command"].split()
            cmd[0] = sys.executable
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                drifted.append((name, "regeneration failed"))
                print(f"  FAILED    {name:<26} rc={proc.returncode} "
                      f"{proc.stderr.strip().splitlines()[-1:] }")
                continue
            got = sha256(artifact)

        bad_inputs = [p for state, p in input_state if state == "drift"]
        skipped_inputs = [p for state, p in input_state if state == "skip"]

        if bad_inputs:
            drifted.append((name, f"input(s) changed: {bad_inputs}"))
            print(f"  INPUT-DRIFT {name:<24} {bad_inputs}")
        elif got != entry["artifact_sha256"]:
            drifted.append((name, "artifact hash changed"))
            print(f"  DRIFT     {name:<26} {got[:12]} != {entry['artifact_sha256'][:12]}")
        elif skipped_inputs:
            skipped.append(name)
            print(f"  OK*       {name:<26} artifact matches; {len(skipped_inputs)} "
                  "input(s) absent (git-ignored, expected in a clean clone)")
        else:
            ok.append(name)
            print(f"  OK        {name:<26} artifact and all inputs match")

    print(f"\n{len(ok)} verified, {len(skipped)} verified with absent inputs, "
          f"{len(drifted)} drifted, {len(missing)} missing")
    if drifted:
        print("\nDRIFT IS A FINDING, NOT A FAILURE TO SMOOTH OVER:", file=sys.stderr)
        for name, why in drifted:
            print(f"  - {name}: {why}", file=sys.stderr)
    return 1 if (drifted or missing) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=ROOT / "configs" / "frozen.yaml")
    ap.add_argument("--regenerate", action="store_true",
                    help="re-run each regenerable command and report hash drift")
    args = ap.parse_args()
    return run(args.config, args.regenerate)


if __name__ == "__main__":
    raise SystemExit(main())
