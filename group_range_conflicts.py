from pathlib import Path
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation
import argparse
import yaml


parser = argparse.ArgumentParser()

parser.add_argument(
    "--version",
    required=True
)

parser.add_argument(
    "--samples",
    type=int,
    default=10
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
    / "range_conflict_triage.yaml"
)

OUTPUT = (
    ROOT
    / "audit"
    / "range_conflict_groups.yaml"
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


def normalize_number(value):

    try:

        d = Decimal(
            str(value)
        )

        return str(
            d.normalize()
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError
    ):

        return str(value)


# ============================================================
# 1. Groupement exact par :
#
# field + terraform value + cli value
# ============================================================

groups = defaultdict(list)


for item in records:

    values = item.get(
        "raw_values",
        {}
    )

    tf = normalize_number(
        values.get("terraform")
    )

    cli = normalize_number(
        values.get("cli_reference")
    )

    key = (
        item.get("field"),
        tf,
        cli,
    )

    groups[key].append(
        item
    )


sorted_groups = sorted(
    groups.items(),
    key=lambda x: (
        -len(x[1]),
        str(x[0])
    )
)


# ============================================================
# 2. Groupement également par nom d'attribut final
# ============================================================

attribute_groups = defaultdict(list)


for item in records:

    attr = str(
        item.get(
            "attribute_path",
            ""
        )
    )

    basename = (
        attr.split(".")[-1]
    )

    attribute_groups[
        basename
    ].append(
        item
    )


repeated_attributes = {

    name: items

    for name, items
    in attribute_groups.items()

    if len(items) > 1
}


# ============================================================
# 3. Construire rapport
# ============================================================

report_groups = []


for index, (key, items) in enumerate(
    sorted_groups,
    start=1
):

    field, tf, cli = key

    triage_counts = Counter(
        x.get(
            "triage_class"
        )
        for x in items
    )

    report_groups.append({

        "group_id":
            index,

        "count":
            len(items),

        "field":
            field,

        "terraform":
            tf,

        "cli_reference":
            cli,

        "triage_classes":
            dict(
                triage_counts
            ),

        "items": [
            {
                "section":
                    x.get("section"),

                "attribute":
                    x.get(
                        "attribute_path"
                    ),

                "triage_class":
                    x.get(
                        "triage_class"
                    ),
            }

            for x in items
        ],
    })


final = {

    "version":
        args.version,

    "total_conflicts":
        len(records),

    "unique_value_signatures":
        len(groups),

    "repeated_value_signatures":
        sum(
            1
            for items
            in groups.values()
            if len(items) > 1
        ),

    "repeated_attribute_names":
        len(
            repeated_attributes
        ),

    "groups":
        report_groups,

    "attribute_groups": {

        name: [
            {
                "section":
                    x.get("section"),

                "field":
                    x.get("field"),

                "values":
                    x.get(
                        "raw_values"
                    ),
            }

            for x in items
        ]

        for name, items
        in sorted(
            repeated_attributes.items()
        )
    },
}


OUTPUT.write_text(
    yaml.safe_dump(
        final,
        sort_keys=False,
        allow_unicode=True
    ),
    encoding="utf-8"
)


# ============================================================
# PRINT
# ============================================================

print()
print(
    f"=== RANGE CONFLICT GROUPING {args.version} ==="
)

print(
    "Total conflicts             :",
    len(records)
)

print(
    "Unique value signatures     :",
    len(groups)
)

print(
    "Repeated value signatures   :",
    final[
        "repeated_value_signatures"
    ]
)

print(
    "Repeated attribute names    :",
    len(
        repeated_attributes
    )
)


print()
print(
    "=== LARGEST VALUE GROUPS ==="
)


for index, (key, items) in enumerate(
    sorted_groups[
        :args.samples
    ],
    start=1
):

    field, tf, cli = key

    print()
    print(
        "-" * 75
    )

    print(
        f"GROUP {index}"
    )

    print(
        "count:",
        len(items)
    )

    print(
        "field:",
        field
    )

    print(
        "terraform:",
        tf
    )

    print(
        "cli:",
        cli
    )

    print(
        "classes:",
        dict(
            Counter(
                x.get(
                    "triage_class"
                )
                for x in items
            )
        )
    )

    for item in items[
        :10
    ]:

        print(
            " ",
            item.get("section"),
            "::",
            item.get(
                "attribute_path"
            )
        )


print()
print(
    "=== REPEATED ATTRIBUTE NAMES ==="
)


shown = 0


for name, items in sorted(
    repeated_attributes.items(),
    key=lambda x: -len(x[1])
):

    if shown >= args.samples:
        break

    shown += 1

    print()
    print(
        name,
        "=>",
        len(items)
    )

    for item in items[
        :10
    ]:

        print(
            " ",
            item.get("section"),
            item.get("field"),
            item.get(
                "raw_values"
            )
        )


print()
print(
    "[OK] Report:",
    OUTPUT
)
