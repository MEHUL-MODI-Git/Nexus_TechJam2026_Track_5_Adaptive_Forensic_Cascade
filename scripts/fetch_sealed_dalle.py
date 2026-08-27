"""Fetch ONLY the organizers' DALL-E Advanced subset from WildFake (2R.2).

WildFake ships DALL-E as one 25.6 GB zip holding 64,495 images. The organizers'
sealed subset is the 8,843 `Advanced/DALLE3` images inside it -- a count this
script verifies rather than assumes. Those entries turn out to be perfectly
contiguous in the archive (measured span/total = 1.000), so a single HTTP range
request over the CDN retrieves 2.84 GB instead of 25.6 GB.

Downloading these images is not using them. They are fingerprinted for the
sealed denylist and never handed to a model, a threshold, or a split.

Two steps, separately resumable:
  --step download   range-fetch the contiguous slice to a local .part file
  --step extract    walk local file headers in that slice and write the images
"""
from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path

API = ("https://www.modelscope.cn/api/v1/datasets/hy2628982280/WildFake/repo"
       "?Revision=master&FilePath=Images/Diffusion_based/DALLE.zip")
WANTED = "Advanced/DALLE3"
EXPECTED_COUNT = 8843


def resolve_cdn_url() -> str:
    """The API endpoint 302s to a time-limited CDN URL. Only the CDN honours
    Range requests, and its auth_key expires, so this is re-resolved on demand
    rather than cached."""
    out = subprocess.run(["curl", "-sI", API], capture_output=True, text=True, check=True).stdout
    match = re.search(r"^[Ll]ocation:\s*(\S+)", out, re.MULTILINE)
    if not match:
        raise RuntimeError("no redirect to a CDN URL; the API response shape changed")
    return match.group(1)


def content_length(url: str) -> int:
    out = subprocess.run(["curl", "-sI", url], capture_output=True, text=True, check=True).stdout
    return int(out.lower().split("content-length:")[1].split()[0])


def fetch_range(url: str, start: int, end: int) -> bytes:
    return subprocess.run(["curl", "-s", "-r", f"{start}-{end}", url],
                          capture_output=True, check=True).stdout


