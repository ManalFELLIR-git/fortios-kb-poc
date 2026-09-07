from __future__ import annotations
from packaging.version import Version


def clean_version(v: str) -> str:
    v = str(v or "").strip()
    if v.lower().startswith("v"):
        v = v[1:]
    return v


def version_in_ranges(target: str, ranges) -> bool:
    """Fortinet Ansible uses ranges like [["v7.6.1", ""], ["v7.4.3", "v7.6.7"]]."""
    if not ranges:
        return True
    t = Version(clean_version(target))
    for item in ranges:
        if not item:
            continue
        start = Version(clean_version(item[0])) if len(item) > 0 and item[0] else None
        end = Version(clean_version(item[1])) if len(item) > 1 and item[1] else None
        if (start is None or t >= start) and (end is None or t <= end):
            return True
    return False
