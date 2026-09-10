from pathlib import Path
import re
import shutil


def replace_function(text, name, new_code):
    start = text.find(f"def {name}(")

    if start == -1:
        raise RuntimeError(f"Fonction introuvable : {name}")

    rest = text[start:]
    match = re.search(
        r"\n(?=def [A-Za-z_][A-Za-z0-9_]*\()",
        rest[1:]
    )

    if match:
        end = start + 1 + match.start()
        return (
            text[:start]
            + new_code.rstrip()
            + "\n\n"
            + text[end + 1:]
        )

    return text[:start] + new_code.rstrip() + "\n"


def backup(path):
    backup_path = Path(str(path) + ".bak")

    if not backup_path.exists():
        shutil.copy2(path, backup_path)

    print(f"[BACKUP] {backup_path}")


# =========================================================
# 1. CORRECTION TERRAFORM
# =========================================================

tf_path = Path("kb_builder/terraform_extractor.py")
backup(tf_path)

tf = tf_path.read_text(
    encoding="utf-8"
)

direct_level_code = r'''
def direct_level_text(body: str) -> str:
    """
    Garde uniquement les propriétés du niveau courant.

    Cela empêche un parent Terraform de récupérer
    les contraintes IntBetween/StringLenBetween
    appartenant à ses enfants.
    """
    chars = list(body)

    depth = 0
    in_string = False
    escaped = False

    for i, char in enumerate(body):

        if in_string:

            if escaped:
                escaped = False

            elif char == "\\":
                escaped = True

            elif char == '"':
                in_string = False

            if depth > 0:
                chars[i] = " "

            continue

        if char == '"':
            in_string = True

            if depth > 0:
                chars[i] = " "

        elif char == "{":
            depth += 1
            chars[i] = " "

        elif char == "}":
            chars[i] = " "
            depth = max(0, depth - 1)

        elif depth > 0:
            chars[i] = " "

    return "".join(chars)
'''

if "def direct_level_text(" in tf:
    tf = replace_function(
        tf,
        "direct_level_text",
        direct_level_code
    )
else:
    marker = "def extract_validation(body: str):"

    if marker not in tf:
        raise RuntimeError(
            "extract_validation introuvable"
        )

    tf = tf.replace(
        marker,
        direct_level_code.rstrip()
        + "\n\n\n"
        + marker,
        1
    )


parse_schema_code = r'''
def parse_schema_entry(body: str):
    # Lire les propriétés uniquement au niveau courant.
    direct = direct_level_text(body)

    tm = re.search(
        r"\bType\s*:\s*schema\.(Type\w+)",
        direct
    )

    raw_type = tm.group(1) if tm else None

    out = {
        "type": canonical_type(raw_type),
        "raw_type": raw_type,
    }

    for key, go_key in [
        ("required", "Required"),
        ("optional", "Optional"),
        ("computed", "Computed"),
        ("force_new", "ForceNew"),
    ]:

        m = re.search(
            rf"\b{go_key}\s*:\s*(true|false)",
            direct
        )

        if m:
            out[key] = (
                m.group(1) == "true"
            )

    # IMPORTANT :
    # validation du parent uniquement.
    out.update(
        extract_validation(direct)
    )

    # Les enfants sont parsés séparément.
    nested = find_schema_map(body)

    if nested:
        out["children"] = {
            name: parse_schema_entry(child_body)
            for name, child_body
            in top_level_entries(nested)
        }

    return {
        k: v
        for k, v in out.items()
        if v is not None
    }
'''

tf = replace_function(
    tf,
    "parse_schema_entry",
    parse_schema_code
)

tf_path.write_text(
    tf,
    encoding="utf-8"
)

print(
    "[OK] terraform_extractor.py corrigé"
)


# =========================================================
# 2. NORMALISATION CLI '-' VS '_'
# =========================================================

rec_path = Path(
    "kb_builder/reconcile.py"
)

backup(rec_path)

rec = rec_path.read_text(
    encoding="utf-8"
)

normalize_code = r'''
def normalize_attr_path(path: str) -> str:
    """
    FortiOS CLI:
        duplication-max-num

    Ansible / Terraform:
        duplication_max_num

    Forme canonique interne:
        duplication_max_num
    """
    return ".".join(
        part.replace("-", "_")
        for part in path.split(".")
    )
'''

if "def normalize_attr_path(" in rec:

    rec = replace_function(
        rec,
        "normalize_attr_path",
        normalize_code
    )

