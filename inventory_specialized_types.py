from pathlib import Path
from collections import Counter, defaultdict
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
    default=5
)

args = parser.parse_args()


REPORT = (
    Path("knowledge_base")
    / "fortios"
    / args.version
    / "audit"
    / "type_conflict_classification.yaml"
)


data = yaml.safe_load(
    REPORT.read_text(
        encoding="utf-8"
    )
)


records = data.get(
    "records",
    []
)


needs_review = [
    r
    for r in records
    if r.get("classification")
    == "needs_review"
]


cli_types = Counter()

combinations = Counter()

examples = defaultdict(list)


for record in needs_review:

    values = record.get(
        "values",
        {}
    )

    cli_type = values.get(
        "cli_reference"
    )

    if cli_type:
        cli_types[
            str(cli_type)
        ] += 1

    combo = tuple(
        sorted(
            (
                str(source),
                str(value)
            )
            for source, value
            in values.items()
        )
    )

    combinations[
        combo
    ] += 1

    if (
        cli_type
        and len(
            examples[str(cli_type)]
        ) < args.samples
    ):

        examples[
            str(cli_type)
        ].append({
            "section":
                record.get("section"),

            "attribute":
                record.get("attribute"),

            "values":
                values,
        })


print()
print(
    f"=== SPECIALIZED CLI TYPES {args.version} ==="
)

print(
    "Needs review:",
    len(needs_review)
)

print()
print(
    "=== CLI TYPE INVENTORY ==="
)

for cli_type, count in (
    cli_types.most_common()
):

    print(
        f"{cli_type:35} {count}"
    )


print()
print(
    "=== TOP SOURCE COMBINATIONS ==="
)

for combo, count in (
    combinations.most_common(30)
):

    print()
    print(
        count,
        "=>",
        dict(combo)
    )


print()
print(
    "=== EXAMPLES PER CLI TYPE ==="
)

for cli_type, items in examples.items():

    print()
    print(
        "=" * 70
    )

    print(
        cli_type.upper(),
        f"({cli_types[cli_type]})"
    )

    for item in items:

        print(
            " ",
            item["section"],
            "::",
            item["attribute"],
            "=>",
            item["values"]
        )


OUT = (
    Path("knowledge_base")
    / "fortios"
    / args.version
    / "audit"
    / "specialized_cli_types.yaml"
)


OUT.write_text(
    yaml.safe_dump(
        {
            "version":
                args.version,

            "needs_review":
                len(needs_review),

            "cli_type_counts":
                dict(cli_types),

            "examples":
                dict(examples),
        },
        sort_keys=False,
        allow_unicode=True
    ),
    encoding="utf-8"
)


print()
print(
    "[OK] Report:",
    OUT
)
