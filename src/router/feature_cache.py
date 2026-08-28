"""Feature cache builder (Phase 2 backbone) — `specs/phase2-feature-cache.md` v2.

The router trains on features, not images. Producing them means running every
expert and every probe over the corpus × the transform grid: hours of compute
that must never be silently repeated, and never silently reused when stale.

Two properties everything here serves:
1. **A row proves which code produced it.** The cache key hashes a canonical
   JSON object over pipeline/probe versions, config hashes and expert
   fingerprints; a mismatch REFUSES to append rather than mixing generations.
2. **A row records what happened, including failure.** No imputation anywhere.

STORAGE DEVIATION FROM THE FROZEN SPEC (recorded, not quiet): the spec names
Parquet. `pyarrow` is not in the lockfile, and adding a dependency to a file
another agent owns while it is offline is not a call to make in passing. Storage
is therefore pluggable — Parquet when pyarrow is importable, JSONL otherwise —
and the chosen format is recorded in the manifest. Rows are schema-identical
either way.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..experts.base import Expert, ExpertInferenceError
from ..pipeline.decode import DecodeError, decode_image
from ..pipeline.probes import compute_probe_features
from ..pipeline.quality import compute_quality
from ..pipeline.transforms import CONDITION_IDS, FAMILY_OF
from ..pipeline.version import PIPELINE_VERSION, PROBE_VERSION

SCHEMA_VERSION = "feature-cache-row.v2"
# Only used to satisfy the probe helper's signature; no threshold-dependent
# value derived from it is ever written to a row (R9).
_UNUSED_THRESHOLD = 0.5
ALLOWED_SPLITS = frozenset({"train", "dev"})


class DenylistViolation(Exception):
    """A sealed-reference image reached a fitting corpus. Fatal, always."""


class CacheKeyMismatch(Exception):
    """The cache directory was produced by different code. Never mix."""


def _library_versions() -> dict[str, str]:
    """Recorded in the manifest so a cache states what produced it (R24)."""
    import importlib.metadata as md

    out = {}
    for pkg in ("torch", "torchvision", "pillow", "numpy", "timm"):
        try:
            out[pkg] = md.version(pkg)
        except Exception:      # noqa: BLE001
            out[pkg] = "unknown"
    return out


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_cache_key(expert_fingerprints: list[str], config_paths: dict[str, Path]) -> tuple[str, dict]:
    """Canonical-JSON cache key (spec [F6]).

    Hashes a sorted JSON object, never pipe-concatenated values: a value
    containing the separator could otherwise forge another key's digest.
    """
    key_object = {
        "feature_schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "probe_version": PROBE_VERSION,
        "transform_config_sha256": _sha256_file(config_paths["transforms"]),
        "probe_config_sha256": _sha256_file(config_paths["probes"]),
        "expert_fingerprints": sorted(expert_fingerprints),
    }
    payload = json.dumps(key_object, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), key_object


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PHASH_RE = re.compile(r"^[0-9a-f]{16}$")


@dataclass(frozen=True)
class Denylist:
    """Sealed-reference hashes. Malformed input is an ERROR, never 'protection'."""

    sha256: frozenset[str]
    phash: frozenset[str]

    def __bool__(self) -> bool:
        return bool(self.sha256 or self.phash)

    @property
    def perceptual_protected(self) -> bool:
        return bool(self.phash)


def load_denylist(path: Path | None) -> Denylist:
    """Parse a sealed-reference denylist STRICTLY (Codex R7a).

    The previous version accepted any token, so a file of junk produced a
    non-empty denylist and stamped `denylist_protected=true` while protecting
    nothing. A malformed entry now aborts: silently degrading contamination
    protection is the one failure this guard exists to prevent.

    Format: one lowercase 64-hex SHA-256 per line; an optional second field
    `phash=<16 hex>` adds perceptual protection. '#' starts a comment.
    """
    if path is None:
        return Denylist(frozenset(), frozenset())
    if not path.exists():
        raise DenylistViolation(f"denylist file not found: {path}")
    sha, ph = set(), set()
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        token = fields[0].lower()
        if not _SHA256_RE.match(token):
            raise DenylistViolation(
                f"{path}:{number}: {fields[0]!r} is not a lowercase 64-hex SHA-256. "
                "Refusing to treat a malformed denylist as protection."
            )
        sha.add(token)
        for extra in fields[1:]:
            if extra.startswith("phash="):
                value = extra.split("=", 1)[1].lower()
                if not _PHASH_RE.match(value):
                    raise DenylistViolation(f"{path}:{number}: bad phash {value!r}")
                ph.add(value)
    if not sha:
        raise DenylistViolation(f"{path} contains no usable hashes")
    return Denylist(frozenset(sha), frozenset(ph))


def _hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def validate_manifest_rows(
    rows: list[dict], denylist: "Denylist", *, verify_bytes: bool = True,
    phash_threshold: int = 6, evaluation_cache: bool = False,
) -> None:
    """Every hard constraint, enforced BEFORE a single forward pass runs.

    Checking after extraction would mean discovering contamination only after
    burning the compute — and worse, after a cache exists that someone might use.
    """
    if not rows:
        raise ValueError("manifest is empty")

    # [F1] All 20 views of a source share original_sha256, so the real rule is
    # one hash -> one source_id. A naive duplicate-hash check would reject
    # every legitimate cache.
    source_by_hash: dict[str, str] = {}
    for row in rows:
        source_id = row["source_id"]
        claimed = row["original_sha256"].lower()
        # R7b: hash the ACTUAL bytes. Checking the manifest's own claim against
        # the denylist would let a mislabelled row walk a sealed image straight
        # into a fitting corpus.
        if verify_bytes:
            path = Path(row["relative_path"])
            if not path.exists():
                raise DenylistViolation(
                    f"{row.get('sample_id')}: file {path} does not exist; cannot verify "
                    "it is not a sealed reference image."
                )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != claimed:
                raise DenylistViolation(
                    f"{row.get('sample_id')}: manifest claims sha256 {claimed[:12]}… but the "
                    f"file hashes to {digest[:12]}…. Refusing to trust a manifest that does "
                    "not describe its own bytes."
                )
            if denylist.perceptual_protected:
                try:
                    import imagehash
                    from PIL import Image

                    observed = str(imagehash.phash(Image.open(path).convert("RGB")))
                    for sealed in denylist.phash:
                        if _hamming(observed, sealed) <= phash_threshold:
                            raise DenylistViolation(
                                f"NEAR-DUPLICATE OF A SEALED REFERENCE IMAGE: "
                                f"{path} (phash {observed} within {phash_threshold} of {sealed})"
                            )
                except DenylistViolation:
                    raise
                except Exception:
                    pass   # unreadable image is caught by the decode path later
        else:
            digest = claimed
        if source_by_hash.setdefault(digest, source_id) != source_id:
            raise ValueError(
                f"sha256 {digest[:12]}… maps to multiple source_ids "
                f"({source_by_hash[digest]!r} and {source_id!r}) — contaminated or "
                "double-counted manifest"
            )
        if digest in denylist.sha256:
            raise DenylistViolation(
                f"SEALED REFERENCE IMAGE IN A FITTING CORPUS: {row.get('relative_path')} "
                f"(sha256 {digest[:12]}…). Aborting the entire job — a skipped row would "
                "hide a contaminated manifest."
            )

        split = row.get("dataset_split", "")
        # `test` rows are barred from a FITTING cache by default -- that guard is
        # what keeps the untouched internal test untouched, and it fired exactly
        # as intended the first time we pointed extraction at that manifest.
        # Evaluating on the test set still needs its features, so the escape
        # hatch is explicit, single-purpose and recorded in the manifest rather
        # than achieved by relabelling rows, which would defeat the guard
        # silently. `train.VALID_SPLITS` remains ("train", "dev"), so the trainer
        # structurally cannot fit on the cache this produces.
        allowed = set(ALLOWED_SPLITS) | ({"test"} if evaluation_cache else set())
        if split not in allowed:
            raise ValueError(
                f"dataset_split {split!r} may not enter a fitting cache; "
                f"allowed: {sorted(allowed)}. Pass evaluation_cache=True only to build a "
                "cache that will be EVALUATED on, never fitted on."
            )
        if split == "test" and not evaluation_cache:
            raise ValueError("refusing to place test rows in a fitting cache")
        blob = json.dumps(row).lower()
        if "val2017" in blob:
            raise ValueError(f"val2017 reference in manifest row {row.get('sample_id')!r}")


def _view_sha256(image) -> str:
    import numpy as np

    return hashlib.sha256(np.array(image, dtype=np.uint8).tobytes()).hexdigest()


def build_row(
    source: dict,
    decoded,
    condition_id: str,
    view,
    experts: list[Expert],
    cache_key: str,
) -> dict:
    """Extract one `(source, condition)` row: experts, probes, quality."""
    view_decoded = replace(decoded, image=view, width=view.width, height=view.height)

    expert_blocks: dict[str, dict] = {}
    probe_blocks: dict[str, dict] = {}
    successes: dict[str, float] = {}
    for expert in experts:
        try:
            out = expert.predict(view_decoded)
        except ExpertInferenceError as exc:
            # A failure block carries NO score fields at all — structurally
            # incapable of contributing a number.
            expert_blocks[expert.expert_id] = {
                "ok": False, "reason_code": exc.reason_code, "message": exc.message,
            }
            continue
        expert_blocks[expert.expert_id] = {
            "ok": True,
            "raw_logit": out.raw_logit,
            "p_fake": out.p_fake,
            "inference_ms": out.inference_ms,
            "embedding_key": None,
            "embedding_dim": None,
            "warnings": list(out.warnings),
        }
        successes[expert.expert_id] = out.p_fake
        # R9: the cache is threshold-FREE, so no threshold-dependent value may be
        # stored in it. `probe_flip` is derivable at consumption from
        # `probe_scores` + the expert's `p_fake` + whatever threshold is in force,
        # so we store the inputs and derive the flip downstream. Passing the
        # sentinel below keeps the helper's signature honest without the value
        # ever reaching a row.
        probes = compute_probe_features(expert, view_decoded, _UNUSED_THRESHOLD,
                                        base_p_fake=out.p_fake)
        probe_blocks[expert.expert_id] = {
            "probe_scores": probes.probe_scores,
            "n_probes_ok": probes.n_probes_ok,
            "probe_mean": probes.probe_mean,
            "probe_std": probes.probe_std,
            "probe_range": probes.probe_range,
            "probe_max_delta": probes.probe_max_delta,
            # probe_flip deliberately ABSENT (R9) — derive it at consumption.
            "probe_failures": probes.probe_failures,
        }

    # [F5] Pairwise so the schema is defined for N>2; no threshold-dependent
    # value lives in a threshold-free cache.
    disagreement = None
    if len(successes) >= 2:
        ids = sorted(successes)
        pairwise = {
            f"{a}|{b}": abs(successes[a] - successes[b])
            for i, a in enumerate(ids) for b in ids[i + 1:]
        }
        values = list(pairwise.values())
        disagreement = {
            "pairwise_abs_p_diff": pairwise,
            "max_abs_p_diff": max(values),
            "mean_abs_p_diff": sum(values) / len(values),
            "n_experts_ok": len(successes),
        }

    quality = compute_quality(view_decoded).to_json_dict()
    quality.pop("schema_version", None)

    return {
        "schema_version": SCHEMA_VERSION,
        "cache_key": cache_key,
        "source_sample_id": source["sample_id"],
        "view_id": f"{source['sample_id']}:{condition_id}",
        "source_id": source["source_id"],
        "relative_path": source["relative_path"],
        "condition_id": condition_id,
        "family": FAMILY_OF[condition_id],
        "label": int(source["label"]),
        "dataset": source["dataset"],
        "dataset_split": source["dataset_split"],
        "source_group": source["source_group"],
        "generator": source.get("generator"),
        "original_sha256": source["original_sha256"],
        "view_rgb_sha256": _view_sha256(view),
        "decoded_phash": source.get("decoded_phash"),
        "license_id": source.get("license_id"),
        "view_warnings": list(decoded.warnings),
        "experts": expert_blocks,
        "probes": probe_blocks,
        "quality": quality,
        "disagreement": disagreement,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def scan_existing_rows(path: Path, cache_key: str) -> tuple[set[str], int]:
    """Resume scan: validate every existing row and TRUNCATE a torn tail (R8).

    Three failures the previous version had:
    - a torn final line was skipped but left in place, so the next append
      concatenated onto the fragment and corrupted that line permanently;
    - rows were trusted by `view_id` alone, never checked against the cache key
      they were written under;
    - the row total was not recoverable, so the manifest reported per-invocation
      counts as if they described the artifact.
    """
    done: set[str] = set()
    if not path.exists():
        return done, 0
    good_bytes = 0
    total = 0
    with path.open("rb") as handle:
        for raw in handle:
            if not raw.endswith(b"\n"):
                break                      # torn tail: stop, do not count it
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                good_bytes += len(raw)
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                break                      # corrupt line: everything after is suspect
            if row.get("cache_key") != cache_key:
                raise CacheKeyMismatch(
                    f"{path} contains a row written under cache key "
                    f"{str(row.get('cache_key'))[:12]}… but this run computes "
                    f"{cache_key[:12]}…. Never mix cache generations."
                )
            if row.get("schema_version") != SCHEMA_VERSION:
                raise CacheKeyMismatch(
                    f"{path} contains schema {row.get('schema_version')!r}, expected "
                    f"{SCHEMA_VERSION!r}."
                )
            done.add(row["view_id"])
            good_bytes += len(raw)
            total += 1
    if good_bytes < path.stat().st_size:
        # Truncate the unusable tail rather than appending after it.
        with path.open("r+b") as handle:
            handle.truncate(good_bytes)
    return done, total


def write_manifest(directory: Path, manifest: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.json"
    fd, tmp = tempfile.mkstemp(dir=str(directory), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def check_cache_key(directory: Path, cache_key: str) -> None:
    """Refuse to append to a cache produced by different code."""
    path = directory / "manifest.json"
    if not path.exists():
        return
    existing = json.loads(path.read_text()).get("cache_key")
    if existing and existing != cache_key:
        raise CacheKeyMismatch(
            f"cache at {directory} was built with key {existing[:12]}… but this run "
            f"computes {cache_key[:12]}…. Pipeline/probe versions, configs or expert "
            "checkpoints changed. Start a new cache directory; never mix generations."
        )


def build_cache(
    manifest_rows: list[dict],
    out_dir: Path,
    experts: list[Expert],
    config_paths: dict[str, Path],
    *,
    threshold: float = 0.5,
    conditions: Iterable[str] = CONDITION_IDS,
    denylist: set[str] | None = None,
    denylist_acknowledged_absent: bool = False,
    progress_every: int = 25,
    evaluation_cache: bool = False,
) -> dict:
    """Extract features for every (source, condition). Returns the manifest."""
    started = datetime.now(timezone.utc)
    denylist = denylist or Denylist(frozenset(), frozenset())
    if not denylist and not denylist_acknowledged_absent:
        # Fail closed. Building an unprotected fitting cache by accident is
        # exactly the mistake the sealed-subset rule exists to prevent.
        raise DenylistViolation(
            "no sealed-reference denylist supplied. Refusing to build a fitting cache "
            "without contamination protection. Supply --denylist, or pass "
            "--acknowledge-no-denylist to stamp this cache as UNPROTECTED (smoke only)."
        )

    validate_manifest_rows(manifest_rows, denylist, evaluation_cache=evaluation_cache)

    fingerprints = [f"{e.expert_id}@{e.model_version}" for e in experts]
    cache_key, key_object = compute_cache_key(fingerprints, config_paths)
    out_dir.mkdir(parents=True, exist_ok=True)
    check_cache_key(out_dir, cache_key)

    rows_path = out_dir / "rows.jsonl"
    # R8: write the manifest BEFORE extracting, so an interrupted first run
    # still leaves a key on disk for the next run to check against.
    write_manifest(out_dir, {"cache_key": cache_key, "key_object": key_object,
                             "schema_version": SCHEMA_VERSION, "status": "in_progress",
                             "started_at": started.isoformat()})
    done, existing_rows = scan_existing_rows(rows_path, cache_key)
    conditions = list(conditions)
    written = decode_failures = 0

    with rows_path.open("a") as handle:
        for i, source in enumerate(manifest_rows, start=1):
            pending = [c for c in conditions if f"{source['sample_id']}:{c}" not in done]
            if not pending:
                continue
            try:
                decoded = decode_image(Path(source["relative_path"]))
            except DecodeError:
                decode_failures += 1
                continue
            from ..pipeline.transforms import apply_transform

            for condition_id in pending:
                view = apply_transform(decoded.image, condition_id, decoded.sha256)
                row = build_row(source, decoded, condition_id, view, experts, cache_key)
                handle.write(json.dumps(row) + "\n")
                written += 1
            handle.flush()
            if progress_every and i % progress_every == 0:
                print(f"  [{i}/{len(manifest_rows)}] sources, {written} rows")

    manifest = {
        "cache_key": cache_key,
        "key_object": key_object,          # stored so the key is re-derivable
        "schema_version": SCHEMA_VERSION,
        "storage_format": "jsonl",
        "storage_note": ("spec names Parquet; pyarrow is not in the lockfile so rows are "
                         "JSONL with an identical schema (recorded deviation)"),
        "created_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "n_sources": len(manifest_rows),
        "n_conditions": len(conditions),
        "rows_total": existing_rows + written,      # describes the ARTIFACT (R8)
        "rows_written_this_invocation": written,
        "decode_failures_this_invocation": decode_failures,
        "experts": fingerprints,
        "role": "evaluation" if evaluation_cache else "fitting",
        "may_not_be_used_for_fitting": bool(evaluation_cache),
        "denylist_size": len(denylist.sha256),
        "denylist_protected": bool(denylist),
        "denylist_perceptual_protected": denylist.perceptual_protected,
        "threshold_free": True,   # R9: no threshold-dependent value is stored
        "command": " ".join(sys.argv),
        "host": platform.node(),
        "device": str(getattr(experts[0], "device", "unknown")) if experts else "none",
        "library_versions": _library_versions(),
        "UNPROTECTED_SMOKE_ONLY": not denylist,
    }
    write_manifest(out_dir, manifest)
    return manifest
