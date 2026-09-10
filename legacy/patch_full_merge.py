from pathlib import Path
import re
import shutil

path = Path("kb_builder/reconcile.py")

backup = Path("kb_builder/reconcile.py.before_full_merge.bak")
if not backup.exists():
    shutil.copy2(path, backup)

text = path.read_text(encoding="utf-8")


def replace_function(text, name, new_code):
    start = text.find(f"def {name}(")

    if start == -1:
        raise RuntimeError(f"Fonction introuvable : {name}")

    remaining = text[start + 1:]

    match = re.search(
        r"\n(?=def [A-Za-z_][A-Za-z0-9_]*\()",
        remaining
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


helpers = r'''
def choose_type(per):
    """
    Choisit le type canonique sans laisser une représentation CLI
    plate écraser une structure list/dict connue par Ansible/Terraform.
    """

    # Une structure explicite list/dict avec enfants a priorité.
    for src in ["ansible", "terraform", "cli_reference"]:
        spec = per.get(src)

        if not spec:
            continue

        stype = canonical_type(
            spec.get("type") or spec.get("raw_type"),
            spec.get("choices")
        )

        if (
            stype in {"list", "dict"}
            and (
                spec.get("children")
                or spec.get("elements")
            )
        ):
            return stype, src

    # Sinon CLI officielle en premier.
    for src in ["cli_reference", "ansible", "terraform"]:
        spec = per.get(src)

        if not spec:
            continue

        stype = canonical_type(
            spec.get("type") or spec.get("raw_type"),
            spec.get("choices")
        )

        if stype:
            # enum est plus précis que string si des choices existent
            if (
                stype == "string"
                and spec.get("choices")
            ):
                return "enum", src

            return stype, src

    return None, None


def first_value(per, field, order):
    for src in order:
        spec = per.get(src)

        if (
            spec
            and field in spec
            and spec[field] is not None
        ):
            return spec[field], src

    return None, None


def build_canonical(per):
    """
    Fusion champ par champ.

    CLI Reference:
      description/default/range/choices

    Ansible/Terraform:
      structure/list/children/references/version
    """

    canonical = {}
    field_sources = {}

    chosen_type, type_src = choose_type(per)

    if chosen_type:
        canonical["type"] = chosen_type
        field_sources["type"] = type_src

    # Structure : priorité aux sources structurées
    for field in [
        "elements",
        "children",
        "references",
        "required",
        "version_ranges",
    ]:
        value, src = first_value(
            per,
            field,
            ["ansible", "terraform", "cli_reference"]
        )

        if value is not None:
            canonical[field] = value
            field_sources[field] = src

    # Vérité documentaire officielle
    for field in [
        "choices",
        "default",
        "min",
        "max",
        "min_length",
        "max_length",
        "description",
    ]:
        value, src = first_value(
            per,
            field,
            ["cli_reference", "ansible", "terraform"]
        )

        if value is not None:
            canonical[field] = value
            field_sources[field] = src

    # Nom CLI original si disponible
    value, src = first_value(
        per,
        "source_attribute",
        ["cli_reference", "ansible", "terraform"]
    )

    if value is not None:
        canonical["source_attribute"] = value
        field_sources["source_attribute"] = src

    return canonical, field_sources
'''

if "def choose_type(" not in text:
    marker = "def reconcile_section("

    if marker not in text:
        raise RuntimeError("reconcile_section introuvable")

    text = text.replace(
        marker,
        helpers.rstrip() + "\n\n\n" + marker,
        1
    )


new_reconcile = r'''
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
            for src, signature in signatures.items()
            if signature and signature.get("type")
        }

        norm_types = set(types.values())

        # enum/string = différence de représentation acceptable.
        compatible = (
            norm_types <= {"string", "enum"}
            or len(norm_types) <= 1
        )

        if not compatible:
            conflicts.append({
                "attribute": ap,
                "field": "type",
                "values": types,
                "classification": "representation_or_real_conflict",
            })

        canonical, field_sources = build_canonical(per)

        attrs[ap] = {
            "canonical": canonical,
            "canonical_source": "merged",
            "field_sources": field_sources,
            "evidence": per,
            "sources": sorted(per.keys()),
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

text = replace_function(
    text,
    "reconcile_section",
    new_reconcile
)

path.write_text(
    text,
    encoding="utf-8"
)

print("[OK] Fusion champ-par-champ installée")
print("[BACKUP]", backup)
