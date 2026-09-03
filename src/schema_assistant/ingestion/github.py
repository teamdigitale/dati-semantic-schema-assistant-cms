from __future__ import annotations

import subprocess
from pathlib import Path


def clone_repository(repo_url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(destination)],
        check=True,
    )
    return destination


def resolve_assets_dir(repo_dir: Path, assets_path: str) -> Path:
    assets_dir = repo_dir / assets_path if assets_path else repo_dir
    if not assets_dir.exists():
        raise FileNotFoundError(f"Assets path not found: {assets_dir}")
    return assets_dir
