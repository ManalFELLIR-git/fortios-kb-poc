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
    default=30
)

args = parser.parse_args()


ROOT = (
    Path("knowledge_base")
    / "fortios"
    / args.version
    / "canonical"
)


def walk(obj, section_id, path=""):

    found = []

    if isinstance(obj, dict):

        # conflit unique
        conflict = obj.get("conflict")

        if isinstance(conflict, dict):

            found.append({
                "section": section_id,
                "path": path,
                "data": conflict,
            })

        # liste de conflits
        conflicts = obj.get("conflicts")

        if isinstance(conflicts, list):

            for item in conflicts:

                if isinstance(item, dict):

                    found.append({
                        "section": section_id,
                        "path": path,
                        "data": item,
                    })

        for key, value in obj.items():

            if key in (
                "conflict",
                "conflicts",
            ):
                continue

            child_path = (
                f"{path}.{key}"
                if path
                else str(key)
            )

            found.extend(
                walk(
                    value,
                    section_id,
                    child_path
                )
            )

    elif isinstance(obj, list):

        for index, value in enumerate(obj):

            found.extend(
                walk(
                    value,
                    section_id,
                    f"{path}[{index}]"
                )
            )

    return found


all_conflicts = []


for file in sorted(
    ROOT.glob("*.yaml")
):

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

    section_id = (
        data.get("id")
        or data.get("section_id")
        or file.stem
    )

    all_conflicts.extend(
        walk(
            data,
            section_id
        )
    )


print()
print(
    f"=== CONFLICT ANALYSIS FortiOS {args.version} ==="
)

print(
    "Detected conflict records:",
    len(all_conflicts)
)


field_counter = Counter()

shape_counter = Counter()

section_counter = Counter()


for item in all_conflicts:

    data = item["data"]

    field = (
        data.get("field")
        or data.get("attribute")
        or data.get("property")
        or "UNKNOWN"
    )

    field_counter[field] += 1

    section_counter[
        item["section"]
    ] += 1

    shape_counter[
        tuple(sorted(data.keys()))
    ] += 1


print()
print(
    "=== TOP CONFLICT FIELDS ==="
)

for field, count in field_counter.most_common(
    30
):

    print(
        f"{field:30} {count}"
    )


print()
print(
    "=== SECTIONS WITH MOST CONFLICTS ==="
)

for section, count in section_counter.most_common(
    20
):

    print(
        f"{section:45} {count}"
    )


print()
print(
    "=== CONFLICT RECORD SHAPES ==="
)

for shape, count in shape_counter.most_common(
    15
):

    print(
        count,
        "=>",
        shape
    )


print()
print(
    "=== FIRST CONFLICT SAMPLES ==="
)

for index, item in enumerate(
    all_conflicts[:args.samples],
    start=1
):

    print()
    print(
        "-" * 75
    )

    print(
        f"[{index}] SECTION:",
        item["section"]
    )

    print(
        "PATH:",
        item["path"]
    )

    print(
        yaml.safe_dump(
            item["data"],
            sort_keys=False,
            allow_unicode=True
        ).strip()
    )


print()
print(
    "=== END ==="
)