else:

    marker = "def attr_map(section):"

    if marker not in rec:
        raise RuntimeError(
            "attr_map introuvable"
        )

    rec = rec.replace(
        marker,
        normalize_code.rstrip()
        + "\n\n\n"
        + marker,
        1
    )


attr_map_code = r'''
def attr_map(section):
    if not section:
        return {}

    result = {}

    for path, spec in flatten_attributes(section):

        canonical_path = normalize_attr_path(
            path
        )

        spec = dict(spec or {})

        # Conserver le nom original.
        spec.setdefault(
            "source_attribute",
            path
        )

        result[canonical_path] = spec

    return result
'''

rec = replace_function(
    rec,
    "attr_map",
    attr_map_code
)


reconcile_section_code = r'''
def reconcile_section(sid, a, t, c, version):
    maps = {
        "ansible": attr_map(a),
        "terraform": attr_map(t),
        "cli_reference": attr_map(c),
    }

    all_attrs = sorted(
        set().union(
            *(m.keys() for m in maps.values())
        )
    )

    attrs = {}
    conflicts = []

    for ap in all_attrs:

        per = {
            src: m.get(ap)
            for src, m in maps.items()
            if m.get(ap) is not None
        }

        signatures = {
            src: sig(value)
            for src, value in per.items()
        }

        types = {
            src: signature["type"]
            for src, signature
            in signatures.items()
            if (
                signature
                and signature.get("type")
            )
        }

        norm_types = set(
            types.values()
        )

        # string vs enum n'est pas forcément
        # un vrai conflit de type.
        compatible = (
            norm_types <= {
                "string",
                "enum"
            }
            or len(norm_types) <= 1
        )

        if not compatible:

            conflicts.append({
                "attribute": ap,
                "field": "type",
                "values": types,
            })

        # Ordre d'autorité.
        if "cli_reference" in per:
            canonical_source = (
                "cli_reference"
            )

        elif "ansible" in per:
            canonical_source = "ansible"

        else:
            canonical_source = (
                "terraform"
            )

        pref = per[
            canonical_source
        ]

        attrs[ap] = {
            "canonical": pref,
            "canonical_source":
                canonical_source,
            "evidence": per,
            "sources": sorted(
                per.keys()
            ),
        }

    return {
        "id": sid,
        "version": version,

        "source_presence": {
            "ansible": bool(a),
            "terraform": bool(t),
            "cli_reference": bool(c),
        },

        "attributes_flat": attrs,

        "conflicts": conflicts,
    }
'''

rec = replace_function(
    rec,
    "reconcile_section",
    reconcile_section_code
)

rec_path.write_text(
    rec,
    encoding="utf-8"
)

print(
    "[OK] reconcile.py corrigé"
)


# =========================================================
# 3. AFFICHAGE PROGRESSION DOCS
# =========================================================

docs_path = Path(
    "kb_builder/fortinet_docs.py"
)

backup(docs_path)

docs = docs_path.read_text(
    encoding="utf-8"
)

crawl_code = r'''
def crawl(seed: str, allowed_prefixes: list[str], max_pages: int, delay: float=0.15):
    q = [seed]
    seen = set()
    pages = []

    while q and (
        max_pages <= 0
        or len(seen) < max_pages
    ):

        url = q.pop(0)

        if url in seen:
            continue

        seen.add(url)

        limit = (
            "ALL"
            if max_pages <= 0
            else str(max_pages)
        )

        print(
            f"[DOCS] "
            f"{len(seen)}/{limit} "
            f"{url}",
            flush=True
        )

        try:
            html = fetch(url)

        except Exception as exc:

            print(
                f"[DOCS][ERROR] "
                f"{url} : {exc}",
                flush=True
            )

            pages.append(
                (
                    url,
                    None,
                    repr(exc)
                )
            )

            continue

        pages.append(
            (
                url,
                html,
                None
            )
        )

        for link in discover_links(
            html,
            url,
            allowed_prefixes
        ):

            if (
                link not in seen
                and link not in q
            ):
                q.append(link)

        if delay:
            time.sleep(delay)

    return pages
'''

docs = replace_function(
    docs,
    "crawl",
    crawl_code
)

docs_path.write_text(
    docs,
    encoding="utf-8"
)

print(
    "[OK] fortinet_docs.py corrigé"
)

print()
print(
    "=== PATCH TERMINÉ ==="
)
