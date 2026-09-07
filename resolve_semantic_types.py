from pathlib import Path
from collections import Counter
import argparse
import yaml


BASE_TYPES = {
    "string",
    "integer",
    "boolean",
    "float",
    "number",
    "object",
    "list",
    "set",
    "enum",
}


def norm_type(value):

    if value is None:
        return None

    value = str(value).strip().lower()

    aliases = {
        "int": "integer",
        "bool": "boolean",
        "dict": "object",
        "array": "list",
    }

    return aliases.get(
        value,
        value
    )


parser = argparse.ArgumentParser()

parser.add_argument(
    "--version",
    required=True
)

args = parser.parse_args()


ROOT = (
    Path("knowledge_base")
    / "fortios"
    / args.version
)

INPUT = (
    ROOT
    / "audit"
    / "type_conflict_classification.yaml"
)

OUTPUT = (
    ROOT
    / "audit"
    / "semantic_type_resolution.yaml"
)


data = yaml.safe_load(
    INPUT.read_text(
        encoding="utf-8"
    )
)

records = data.get(
    "records",
    []
)

resolved = []

counter = Counter()


for record in records:

    values = {
        source: norm_type(value)
        for source, value
        in record.get(
            "values",
            {}
        ).items()
    }

    classification = record.get(
        "classification"
    )

    result = {
        "section":
            record.get("section"),

        "attribute":
            record.get("attribute"),

        "source_types":
            values,
    }


    # =====================================================
    # 1. OBJECT vs TERRAFORM LIST
    # =====================================================

    if (
        classification
        == "object_container_representation"
    ):

        result.update({
            "resolution":
                "compatible_representation",

            "semantic_type": {
                "kind": "object",
                "container_representation":
                    values.get("terraform"),
            },

            "confidence":
                "high",
        })


    # =====================================================
    # 2. COLLECTION vs TYPE ELEMENT
    # =====================================================

    elif (
        classification
        == "collection_vs_element_type"
    ):

        scalar_types = {
            value
            for value in values.values()
            if value not in {
                "list",
                "set",
                "object",
            }
        }

        element_type = (
            next(iter(scalar_types))
            if len(scalar_types) == 1
            else None
        )

        result.update({
            "resolution":
                "compatible_representation",

            "semantic_type": {
                "element_type":
                    element_type,

                "cardinality":
                    "multiple",
            },

            "confidence":
                "high"
                if element_type
                else "medium",
        })


    # =====================================================
    # 3. TYPE SPECIALISE FORTINET
    #
    # string / string / ipv4-address
    # string / string / password
    # string / string / uuid
    # etc.
    # =====================================================

    elif classification == "needs_review":

        cli_type = values.get(
            "cli_reference"
        )

        other_types = {
            value
            for source, value in values.items()
            if source != "cli_reference"
        }

        if (
            cli_type
            and cli_type not in BASE_TYPES
            and other_types
            and other_types == {"string"}
        ):

            semantic = {
                "primitive":
                    "string",

                "format":
                    cli_type,
            }

            if "password" in cli_type:
                semantic[
                    "sensitive"
                ] = True

            result.update({
                "resolution":
                    "compatible_specialization",

                "semantic_type":
                    semantic,

                "authority":
                    "cli_reference",

                "confidence":
                    "high",
            })

        elif (
            cli_type == "enum"
            and "integer"
            in other_types
        ):

            result.update({
                "resolution":
                    "enum_numeric_representation_review",

                "semantic_type": {
                    "kind": "enum"
                },

                "confidence":
                    "needs_review",
            })

        else:

            result.update({
                "resolution":
                    "unresolved",

                "confidence":
                    "needs_review",
            })


    # =====================================================
    # 4. VRAI CONFLIT SCALAIRE
    # =====================================================

    elif (
        classification
        == "scalar_type_conflict"
    ):

        result.update({
            "resolution":
                "scalar_type_conflict",

            "confidence":
                "needs_review",
        })


    else:

        result.update({
            "resolution":
                "unresolved",

            "confidence":
                "needs_review",
        })


    counter[
        result["resolution"]
    ] += 1

    resolved.append(
        result
    )


report = {
    "version":
        args.version,

    "total":
        len(resolved),

    "summary":
        dict(counter),

    "records":
        resolved,
}


OUTPUT.write_text(
    yaml.safe_dump(
        report,
        sort_keys=False,
        allow_unicode=True
    ),
    encoding="utf-8"
)


print()
print(
    f"=== SEMANTIC TYPE RESOLUTION {args.version} ==="
)

print(
    "Total:",
    len(resolved)
)

print()


for name, count in counter.most_common():

    pct = (
        count
        / len(resolved)
        * 100
        if resolved
        else 0
    )

    print(
        f"{name:38}"
        f"{count:5} "
        f"({pct:5.1f}%)"
    )


print()
print(
    "=== ITEMS STILL REQUIRING REVIEW ==="
)


for item in resolved:

    if item["confidence"] != "needs_review":
        continue

    print()
    print(
        item["section"],
        "::",
        item["attribute"]
    )

    print(
        "  types:",
        item["source_types"]
    )

    print(
        "  resolution:",
        item["resolution"]
    )


print()
print(
    "[OK] Report:",
    OUTPUT
)
