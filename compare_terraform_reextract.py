from pathlib import Path
from collections import Counter
import argparse
import yaml


parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--samples", type=int, default=30)
args = parser.parse_args()


ROOT = Path("knowledge_base") / "fortios" / args.version

OLD = ROOT / "raw" / "terraform"

NEW = (
    Path(".work")
    / "terraform_reextract_test"
    / args.version
)


FIELDS = (
    "type",
    "raw_type",
    "min",
    "max",
    "min_length",
    "max_length",
    "optional",
    "required",
    "computed",
    "force_new",
    "default",
    "choices",
)


def flatten_attributes(attrs, prefix=""):

    result = {}

    if not isinstance(attrs, dict):
        return result

    for name, data in attrs.items():

        if not isinstance(data, dict):
            continue

        path = (
            f"{prefix}.{name}"
            if prefix
            else str(name)
        )

        result[path] = {
            key: data[key]
            for key in FIELDS
            if key in data
        }

        children = data.get("children")

        if isinstance(children, dict):

            result.update(
                flatten_attributes(
                    children,
                    path
                )
            )

    return result


def load_directory(directory):

    resources = {}

    for file in sorted(
        directory.glob("*.yaml")
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

        sid = (
            data.get("id")
            or data.get("section_id")
            or file.stem
        )

        resources[sid] = {
            "file": file.name,
            "attributes": flatten_attributes(
                data.get(
                    "attributes",
                    {}
                )
            )
        }

    return resources


old = load_directory(OLD)
new = load_directory(NEW)


old_sections = set(old)
new_sections = set(new)


missing_sections = sorted(
    old_sections - new_sections
)

added_sections = sorted(
    new_sections - old_sections
)


missing_attrs = []
added_attrs = []
changed_fields = []

metadata_added = Counter()
metadata_removed = Counter()

old_attr_total = 0
new_attr_total = 0


for sid in sorted(
    old_sections | new_sections
):

    old_attrs = (
        old.get(
            sid,
            {}
        ).get(
            "attributes",
            {}
        )
    )

    new_attrs = (
        new.get(
            sid,
            {}
        ).get(
            "attributes",
            {}
        )
    )

    old_attr_total += len(
        old_attrs
    )

    new_attr_total += len(
        new_attrs
    )


    old_paths = set(
        old_attrs
    )

    new_paths = set(
        new_attrs
    )


    for attr in sorted(
        old_paths - new_paths
    ):

        missing_attrs.append({
            "section": sid,
            "attribute": attr,
        })


    for attr in sorted(
        new_paths - old_paths
    ):

        added_attrs.append({
            "section": sid,
            "attribute": attr,
        })


    for attr in sorted(
        old_paths & new_paths
    ):

        a = old_attrs[attr]
        b = new_attrs[attr]


        for field in FIELDS:

            old_has = (
                field in a
            )

            new_has = (
                field in b
            )


            if (
                not old_has
                and new_has
            ):

                metadata_added[
                    field
                ] += 1

                continue


            if (
                old_has
                and not new_has
            ):

                metadata_removed[
                    field
                ] += 1

                continue


            if (
                old_has
                and new_has
                and a[field] != b[field]
            ):

                changed_fields.append({
                    "section":
                        sid,

                    "attribute":
                        attr,

                    "field":
                        field,

                    "old":
                        a[field],

                    "new":
                        b[field],
                })


print()
print(
    f"=== TERRAFORM RE-EXTRACTION DIFF {args.version} ==="
)

print()
print("OLD resources :", len(old))
print("NEW resources :", len(new))

print()
print("OLD attributes:", old_attr_total)
print("NEW attributes:", new_attr_total)


print()
print("=== STRUCTURE ===")

print(
    "Missing sections:",
    len(missing_sections)
)

print(
    "Added sections  :",
    len(added_sections)
)

print(
    "Missing attrs   :",
    len(missing_attrs)
)

print(
    "Added attrs     :",
    len(added_attrs)
)


print()
print(
    "=== METADATA ADDED ==="
)

for field, count in (
    metadata_added.most_common()
):

    print(
        f"{field:15} {count}"
    )


print()
print(
    "=== METADATA REMOVED ==="
)

if metadata_removed:

    for field, count in (
        metadata_removed.most_common()
    ):

        print(
            f"{field:15} {count}"
        )

else:

    print("None")


print()
print(
    "=== VALUES CHANGED ==="
)

change_counter = Counter(
    item["field"]
    for item in changed_fields
)

if change_counter:

    for field, count in (
        change_counter.most_common()
    ):

        print(
            f"{field:15} {count}"
        )

else:

    print("None")


if missing_sections:

    print()
    print(
        "=== MISSING SECTIONS SAMPLE ==="
    )

    for x in missing_sections[
        :args.samples
    ]:
        print(x)


if missing_attrs:

    print()
    print(
        "=== MISSING ATTRS SAMPLE ==="
    )

    for x in missing_attrs[
        :args.samples
    ]:
        print(x)


if changed_fields:

    print()
    print(
        "=== CHANGED VALUES SAMPLE ==="
    )

    for x in changed_fields[
        :args.samples
    ]:

        print()
        print(
            x["section"],
            "::",
            x["attribute"]
        )

        print(
            " field:",
            x["field"]
        )

        print(
            " old:",
            x["old"]
        )

        print(
            " new:",
            x["new"]
        )


safe = (
    not missing_sections
    and not missing_attrs
    and not metadata_removed
    and not changed_fields
)


print()
print(
    "=== RESULT ==="
)

if safe:

    print(
        "SAFE_REEXTRACTION = YES"
    )

    print(
        "Only additive metadata detected."
    )

else:

    print(
        "SAFE_REEXTRACTION = REVIEW"
    )

    print(
        "Inspect differences before replacing RAW."
    )

