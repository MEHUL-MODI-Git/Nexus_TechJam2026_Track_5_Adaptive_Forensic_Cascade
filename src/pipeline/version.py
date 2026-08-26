"""Single source of truth for pipeline versioning (core spec v2 §0, review note N4).

No other module in the repo may define a version literal. Feature-cache keys,
golden expectations, threshold artifacts and every results JSON embed
PIPELINE_VERSION, so a silent behavior change would poison retained
measurements -- hence the fail-fast assertion in transforms.load_transform_config().
"""

# Bump on ANY change to decode or transform behavior (invalidates caches + goldens).
PIPELINE_VERSION = "0.1.0"

# Bumped in lockstep with PIPELINE_VERSION; kept separate so a future golden-only
# refresh (e.g. new source fixtures, same behavior) can move independently.
GOLDEN_VERSION = "0.1.0"

# Self-probe definitions (doc 03 step 4). Separate from PIPELINE_VERSION because
# probes are UNOFFICIAL diagnostics, not part of the Track-5 transform protocol --
# changing a probe must invalidate cached router features without implying the
# official grid moved. Both keys land in the feature-cache key.
PROBE_VERSION = "0.1.0"