def read_central_directory(url: str, size: int, cache: Path) -> list[tuple[str, int, int, int]]:
    """(name, local_header_offset, compressed_size, uncompressed_size) per entry."""
    if cache.exists():
        raw = cache.read_bytes()
    else:
        tail = fetch_range(url, size - 100_000, size - 1)
        eocd_at = tail.rfind(b"PK\x05\x06")
        _, _, _, _, count, cd_size, cd_offset, _ = struct.unpack(
            "<IHHHHIIH", tail[eocd_at:eocd_at + 22])
        if cd_offset == 0xFFFFFFFF or count == 0xFFFF:      # ZIP64
            z64 = tail.rfind(b"PK\x06\x06")
            rec = tail[z64:z64 + 56]
            cd_size = struct.unpack("<Q", rec[40:48])[0]
            cd_offset = struct.unpack("<Q", rec[48:56])[0]
        raw = fetch_range(url, cd_offset, cd_offset + cd_size - 1)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)

    entries, pos = [], 0
    while pos < len(raw) - 4 and raw[pos:pos + 4] == b"PK\x01\x02":
        (_, _, _, _, _, _, _, _, csize, usize, nlen, elen, clen,
         _, _, _, lho) = struct.unpack("<IHHHHHHIIIHHHHHII", raw[pos:pos + 46])
        name = raw[pos + 46: pos + 46 + nlen].decode("utf-8", "replace")
        extra = raw[pos + 46 + nlen: pos + 46 + nlen + elen]
        if 0xFFFFFFFF in (lho, csize, usize):               # ZIP64 extra field
            ep = 0
            while ep < len(extra) - 4:
                hid, hsz = struct.unpack("<HH", extra[ep:ep + 4])
                if hid == 0x0001:
                    vals, vi = extra[ep + 4: ep + 4 + hsz], 0
                    if usize == 0xFFFFFFFF:
                        usize = struct.unpack("<Q", vals[vi:vi + 8])[0]; vi += 8
                    if csize == 0xFFFFFFFF:
                        csize = struct.unpack("<Q", vals[vi:vi + 8])[0]; vi += 8
                    if lho == 0xFFFFFFFF:
                        lho = struct.unpack("<Q", vals[vi:vi + 8])[0]
                    break
                ep += 4 + hsz
        entries.append((name, lho, csize, usize))
        pos += 46 + nlen + elen + clen
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", choices=("download", "extract"), required=True)
    ap.add_argument("--work", type=Path, default=Path("data/sealed/wildfake_meta"))
    ap.add_argument("--out", type=Path, default=Path("data/sealed/dalle3_advanced"))
    args = ap.parse_args()

    url = resolve_cdn_url()
    size = content_length(url)
    entries = read_central_directory(url, size, args.work / "dalle_central_directory.bin")
    wanted = [e for e in entries if WANTED in e[0] and not e[0].endswith("/")]
    if len(wanted) != EXPECTED_COUNT:
        print(f"REFUSING: found {len(wanted)} '{WANTED}' entries, expected "
              f"{EXPECTED_COUNT}. The archive layout changed; do not guess a subset.",
              file=sys.stderr)
        return 2

    start = min(e[1] for e in wanted)
    # Local header (30 + name + extra) then the compressed bytes. Local extra
    # may exceed the central copy, so pad generously; the slice is parsed by
    # signature, not by arithmetic.
    last = max(wanted, key=lambda e: e[1])
    end = last[1] + 30 + len(last[0]) + 4096 + last[2]
    part = args.work / "dalle_advanced_slice.part"

    if args.step == "download":
        have = part.stat().st_size if part.exists() else 0
        total = end - start + 1
        if have >= total:
            print(f"slice already complete: {have:,} bytes", file=sys.stderr)
            return 0
        print(f"range {start:,}..{end:,}  ({total / 1e9:.2f} GB, resuming at {have:,})",
              file=sys.stderr)
        part.parent.mkdir(parents=True, exist_ok=True)
        # Append, so an interrupted transfer resumes from the byte we reached
        # rather than restarting 2.84 GB.
        command = (f'curl -L --fail --retry 5 --retry-delay 5 '
                   f'-r {start + have}-{end} "{url}" >> "{part}"')
        result = subprocess.run(["bash", "-c", command], check=False)
        final = part.stat().st_size if part.exists() else 0
        print(f"slice now {final:,} / {total:,} bytes", file=sys.stderr)
        return result.returncode

    # ---- extract ----------------------------------------------------------
    blob = part.read_bytes()
    args.out.mkdir(parents=True, exist_ok=True)
    written, skipped = 0, 0
    for name, lho, csize, _usize in wanted:
        pos = lho - start
        if blob[pos:pos + 4] != b"PK\x03\x04":
            skipped += 1
            continue
        _, _, flags, method, _, _, _, _, _, nlen, elen = struct.unpack(
            "<IHHHHHIIIHH", blob[pos:pos + 30])
        data_at = pos + 30 + nlen + elen
        raw = blob[data_at:data_at + csize]
        payload = zlib.decompress(raw, -15) if method == 8 else raw
        # Flatten: the last two path parts keep the batch folder distinct.
        parts = Path(name).parts
        out_name = f"{parts[-2]}__{parts[-1]}" if len(parts) >= 2 else parts[-1]
        (args.out / out_name).write_bytes(payload)
        written += 1
        if written % 1000 == 0:
            print(f"  extracted {written}/{len(wanted)}", file=sys.stderr, flush=True)
    print(f"extracted {written}, skipped {skipped} (flags of last entry: {flags})",
          file=sys.stderr)
    return 0 if written == EXPECTED_COUNT else 1


if __name__ == "__main__":
    raise SystemExit(main())
