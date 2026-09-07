from pathlib import Path
from collections import Counter
import re

from kb_builder.utils import load_yaml

VERSION = "7.6.7"

ROOT = Path("knowledge_base") / "fortios" / VERSION
CANONICAL_DIR = ROOT / "canonical"


def numeric(value):
    if value is None:
        return None

    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def get_enum(canonical):
    for key in (
        "enum",
        "enums",
        "choices",
        "options",
        "values",
        "allowed_values",
    ):
        value = canonical.get(key)
        if value:
            return value

    return None


def has_special_semantics(description, default):
    if not description:
        return False

    text = description.lower()

    d = re.escape(str(default).lower())

    patterns = [
        rf"\b{d}\b[^.]*\bauto\b",
        rf"\b{d}\b[^.]*\bautomatic\b",
        rf"\b{d}\b[^.]*\bdefault\b",
        rf"\b{d}\b[^.]*\bdisable(?:d)?\b",
        rf"\b{d}\b[^.]*\bunlimited\b",
        rf"\b{d}\b[^.]*\bpassthrough\b",
        rf"\b{d}\b[^.]*\bkernel\b",
        rf"\bif\s+set\s+to\s+{d}\b",
        rf"\b{d}\s*=\s*",
        rf"\bdefault\s*=\s*{d}\b",
    ]

    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in patterns
    )


def description_ranges(description):
    if not description:
        return []

    matches = re.findall(
        r"(?<![\d.])"
        r"(\d[\d,]*)\s*[-–]\s*(\d[\d,]*)"
        r"(?![\d.])",
        description,
    )

    result = []

    for low, high in matches:
        try:
            result.append(
                (
                    int(low.replace(",", "")),
                    int(high.replace(",", "")),
                )
            )
        except ValueError:
            pass

    return result


yaml_files = sorted(CANONICAL_DIR.glob("*.yaml"))

total_sections = 0
total_attributes = 0

sections_without_attributes = []

attrs_without_canonical = []
attrs_without_type = []
attrs_without_description = []
attrs_without_evidence = []

attrs_with_default = 0
attrs_with_range = 0
attrs_with_enum = 0
attrs_with_version_ranges = 0

default_normal = []
default_special = []
default_review = []

description_range_mismatch = []

source_counter = Counter()
source_combo_counter = Counter()
canonical_source_counter = Counter()
field_source_counter = Counter()

attrs_without_cli_reference = []
attrs_only_terraform = []
attrs_only_ansible = []

sections_with_conflicts = []
total_conflict_objects = 0

evidence_field_disagreements = []

FIELDS_TO_COMPARE = (
    "type",
    "default",
    "min",
    "max",
)


