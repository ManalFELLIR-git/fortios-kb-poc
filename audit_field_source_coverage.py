from pathlib import Path
from collections import Counter, defaultdict
import argparse
import yaml


parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--samples", type=int, default=5)
args = parser.parse_args()


ROOT = (
    Path("knowledge_base")
    / "fortios"
    / args.version
    / "canonical"
)


FIELDS = (
    "default",
    "choices",
    "min",
    "max",
)


SOURCES = (
    "ansible",
    "terraform",
    "cli_reference",
)


counts = {
    field: Counter()
    for field in FIELDS
}

examples = {
    field: defaultdict(list)
    for field in FIELDS
}


def walk(obj, section, path=""):

    if isinstance(obj, dict):

        evidence = obj.get("evidence")

        if isinstance(evidence, dict):

            for field in FIELDS:

                present = []

                values = {}

                for source in SOURCES:

                    source_data = evidence.get(source)

                    if not isinstance(
                        source_data,
                        dict
                    ):
                        continue

                    if (
                        field in source_data
                        and source_data[field]
                        is not None
                    ):

                        present.append(source)

                        values[source] = (
                            source_data[field]
                        )

                if present:

                    key = "+".join(
                        sorted(present)
                    )

                    counts[field][
                        key
                    ] += 1

                    if (
                        len(
                            examples[field][key]
                        )
                        < args.samples
                    ):

                        examples[field][
                            key
                        ].append({
                            "section": section,
                            "attribute": path,
                            "values": values,
                        })


        for key, value in obj.items():

            if key == "evidence":
                continue

            child = (
                f"{path}.{key}"
                if path
                else str(key)
            )

            walk(
                value,
                section,
                child
            )


    elif isinstance(obj, list):

        for i, value in enumerate(obj):

            walk(
                value,
                section,
                f"{path}[{i}]"
            )


for file in ROOT.glob("*.yaml"):

    try:

        data = yaml.safe_load(
            file.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        continue

    if not isinstance(data, dict):
        continue

    section = (
        data.get("id")
        or data.get("section_id")
        or file.stem
    )

    walk(
        data,
        section
    )


print()
print(
    f"=== FIELD SOURCE COVERAGE {args.version} ==="
)


for field in FIELDS:

    print()
    print(
        "=" * 70
    )

    print(
        field.upper()
    )

    total = sum(
        counts[field].values()
    )

    print(
        "facts:",
        total
    )

    for combo, count in (
        counts[field].most_common()
    ):

        print(
            f"{combo:45} {count}"
        )


    print()
    print(
        "MULTI-SOURCE EXAMPLES"
    )

    found = False

    for combo, items in (
        examples[field].items()
    ):

        if "+" not in combo:
            continue

        found = True

        print()
        print(
            combo
        )

        for item in items:

            print(
                " ",
                item
            )

    if not found:

        print(
            "  None"
        )
