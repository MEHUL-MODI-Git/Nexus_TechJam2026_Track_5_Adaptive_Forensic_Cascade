"""Keep every Hugging Face download inside the repository (Mehul, 2026-08-27).

By default `huggingface_hub` writes to `~/.cache/huggingface`, so model weights
and dataset shards land outside the project — invisible to `du` on the repo,
absent from any backup of it, and easy to lose track of. This module redirects
that cache to `data/hf_cache/` (git-ignored) instead.

`HF_HOME` is read by `huggingface_hub` when it is first imported, so
`use_repo_local_cache()` must run BEFORE that import. Both download sites call
it at module import time, ahead of their own lazy `huggingface_hub` imports.
An HF_HOME already set in the environment is respected, not overridden.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HF_CACHE_DIR = REPO_ROOT / "data" / "hf_cache"


def use_repo_local_cache() -> Path:
    """Point the HF cache at `data/hf_cache/` unless the caller set HF_HOME."""
    HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR))
    return Path(os.environ["HF_HOME"])