for path in yaml_files:

    data = load_yaml(path) or {}

    section = data.get("id") or path.stem

    total_sections += 1

    attrs = data.get("attributes_flat", {}) or {}

    if not attrs:
        sections_without_attributes.append(section)

    conflicts = data.get("conflicts")

    if conflicts:
        sections_with_conflicts.append(section)

        try:
            total_conflict_objects += len(conflicts)
        except TypeError:
            total_conflict_objects += 1

    for attr_name, entry in attrs.items():

        total_attributes += 1

        if not isinstance(entry, dict):
            attrs_without_canonical.append(
                f"{section}::{attr_name}"
            )
            continue

        canonical = entry.get("canonical") or {}
        evidence = entry.get("evidence") or {}
        sources = entry.get("sources") or []
        field_sources = entry.get("field_sources") or {}

        if not canonical:
            attrs_without_canonical.append(
                f"{section}::{attr_name}"
            )
            continue

        canonical_source_counter[
            entry.get("canonical_source", "unknown")
        ] += 1

        normalized_sources = tuple(sorted(sources))

        source_combo_counter[
            normalized_sources
        ] += 1

        for source in sources:
            source_counter[source] += 1

        for field, source in field_sources.items():
            field_source_counter[
                f"{field} <- {source}"
            ] += 1

        if not evidence:
            attrs_without_evidence.append(
                f"{section}::{attr_name}"
            )

        if "cli_reference" not in evidence:
            attrs_without_cli_reference.append(
                f"{section}::{attr_name}"
            )

        if set(evidence.keys()) == {"terraform"}:
            attrs_only_terraform.append(
                f"{section}::{attr_name}"
            )

        if set(evidence.keys()) == {"ansible"}:
            attrs_only_ansible.append(
                f"{section}::{attr_name}"
            )

        attr_type = canonical.get("type")

        if not attr_type:
            attrs_without_type.append(
                f"{section}::{attr_name}"
            )

        description = canonical.get("description")

        if not description:
            attrs_without_description.append(
                f"{section}::{attr_name}"
            )

        default = canonical.get("default")
        minimum = canonical.get("min")
        maximum = canonical.get("max")

        enum = get_enum(canonical)

        if default is not None:
            attrs_with_default += 1

        if minimum is not None or maximum is not None:
            attrs_with_range += 1

        if enum:
            attrs_with_enum += 1

        if canonical.get("version_ranges"):
            attrs_with_version_ranges += 1

        # -------------------------------------------------
        # DEFAULT / RANGE VALIDATION
        # -------------------------------------------------

        d = numeric(default)
        mn = numeric(minimum)
        mx = numeric(maximum)

        if (
            d is not None
            and mn is not None
            and mx is not None
        ):

            item = {
                "section": section,
                "attribute": attr_name,
                "default": default,
                "min": minimum,
                "max": maximum,
                "description": description,
                "default_source": field_sources.get(
                    "default"
                ),
                "min_source": field_sources.get("min"),
                "max_source": field_sources.get("max"),
            }

            if mn <= d <= mx:

                default_normal.append(item)

            elif has_special_semantics(
                description,
                default,
            ):

                default_special.append(item)

            else:

                default_review.append(item)

        # -------------------------------------------------
        # DESCRIPTION RANGE VS STRUCTURED RANGE
        # -------------------------------------------------

        if (
            description
            and mn is not None
            and mx is not None
        ):

            desc_ranges = description_ranges(
                description
            )

            # Only use simple unambiguous descriptions.
            if len(desc_ranges) == 1:

                desc_min, desc_max = desc_ranges[0]

                if (
                    int(mn) != desc_min
                    or int(mx) != desc_max
                ):
                    description_range_mismatch.append({
                        "section": section,
                        "attribute": attr_name,
                        "canonical_min": minimum,
                        "canonical_max": maximum,
                        "description_min": desc_min,
                        "description_max": desc_max,
                        "description": description,
                    })

        # -------------------------------------------------
        # EVIDENCE FIELD DISAGREEMENTS
        # -------------------------------------------------

        for field in FIELDS_TO_COMPARE:

            values = {}

            for source, spec in evidence.items():

                if not isinstance(spec, dict):
                    continue

                value = spec.get(field)

                if value is not None:
                    values[source] = str(value)

            unique_values = set(values.values())

            if len(unique_values) > 1:
                evidence_field_disagreements.append({
                    "section": section,
                    "attribute": attr_name,
                    "field": field,
                    "values": values,
                    "canonical": canonical.get(field),
                    "canonical_source": field_sources.get(
                        field
                    ),
                })


print()
print("=" * 80)
print(f"FINAL KB AUDIT - FortiOS {VERSION}")
print("=" * 80)

print()
print("=== COVERAGE ===")
print("Canonical YAML files       :", len(yaml_files))
print("Sections                   :", total_sections)
print("Attributes                 :", total_attributes)

print()
print("=== CANONICAL METADATA ===")
print("Attributes with type       :", total_attributes - len(attrs_without_type))
print("Attributes with enum       :", attrs_with_enum)
print("Attributes with range      :", attrs_with_range)
print("Attributes with default    :", attrs_with_default)
print("Attributes with versions   :", attrs_with_version_ranges)
print(
    "Attributes with description:",
    total_attributes - len(attrs_without_description),
)

print()
print("=== BASIC QUALITY ===")
print("Sections without attrs     :", len(sections_without_attributes))
print("Attrs without canonical    :", len(attrs_without_canonical))
print("Attrs without evidence     :", len(attrs_without_evidence))
print("Attrs without type         :", len(attrs_without_type))
print("Attrs without description  :", len(attrs_without_description))

