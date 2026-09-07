from __future__ import annotations
from pathlib import Path
import ast, re, yaml
from .versioning import version_in_ranges
from .utils import canonical_type, dump_yaml


def literal_assignment(tree: ast.AST, name: str):
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        return None
    return None


def find_api_path(tree: ast.AST, module_name: str):
    candidates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"get", "set", "post", "put", "delete", "get_mkey"}:
            continue
        vals = []
        for arg in node.args[:2]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                vals.append(arg.value)
        if len(vals) == 2 and vals[0] not in {"http_status", "results"}:
            candidates.append(tuple(vals))
    if candidates:
        # prefer the most common pair
        from collections import Counter
        a, b = Counter(candidates).most_common(1)[0][0]
        return f"{a}.{b}"
    base = module_name.removeprefix("fortios_")
    parts = base.split("_", 1)
    return ".".join(parts) if len(parts) == 2 else base


def filter_schema(node, target_version: str):
    if not isinstance(node, dict):
        return node
    if node.get("v_range") and not version_in_ranges(target_version, node.get("v_range")):
        return None
    out = {}
    for k, v in node.items():
        if k == "children" and isinstance(v, dict):
            kids = {}
            for ck, cv in v.items():
                fv = filter_schema(cv, target_version)
                if fv is not None:
                    kids[ck] = fv
            out[k] = kids
        elif k == "options" and isinstance(v, list):
            opts = []
            for opt in v:
                if isinstance(opt, dict) and opt.get("v_range") and not version_in_ranges(target_version, opt.get("v_range")):
                    continue
                opts.append(opt)
            out[k] = opts
        else:
            out[k] = v
    return out


def documentation_map(doc_string: str | None, module_name: str):
    if not doc_string:
        return {}
    try:
        doc = yaml.safe_load(doc_string) or {}
    except Exception:
        return {}
    root_name = module_name.removeprefix("fortios_")
    options = doc.get("options") or {}
    root = options.get(root_name) or {}
    return root.get("suboptions") or {}


def parse_source_refs(description) -> list[str]:
    if not description:
        return []
    if isinstance(description, list):
        text = " ".join(str(x) for x in description)
    else:
        text = str(description)
    m = re.search(r"\bSource\s+([^.<]+(?:\.[^.<]+)+[^.]*)", text)
    if not m:
        # broader Fortinet generated phrasing: Source system.interface.name system.zone.name
        m = re.search(r"\bSource\s+(.+?)(?:\.|$)", text)
    if not m:
        return []
    chunk = m.group(1)
    refs = re.findall(r"[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+){2,}", chunk)
    return sorted(set(refs))


def normalize_node(node: dict, doc_node: dict | None = None):
    doc_node = doc_node or {}
    options = [o.get("value") for o in (node.get("options") or []) if isinstance(o, dict) and "value" in o]
    raw_type = node.get("type")
    result = {
        "type": canonical_type(raw_type, options),
        "raw_type": raw_type,
    }
    if options:
        result["choices"] = options
    if node.get("required") is not None:
        result["required"] = bool(node.get("required"))
    if node.get("multiple_values"):
        result["multiple_values"] = True
    if node.get("elements"):
        result["elements"] = node.get("elements")
    if node.get("v_range"):
        result["version_ranges"] = node.get("v_range")
    desc = doc_node.get("description") if isinstance(doc_node, dict) else None
    if desc:
        result["description"] = " ".join(desc) if isinstance(desc, list) else str(desc)
        refs = parse_source_refs(desc)
        if refs:
            result["references"] = refs
    if node.get("children"):
        doc_children = doc_node.get("suboptions") if isinstance(doc_node, dict) else {}
        result["children"] = {
            k: normalize_node(v, (doc_children or {}).get(k, {})) for k, v in node["children"].items()
        }
    return {k: v for k, v in result.items() if v not in (None, [], {}, "")}


def extract_module(path: Path, target_version: str):
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text, filename=str(path))
    schema = literal_assignment(tree, "versioned_schema")
    if not isinstance(schema, dict):
        return None
    filtered = filter_schema(schema, target_version)
    if filtered is None:
        return None
    module_name = path.stem
    doc_string = literal_assignment(tree, "DOCUMENTATION")
    docs = documentation_map(doc_string, module_name)
    children = filtered.get("children") or {}
    attrs = {k: normalize_node(v, docs.get(k, {})) for k, v in children.items()}
    return {
        "id": find_api_path(tree, module_name),
        "version": target_version,
        "source_object": module_name,
        "source": {"kind": "ansible", "file": str(path)},
        "root_type": canonical_type(filtered.get("type")),
        "attributes": attrs,
    }


def extract_all(modules_dir: Path, target_version: str, out_dir: Path):
    results = []
    errors = []
    for path in sorted(modules_dir.glob("fortios_*.py")):
        try:
            item = extract_module(path, target_version)
            if item:
                results.append(item)
                dump_yaml(out_dir / f"{item['id']}.yaml", item)
        except Exception as exc:
            errors.append({"file": str(path), "error": repr(exc)})
    return results, errors
