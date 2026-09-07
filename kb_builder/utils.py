from __future__ import annotations
from pathlib import Path
import json, yaml, re


def dump_yaml(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def safe_name(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", s.strip())


def flatten_attributes(node: dict, prefix=""):
    out = []
    attrs = node.get("attributes") or {}
    for name, spec in attrs.items():
        p = f"{prefix}.{name}" if prefix else name
        out.append((p, spec))
        if isinstance(spec, dict) and spec.get("children"):
            out.extend(flatten_attributes({"attributes": spec["children"]}, p))
    return out


def canonical_type(raw: str | None, choices=None) -> str | None:
    if not raw:
        return None
    r = str(raw).lower().strip()
    if choices:
        return "enum"
    mapping = {
        "str": "string", "string": "string", "var-string": "string", "user": "string",
        "int": "integer", "integer": "integer", "float": "number", "number": "number",
        "bool": "boolean", "boolean": "boolean", "dict": "object", "object": "object",
        "list": "list", "set": "list", "option": "enum",
        "typestring": "string", "typeint": "integer", "typebool": "boolean",
        "typelist": "list", "typeset": "list", "typefloat": "number", "typemap": "object",
    }
    return mapping.get(r, r)
