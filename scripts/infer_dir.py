"""Directory inference -- REQUIRED official deliverable (core spec v2 §6b).

Organizer requirement (docs/00a-brief-addendum-2026-08-26.md, evidence
docs/evidence/2026-08-26_track5-deliverables.png):

    "A script that takes an image directory as input and outputs a confidence
     score for each image, indicating the likelihood that it is AIGC-generated.
     The output should be a JSON file containing image_path and pred for each
     image."

Judges may run this on hidden data, so it is written defensively: per-file
error isolation, deterministic ordering, atomic write, bounded memory, and no
crash on a bad file.

    python scripts/infer_dir.py INPUT_DIR --output predictions.json

`pred` is our final calibrated p_fake in [0,1], higher = more likely
AI-generated. Until the router exists it is CF-384's score.

CORRUPT-FILE POLICY (--errors), pending one Codex ACK (CHANNEL A-010 item 3):
  null   (default) a row for EVERY recognized image; failures get pred=null
                   plus an "error" key. Chosen because the requirement says the
                   JSON contains image_path and pred FOR EACH IMAGE -- a missing
                   row silently misaligns any consumer that zips inputs to
                   outputs, which is worse than a visible null. A null is also
                   never an invented score.
  skip             omit failed rows entirely (Codex's product-spec §5 default).
  strict           exit nonzero on the first failure. Our gate smoke uses this,
                   so a regression cannot hide behind a tolerated null.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.decode import DecodeError
from src.pipeline.service import PredictionError, PredictionService

# Case-insensitive; matched against the suffix, so ".JPG" and ".jpg" both count.
SUPPORTED_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".ppm", ".pgm"}
)


def find_images(root: Path, recursive: bool = True) -> list[Path]:
    """Recognized image files, ordered deterministically by relative POSIX path.

    Sorting on the normalized relative path (not on filesystem order, which
    varies by platform) is what makes two runs byte-comparable.
    """
    walker = root.rglob("*") if recursive else root.glob("*")
    found = [
        p for p in walker
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(found, key=lambda p: p.relative_to(root).as_posix())


def _atomic_write_json(payload, path: Path) -> None:
    """Write via a temp file in the same directory, then rename.

    A killed run must not leave a half-written predictions file that looks
    complete to whoever reads it next.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def run(
    input_dir: Path,
    output: Path,
    errors: str = "null",
    recursive: bool = True,
    progress_every: int = 25,
    service: PredictionService | None = None,
) -> tuple[list[dict], int]:
    """Score a directory. Returns (rows, failure_count)."""
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        raise NotADirectoryError(f"not a directory: {input_dir}")

    images = find_images(input_dir, recursive=recursive)
    print(f"found {len(images)} image(s) under {input_dir}", file=sys.stderr)
    if service is None:
        service = PredictionService.from_config()

    rows: list[dict] = []
    failures = 0
    for i, path in enumerate(images, start=1):
        # Paths are emitted relative to the input dir and POSIX-normalized so
        # the output is identical across platforms and run locations.
        rel = path.relative_to(input_dir).as_posix()
        try:
            record = service.predict_image(path)
        except (DecodeError, PredictionError, OSError) as exc:
            failures += 1
            reason = "decode_failed" if isinstance(exc, (DecodeError, OSError)) else "inference_failed"
            print(f"  [{i}/{len(images)}] {rel}: {reason}: {exc}", file=sys.stderr)
            if errors == "strict":
                raise
            if errors == "skip":
                continue
            # Default: keep the row so the output stays aligned with the input,
            # with a null rather than an invented score.
            rows.append({"image_path": rel, "pred": None, "error": reason})
            continue
        rows.append({"image_path": rel, "pred": record.p_fake})
        if progress_every and (i % progress_every == 0 or i == len(images)):
            print(f"  [{i}/{len(images)}] scored", file=sys.stderr)

    _atomic_write_json(rows, output)
    scored = sum(1 for r in rows if r.get("pred") is not None)
    print(f"wrote {output} -- {scored} scored, {failures} failed", file=sys.stderr)
    return rows, failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score every image in a directory; emit JSON {image_path, pred}."
    )
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("predictions.json"))
    parser.add_argument("--errors", choices=("null", "skip", "strict"), default="null",
                        help="how to handle files that cannot be scored (default: null)")
    parser.add_argument("--no-recursive", action="store_true",
                        help="score only the top level of INPUT_DIR")
    args = parser.parse_args()

    try:
        _, failures = run(
            args.input_dir, args.output,
            errors=args.errors, recursive=not args.no_recursive,
        )
    except (DecodeError, PredictionError) as exc:   # only reachable under --errors strict
        print(f"strict mode: aborting on {exc}", file=sys.stderr)
        return 2
    except NotADirectoryError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    # Default and skip modes exit 0 even with failures: the failures are visible
    # in the output rows and on stderr, and a nonzero exit would make a judge's
    # harness treat a complete, usable file as a failed run.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
