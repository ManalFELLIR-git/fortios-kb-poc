from pathlib import Path
from collections import Counter
import re

from kb_builder.utils import load_yaml


VERSION = "7.6.7"

ROOT = (
    Path("knowledge_base")
    / "fortios"
    / VERSION
)

CANONICAL = ROOT / "canonical"


def num(v):
    if v is None:
        return None

    try:
        return float(
            str(v).replace(",", "")
        )
    except (ValueError, TypeError):
        return None


def source_present(source_presence, source):

    if isinstance(source_presence, dict):

        value = source_presence.get(source)

        return value not in (
            None,
            False,
            "",
            [],
            {},
        )

    if isinstance(source_presence, list):
        return source in source_presence

    return False


def semantic_default(description, default):

    if not description:
        return False

    text = description.lower()

    value = str(default).lower()

    number_words = []

    if value in ("0", "0.0"):
        number_words.append("zero")

    candidates = [
        value,
        *number_words,
    ]

    signals = (
        "default",
        "disable",
        "disabled",
        "auto",
        "automatic",
        "automatically",
        "unlimited",
        "no limit",
        "passthrough",
        "do not",
        "don't",
        "unset",
        "kernel",
        "provided by",
        "recommended setting",
        "random",
    )

    for candidate in candidates:

        if candidate not in text:
            continue

        if any(
            signal in text
            for signal in signals
        ):
            return True

    return False


def find_ranges(description):

    if not description:
        return []

    matches = re.findall(
        r"(?<![\d.])"
        r"(\d[\d,]*)\s*[-–]\s*"
        r"(\d[\d,]*)"
        r"(?![\d.])",
        description,
    )

    output = []

    for low, high in matches:

        try:
            output.append(
                (
                    int(low.replace(",", "")),
                    int(high.replace(",", "")),
                )
            )
        except ValueError:
            pass

    return output


type_signatures = Counter()
field_disagreements = Counter()

expected_type_representation = []
type_review = []

value_disagreements = []

default_normal = []
default_special = []
default_implicit = []

range_special = []
range_parser_complex = []
range_review = []

missing_cli_cli_section = []
missing_cli_no_cli_section = []

terraform_only = []

sections_empty = []


for path in sorted(CANONICAL.glob("*.yaml")):

    data = load_yaml(path) or {}

    section = (
        data.get("id")
        or path.stem
    )

    source_presence = (
        data.get("source_presence")
        or {}
    )

    attrs = (
        data.get("attributes_flat")
        or {}
    )

    if not attrs:
        sections_empty.append(section)

    for attr_name, entry in attrs.items():

        if not isinstance(entry, dict):
            continue

        canonical = (
            entry.get("canonical")
            or {}
        )

        evidence = (
            entry.get("evidence")
            or {}
        )

        field_sources = (
            entry.get("field_sources")
            or {}
        )

        name = (
            f"{section}::{attr_name}"
        )

        # ========================================
        # CLI COVERAGE
        # ========================================

        if "cli_reference" not in evidence:

            if source_present(
                source_presence,
                "cli_reference",
            ):
                missing_cli_cli_section.append(
                    name
                )
            else:
                missing_cli_no_cli_section.append(
                    name
                )

        if set(evidence.keys()) == {
            "terraform"
        }:
            terraform_only.append(name)

        # ========================================
        # EVIDENCE DISAGREEMENTS
        # ========================================

        for field in (
            "type",
            "default",
            "min",
            "max",
        ):

            values = {}

            for source, spec in evidence.items():

                if not isinstance(
                    spec,
                    dict,
                ):
                    continue

                value = spec.get(field)

                if value is not None:
                    values[source] = str(
                        value
                    )

            uniques = set(
                values.values()
            )

            if len(uniques) <= 1:
                continue

            field_disagreements[
                field
            ] += 1

            if field == "type":

                signature = tuple(
                    sorted(uniques)
                )

                type_signatures[
                    signature
                ] += 1

                normalized = {
                    x.lower()
                    for x in uniques
                }

                # Terraform string vs
                # enum from CLI/Ansible
                if (
                    normalized
                    <= {"enum", "string"}
                    and "enum" in normalized
                ):

                    expected_type_representation.append(
                        name
                    )

                # Terraform frequently models
                # nested objects as lists/sets
                elif (
                    normalized
                    <= {
                        "object",
                        "list",
                        "set",
                    }
                ):

                    expected_type_representation.append(
                        name
                    )

                else:

                    type_review.append({
                        "name": name,
                        "values": values,
                        "canonical":
                            canonical.get(
                                "type"
                            ),
                    })

            else:

                value_disagreements.append({
                    "name": name,
                    "field": field,
                    "values": values,
                    "canonical":
                        canonical.get(field),
                    "source":
                        field_sources.get(
                            field
                        ),
                })

        # ========================================
        # DEFAULT VALIDATION
        # ========================================

        default = canonical.get(
            "default"
        )

        minimum = canonical.get(
            "min"
        )

        maximum = canonical.get(
            "max"
        )

        description = canonical.get(
            "description"
        ) or ""

        d = num(default)
        mn = num(minimum)
        mx = num(maximum)

        if (
            d is not None
            and mn is not None
            and mx is not None
        ):

            if mn <= d <= mx:

                default_normal.append(
                    name
                )

            elif semantic_default(
                description,
                default,
            ):

                default_special.append(
                    name
                )

            else:

                # Important:
                # a CLI documented default
                # may be outside the user
                # configurable range.
                default_source = (
                    field_sources.get(
                        "default"
                    )
                )

                range_source = (
                    field_sources.get(
                        "min"
                    ),
                    field_sources.get(
                        "max"
                    ),
                )

                default_implicit.append({
                    "name": name,
                    "default": default,
                    "range":
                        (
                            minimum,
                            maximum,
                        ),
                    "default_source":
                        default_source,
                    "range_source":
                        range_source,
                    "description":
                        description,
                })

        # ========================================
        # RANGE DESCRIPTION CHECK
        # ========================================

        if (
            mn is None
            or mx is None
            or not description
        ):
            continue

        ranges = find_ranges(
            description
        )

        if len(ranges) != 1:
            continue

        desc_min, desc_max = ranges[0]

        if (
            int(mn) == desc_min
            and int(mx) == desc_max
        ):
            continue

        text = description.lower()

        # Arithmetic descriptions such as
        # 3600 * 1000 produce false positives
        # for simple regex range extraction.
        if (
            "*" in text
            or "/" in text
        ):

            range_parser_complex.append({
                "name": name,
                "canonical":
                    (minimum, maximum),
                "description_range":
                    (desc_min, desc_max),
                "text": description,
            })

            continue

        # Canonical range includes a sentinel
        # such as 0 while the documentation
        # states the normal operational range.
        sentinel_signals = (
            "0 =",
            "0 means",
            "zero",
            "0 = unset",
            "0 = default",
            "0 = disable",
            "0 = disabled",
            "0 = no limit",
            "default = 0",
            "set to zero",
        )

        if (
            mn == 0
            and desc_min > 0
            and any(
                x in text
                for x in sentinel_signals
            )
        ):

            range_special.append(
                name
            )

            continue

        range_review.append({
            "name": name,
            "canonical":
                (minimum, maximum),
            "description_range":
                (desc_min, desc_max),
            "min_source":
                field_sources.get(
                    "min"
                ),
            "max_source":
                field_sources.get(
                    "max"
                ),
            "description_source":
                field_sources.get(
                    "description"
                ),
            "text": description,
        })