print()
print("=== OFFICIAL CLI COVERAGE ===")
print(
    "Attrs with CLI Reference   :",
    total_attributes - len(attrs_without_cli_reference),
)
print(
    "Attrs without CLI Reference:",
    len(attrs_without_cli_reference),
)
print(
    "Terraform-only attrs       :",
    len(attrs_only_terraform),
)
print(
    "Ansible-only attrs         :",
    len(attrs_only_ansible),
)

print()
print("=== DEFAULT VALIDATION ===")
print("Normal defaults            :", len(default_normal))
print("Special semantic defaults  :", len(default_special))
print("Defaults needing review    :", len(default_review))

print()
print("=== RANGE VALIDATION ===")
print(
    "Description/range mismatch :",
    len(description_range_mismatch),
)

print()
print("=== CONFLICTS ===")
print(
    "Sections with conflicts    :",
    len(sections_with_conflicts),
)
print(
    "Conflict objects           :",
    total_conflict_objects,
)
print(
    "Evidence disagreements     :",
    len(evidence_field_disagreements),
)

print()
print("=== SOURCE COVERAGE ===")

for source, count in source_counter.most_common():
    pct = (
        100 * count / total_attributes
        if total_attributes
        else 0
    )

    print(
        f"{source:25} {count:6} "
        f"({pct:6.2f}%)"
    )

print()
print("=== SOURCE COMBINATIONS ===")

for combo, count in source_combo_counter.most_common(15):
    name = " + ".join(combo) if combo else "NONE"
    print(f"{name:50} {count}")

print()
print("=== CANONICAL SOURCE ===")

for source, count in canonical_source_counter.most_common():
    print(f"{source:30} {count}")

print()
print("=== MOST USED FIELD SOURCES ===")

for name, count in field_source_counter.most_common(30):
    print(f"{name:50} {count}")


def show_list(title, values, limit=30):

    print()
    print(f"=== {title} ===")

    if not values:
        print("NONE")
        return

    for item in values[:limit]:
        print(item)

    if len(values) > limit:
        print(f"... +{len(values)-limit} more")


show_list(
    "SECTIONS WITHOUT ATTRIBUTES",
    sections_without_attributes,
)

show_list(
    "ATTRIBUTES WITHOUT CANONICAL",
    attrs_without_canonical,
)

show_list(
    "ATTRIBUTES WITHOUT TYPE",
    attrs_without_type,
)

show_list(
    "ATTRIBUTES WITHOUT DESCRIPTION",
    attrs_without_description,
)

show_list(
    "TERRAFORM-ONLY ATTRIBUTES",
    attrs_only_terraform,
)

print()
print("=== DEFAULTS NEEDING REVIEW ===")

if not default_review:
    print("NONE")
else:
    for item in default_review[:50]:
        print()
        print(
            f'{item["section"]}::'
            f'{item["attribute"]}'
        )
        print(
            " default/min/max:",
            item["default"],
            item["min"],
            item["max"],
        )
        print(
            " sources:",
            item["default_source"],
            item["min_source"],
            item["max_source"],
        )
        print(
            " description:",
            item["description"],
        )

print()
print("=== SPECIAL DEFAULTS CONFIRMED BY DESCRIPTION ===")

if not default_special:
    print("NONE")
else:
    for item in default_special[:50]:
        print(
            f'{item["section"]}::'
            f'{item["attribute"]} '
            f'default={item["default"]} '
            f'range={item["min"]}-{item["max"]}'
        )

print()
print("=== DESCRIPTION / RANGE MISMATCHES ===")

if not description_range_mismatch:
    print("NONE")
else:
    for item in description_range_mismatch[:50]:
        print()
        print(
            f'{item["section"]}::'
            f'{item["attribute"]}'
        )
        print(
            " canonical:",
            item["canonical_min"],
            "-",
            item["canonical_max"],
        )
        print(
            " description:",
            item["description_min"],
            "-",
            item["description_max"],
        )
        print(
            " text:",
            item["description"],
        )

print()
print("=== EVIDENCE FIELD DISAGREEMENTS ===")

if not evidence_field_disagreements:
    print("NONE")
else:
    for item in evidence_field_disagreements[:50]:
        print()
        print(
            f'{item["section"]}::'
            f'{item["attribute"]} '
            f'field={item["field"]}'
        )
        print(
            " evidence:",
            item["values"],
        )
        print(
            " canonical:",
            item["canonical"],
            "source:",
            item["canonical_source"],
        )

print()
print("=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
