from pathlib import Path
from collections import Counter
from kb_builder.utils import load_yaml, dump_yaml

VERSION = "7.6.7"

ROOT = (
    Path("knowledge_base")
    / "fortios"
    / VERSION
)

CANONICAL = ROOT / "canonical"

summary = Counter()
records = []

unique_affected = set()


def numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


for path in CANONICAL.glob("*.yaml"):

    section = load_yaml(path) or {}

    sid = section.get("id") or path.stem

    attrs = (
        section.get("attributes_flat")
        or {}
    )

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

        sources = set(
            entry.get("sources")
            or []
        )

        resolution = (
            entry.get("resolution")
            or {}
        )

        key = (
            sid,
            attr_name,
        )


        # ====================================================
        # 1. TERRAFORM ONLY
        #
        # On ne dit PAS que c'est faux.
        # On dit simplement : non confirmé comme vérité OS.
        # ====================================================

        if sources == {"terraform"}:

            summary[
                "terraform_only_quarantined"
            ] += 1

            unique_affected.add(key)

            records.append({
                "section":
                    sid,

                "attribute":
                    attr_name,

                "finding":
                    "terraform_only_quarantined",

                "safe_for_cli_generation":
                    False,

                "reason":
                    "not_confirmed_by_exact_fortios_sources",
            })


        # ====================================================
        # 2. REQUIRED TERRAFORM
        # ====================================================

        if (
            canonical.get("required") is True
            and field_sources.get("required")
            == "terraform"
        ):

            summary[
                "provider_required_only"
            ] += 1

            unique_affected.add(key)

            records.append({
                "section":
                    sid,

                "attribute":
                    attr_name,

                "finding":
                    "provider_required_only",

                "os_required":
                    None,

                "terraform_required":
                    True,

                "safe_to_enforce_as_os_required":
                    False,
            })


        # ====================================================
        # 3. ENUM
        # ====================================================

        if (
            canonical.get("type")
            == "enum"
            and not canonical.get("choices")
        ):

            recovered = None
            recovered_source = None

            for source, spec in evidence.items():

                if not isinstance(spec, dict):
                    continue

                choices = spec.get(
                    "choices"
                )

                if choices:

                    recovered = choices
                    recovered_source = source
                    break


            if recovered:

                category = (
                    "enum_choices_recoverable"
                )

            else:

                category = (
                    "enum_choices_need_enrichment"
                )


            summary[category] += 1
            unique_affected.add(key)

            records.append({
                "section":
                    sid,

                "attribute":
                    attr_name,

                "finding":
                    category,

                "recovered_source":
                    recovered_source,

                "recovered_choices":
                    recovered,

                "safe_for_validation":
                    bool(recovered),
            })


        # ====================================================
        # 4. DEFAULT OUTSIDE RANGE
        # ====================================================

        default = numeric(
            canonical.get("default")
        )

        mn = numeric(
            canonical.get("min")
        )

        mx = numeric(
            canonical.get("max")
        )


        if (
            default is not None
            and mn is not None
            and mx is not None
            and (
                default < mn
                or default > mx
            )
        ):

            special_values = (
                entry.get("special_values")
                or []
            )

            special_numeric = {
                numeric(v)
                for v in special_values
                if numeric(v) is not None
            }


            range_resolution = (
                resolution.get("range")
                or {}
            )

            sentinel_resolution = any(
                isinstance(value, dict)
                and value.get("resolution")
                == "sentinel_value_plus_normal_range"

                for value
                in range_resolution.values()
            )


            if (
                default in special_numeric
                or sentinel_resolution
            ):

                category = (
                    "default_outside_range_resolved_sentinel"
                )

                safe = True

            else:

                category = (
                    "default_outside_range_needs_review"
                )

                safe = False


            summary[category] += 1
            unique_affected.add(key)

            records.append({
                "section":
                    sid,

                "attribute":
                    attr_name,

                "finding":
                    category,

                "default":
                    canonical.get("default"),

                "min":
                    canonical.get("min"),

                "max":
                    canonical.get("max"),

                "special_values":
                    special_values,

                "safe_for_generation":
                    safe,
            })


report = {

    "version":
        VERSION,

    "canonical_sections":
        len(
            list(
                CANONICAL.glob("*.yaml")
            )
        ),

    "summary":
        dict(summary),

    "unique_attributes_affected":
        len(unique_affected),

    "records":
        records,
}


OUTPUT = (
    ROOT
    / "audit"
    / "quality_gate_triage.yaml"
)

dump_yaml(
    OUTPUT,
    report
)


print()
print(
    f"=== QUALITY GATE TRIAGE {VERSION} ==="
)

print()

for name, count in summary.most_common():

    print(
        f"{name:50} {count}"
    )

print()

print(
    "Unique attributes affected:",
    len(unique_affected)
)

print()

print(
    "[REPORT]",
    OUTPUT
)