print()
print("=" * 80)
print(
    "FORTIOS 7.6.7 FINAL TRIAGE"
)
print("=" * 80)

print()
print("=== TYPE DISAGREEMENTS ===")

print(
    "Expected provider representation :",
    len(
        expected_type_representation
    ),
)

print(
    "Type conflicts needing review    :",
    len(type_review),
)

print()
print(
    "Top type signatures:"
)

for sig, count in (
    type_signatures.most_common(20)
):
    print(
        f"{count:6}  {' / '.join(sig)}"
    )


print()
print(
    "=== VALUE DISAGREEMENTS ==="
)

print(
    "Default/min/max disagreements    :",
    len(value_disagreements),
)

for field, count in (
    field_disagreements.most_common()
):
    print(
        f"{field:10} {count}"
    )


print()
print(
    "=== DEFAULTS ==="
)

print(
    "Normal                          :",
    len(default_normal),
)

print(
    "Special semantics confirmed     :",
    len(default_special),
)

print(
    "Implicit/outside range          :",
    len(default_implicit),
)


print()
print(
    "=== RANGE MISMATCHES ==="
)

print(
    "Sentinel/special boundary       :",
    len(range_special),
)

print(
    "Complex description/parser case :",
    len(range_parser_complex),
)

print(
    "Real range review               :",
    len(range_review),
)


print()
print(
    "=== CLI COVERAGE TRIAGE ==="
)

print(
    "Missing CLI but section has CLI :",
    len(missing_cli_cli_section),
)

print(
    "Missing CLI + section no CLI    :",
    len(missing_cli_no_cli_section),
)

print(
    "Terraform-only                  :",
    len(terraform_only),
)

print()
print(
    "=== EMPTY SECTIONS ==="
)

print(
    sections_empty
    if sections_empty
    else "NONE"
)


def show(title, items, limit=25):

    print()
    print(
        f"=== {title} ==="
    )

    if not items:
        print("NONE")
        return

    for item in items[:limit]:
        print(item)

    if len(items) > limit:
        print(
            f"... +{len(items)-limit} more"
        )


show(
    "TRUE TYPE REVIEW",
    type_review,
)

show(
    "VALUE DISAGREEMENTS",
    value_disagreements,
)

show(
    "IMPLICIT DEFAULTS",
    default_implicit,
)

show(
    "REAL RANGE REVIEW",
    range_review,
)

show(
    "MISSING CLI INSIDE CLI SECTION",
    missing_cli_cli_section,
)

show(
    "MISSING CLI / NO CLI SECTION",
    missing_cli_no_cli_section,
)

print()
print("=" * 80)
print("TRIAGE COMPLETE")
print("=" * 80)

