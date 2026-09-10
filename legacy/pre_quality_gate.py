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

issues = []
counter = Counter()


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

        field_sources = (
            entry.get("field_sources")
            or {}
        )

        evidence = (
            entry.get("evidence")
            or {}
        )

        sources = set(
            entry.get("sources")
            or []
        )


        # ====================================================
        # 1. ENUM sans choices
        # ====================================================

        if (
            canonical.get("type") == "enum"
            and not canonical.get("choices")
        ):

            counter["enum_without_choices"] += 1

            issues.append({
                "issue":
                    "enum_without_choices",

                "section":
                    sid,

                "attribute":
                    attr_name,

                "sources":
                    sorted(sources),

                "canonical":
                    canonical,
            })


        # ====================================================
        # 2. Terraform-only
        # ====================================================

        if sources == {"terraform"}:

            counter["terraform_only_candidate"] += 1

            issues.append({
                "issue":
                    "terraform_only_candidate",

                "section":
                    sid,

                "attribute":
                    attr_name,

                "canonical":
                    canonical,
            })


        # ====================================================
        # 3. required venant uniquement de Terraform
        # ====================================================

        if (
            canonical.get("required") is True
            and field_sources.get("required")
            == "terraform"
        ):

            counter[
                "terraform_required_not_os_confirmed"
            ] += 1

            issues.append({
                "issue":
                    "terraform_required_not_os_confirmed",

                "section":
                    sid,

                "attribute":
                    attr_name,

                "required":
                    True,

                "evidence":
                    evidence,
            })


        # ====================================================
        # 4. Default numérique hors min/max
        # ====================================================

        default = canonical.get("default")
        mn = canonical.get("min")
        mx = canonical.get("max")

        try:

            if (
                default is not None
                and mn is not None
                and mx is not None
            ):

                d = float(default)
                lo = float(mn)
                hi = float(mx)

                if d < lo or d > hi:

                    counter[
                        "default_outside_range"
                    ] += 1

                    issues.append({
                        "issue":
                            "default_outside_range",

                        "section":
                            sid,

                        "attribute":
                            attr_name,

                        "default":
                            default,

                        "min":
                            mn,

                        "max":
                            mx,
                    })

        except (
            ValueError,
            TypeError
        ):
            pass


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
        dict(counter),

    "total_findings":
        len(issues),

    "findings":
        issues,
}


OUTPUT = (
    ROOT
    / "audit"
    / "pre_quality_gate.yaml"
)

dump_yaml(
    OUTPUT,
    report
)


print()
print(
    f"=== PRE QUALITY GATE {VERSION} ==="
)

print(
    "Canonical sections:",
    report["canonical_sections"]
)

print()

for name, count in counter.most_common():

    print(
        f"{name:40} {count}"
    )

print()
print(
    "Total findings:",
    len(issues)
)

print()
print(
    "[REPORT]",
    OUTPUT
)
