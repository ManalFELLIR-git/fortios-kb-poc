from pathlib import Path
from collections import Counter, defaultdict

from kb_builder.utils import load_yaml

VERSION = "7.6.7"

ROOT = (
    Path("knowledge_base")
    / "fortios"
    / VERSION
    / "canonical"
)

# Champs confirmés comme contrôle/provider Terraform,
# et non comme paramètres CLI FortiOS.
PROVIDER_META = {
    "dynamic_sort_subtable",
    "get_all_tables",
    "vdomparam",
    "update_if_exist",
}

missing_cli = []
provider_meta = []
terraform_only_real_candidates = []
multi_source_without_cli = []

leaf_counter = Counter()
source_combo_counter = Counter()
section_counter = Counter()

semantic_string_types = {
    "ipv4-address",
    "ipv4-address-any",
    "ipv6-address",
    "ipv6-prefix",
    "ipv6-network",
    "ipv4-classnet",
    "ipv4-classnet-any",
    "ipv4-classnet-host",
    "ipv4-netmask",
    "mac-address",
    "uuid",
    "password",
    "password-3",
    "password_aes256",
    "datetime",
}

compatible_types = []
remaining_type_review = []


for path in sorted(ROOT.glob("*.yaml")):

    data = load_yaml(path) or {}

    section = data.get("id") or path.stem
    attrs = data.get("attributes_flat", {}) or {}

    for attr_name, entry in attrs.items():

        if not isinstance(entry, dict):
            continue

        evidence = entry.get("evidence") or {}
        canonical = entry.get("canonical") or {}

        name = f"{section}::{attr_name}"
        sources = tuple(sorted(evidence.keys()))

        # ==================================================
        # CLI COVERAGE ANALYSIS
        # ==================================================

        if "cli_reference" not in evidence:

            missing_cli.append(name)

            leaf = attr_name.split(".")[-1]

            leaf_counter[leaf] += 1
            section_counter[section] += 1
            source_combo_counter[sources] += 1

            if leaf in PROVIDER_META:

                provider_meta.append(name)

            elif set(evidence.keys()) == {"terraform"}:

                terraform_only_real_candidates.append(
                    name
                )

            else:

                multi_source_without_cli.append(
                    name
                )

        # ==================================================
        # TYPE COMPATIBILITY ANALYSIS
        # ==================================================

        values = {}

        for source, spec in evidence.items():

            if (
                isinstance(spec, dict)
                and spec.get("type") is not None
            ):
                values[source] = str(
                    spec["type"]
                ).lower()

        unique = set(values.values())

        if len(unique) <= 1:
            continue

        # enum vs Terraform string
        if unique <= {"enum", "string"}:

            compatible_types.append({
                "name": name,
                "reason": "enum_string_representation",
                "values": values,
            })
            continue

        # semantic CLI scalar represented
        # simply as string by another provider
        non_string = unique - {"string"}

        if (
            "string" in unique
            and non_string
            and non_string.issubset(
                semantic_string_types
            )
        ):

            compatible_types.append({
                "name": name,
                "reason": "semantic_string_representation",
                "values": values,
            })
            continue

        # Nested object representation
        if unique <= {
            "object",
            "list",
            "set",
        }:

            compatible_types.append({
                "name": name,
                "reason": "nested_structure_representation",
                "values": values,
            })
            continue

        remaining_type_review.append({
            "name": name,
            "values": values,
            "canonical": canonical.get("type"),
        })


print()
print("=" * 80)
print("FORTIOS 7.6.7 - CLI COVERAGE CLEANUP")
print("=" * 80)

print()
print("=== CLI COVERAGE ===")
print(
    "Total without CLI Reference :",
    len(missing_cli),
)
print(
    "Known provider metadata     :",
    len(provider_meta),
)
print(
    "Terraform-only candidates   :",
    len(terraform_only_real_candidates),
)
print(
    "Multi-source without CLI    :",
    len(multi_source_without_cli),
)

print()
print("=== TYPE NORMALIZATION ===")
print(
    "Compatible representations :",
    len(compatible_types),
)
print(
    "Remaining type review      :",
    len(remaining_type_review),
)

print()
print("=== MOST COMMON MISSING CLI LEAF NAMES ===")

for name, count in leaf_counter.most_common(50):
    marker = (
        " [PROVIDER META]"
        if name in PROVIDER_META
        else ""
    )

    print(
        f"{count:6}  {name}{marker}"
    )

print()
print("=== MISSING CLI SOURCE COMBINATIONS ===")

for combo, count in source_combo_counter.most_common():

    label = (
        " + ".join(combo)
        if combo
        else "NONE"
    )

    print(
        f"{count:6}  {label}"
    )

print()
print("=== SECTIONS WITH MOST MISSING CLI ===")

for section, count in section_counter.most_common(30):

    print(
        f"{count:6}  {section}"
    )


def show(title, values, limit=40):

    print()
    print(f"=== {title} ===")

    if not values:
        print("NONE")
        return

    for value in values[:limit]:
        print(value)

    if len(values) > limit:
        print(
            f"... +{len(values)-limit} more"
        )


show(
    "KNOWN PROVIDER METADATA",
    provider_meta,
)

show(
    "TERRAFORM-ONLY REAL CANDIDATES",
    terraform_only_real_candidates,
)

show(
    "MULTI-SOURCE WITHOUT CLI",
    multi_source_without_cli,
)

show(
    "REMAINING TYPE REVIEW",
    remaining_type_review,
)

print()
print("=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)

