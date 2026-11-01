"""Locate the shared JSON config (reserved handles, feature switches).

Works both when running from the repo root locally and inside a Docker image
where `packages/shared` is copied next to the app. Searches upward from this
file and a few well-known locations.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


def _candidates(filename: str) -> list[Path]:
    here = Path(__file__).resolve()
    found: list[Path] = []
    env_dir = os.getenv("SHARED_CONFIG_DIR")
    if env_dir:
        found.append(Path(env_dir) / filename)
    for parent in [here.parent, *here.parents]:
        found.append(parent / "packages" / "shared" / filename)
    found.append(Path("/app/packages/shared") / filename)
    return found


@lru_cache(maxsize=8)
def load_shared(filename: str) -> dict:
    for path in _candidates(filename):
        if path.is_file():
            with path.open() as fh:
                return json.load(fh)
    raise FileNotFoundError(
        f"Could not locate shared config '{filename}'. "
        f"Set SHARED_CONFIG_DIR or ensure packages/shared/{filename} exists."
    )
