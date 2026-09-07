from __future__ import annotations
from pathlib import Path
import subprocess


def _run(cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)


def clone_pinned(url: str, tag: str, dest: Path):
    if dest.exists() and (dest / ".git").exists():
        _run(["git", "fetch", "--tags", "--force"], cwd=dest)
        _run(["git", "checkout", "--force", tag], cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--depth", "1", "--branch", tag, url, str(dest)])
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=dest, text=True).strip()
    return sha
