from pathlib import Path
from collections import Counter
from kb_builder.utils import load_yaml

VERSION = "7.6.7"

ROOT = (
    Path("knowledge_base")
    / "fortios"
    / VERSION
)

triage = load_yaml(
    ROOT
    / "audit"
    / "quality_gate_triage.yaml"
) or {}

records = [
    x
    for x in triage.get("records", [])
    if x.get("finding")
    == "default_outside_range_needs_review"
]

canonical_dir = ROOT / "canonical"

confirmed = []
unknown = []
nonzero = []

sentinel_patterns = (
    "disable",
    "disabled",
    "unlimited",
    "automatic",
    "automatically",
    " auto ",
    "means",
    "no limit",
    "always",
    "system determines",
    "system decide",
)


for item in records:

    section = item["section"]
    attr = item["attribute"]

    default = item.get("default")

    if str(default) not in {"0", "0.0"}:
        nonzero.append(item)
        continue

    path = canonical_dir / f"{section}.yaml"

    if not path.exists():
        unknown.append(item)
        continue

    data = load_yaml(path) or {}

    entry = (
        data.get("attributes_flat", {})
        .get(attr, {})
    )

    evidence = entry.get(
        "evidence",
        {}
    )

    descriptions = []

    for source, spec in evidence.items():

        if not isinstance(spec, dict):
            continue

        desc = spec.get("description")

        if desc:
            descriptions.append(
                f"[{source}] {desc}"
            )

    full_text = " ".join(
        descriptions
    ).lower()

    if any(
        pattern in full_text
        for pattern in sentinel_patterns
    ):

        confirmed.append({
            **item,
            "descriptions": descriptions,
        })

    else:

        unknown.append({
            **item,
            "descriptions": descriptions,
        })


print()
print("=== DEFAULT OUTSIDE RANGE ANALYSIS ===")
print()
print("Total               :", len(records))
print("0 + semantic signal :", len(confirmed))
print("0 still unknown     :", len(unknown))
print("Non-zero default    :", len(nonzero))

print()
print("=== FIRST UNKNOWN ZERO CASES ===")

for item in unknown[:20]:

    print()
    print(
        item["section"],
        "::",
        item["attribute"]
    )

    print(
        "default/min/max:",
        item.get("default"),
        item.get("min"),
        item.get("max"),
    )

    for desc in item.get(
        "descriptions",
        []
    ):
        print(" ", desc)

print()
print("=== NON-ZERO CASES ===")

for item in nonzero[:20]:

    print(
        item["section"],
        "::",
        item["attribute"],
        "default=",
        item.get("default"),
        "range=",
        item.get("min"),
        "-",
        item.get("max"),
    )
