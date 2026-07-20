"""Copy human-review bundles to the user's cross-platform Sync directory."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_REVIEW_SYNC_ROOT = Path("~/Sync/Obsidian/gather_insight").expanduser()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_sync_root(override: Path | None = None) -> Path:
    if override is not None:
        return override.expanduser()
    configured = os.environ.get("GATHER_INSIGHT_REVIEW_SYNC_ROOT", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_REVIEW_SYNC_ROOT


def sync_review_bundle(
    *, bundle_slug: str, files: Iterable[tuple[Path, str]], root: Path | None = None, title: str,
) -> Path:
    """Copy an explicit allow-list of review artifacts and write a small manifest."""
    destination = review_sync_root(root) / bundle_slug
    destination.mkdir(parents=True, exist_ok=True)
    manifest_files = []
    for source, relative in files:
        if not source.exists() or not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest_files.append({"path": relative, "sha256": _sha256(target), "size_bytes": target.stat().st_size})
    copied_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest = {"schema_version": "review_sync_bundle_v1", "bundle_slug": bundle_slug, "title": title, "copied_at": copied_at, "file_count": len(manifest_files), "files": sorted(manifest_files, key=lambda row: row["path"])}
    (destination / "sync_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (destination / "README.md").write_text(
        f"# {title}\n\n"
        "This folder is an automatically refreshed human-review copy from GatherInsight.\n\n"
        "- Start with the HTML files under `views/`.\n"
        "- Download completed JSONL decisions from the browser.\n"
        "- Do not edit machine source files in this folder.\n"
        "- `sync_manifest.json` records the copied artifact hashes.\n",
        encoding="utf-8",
    )
    return destination
