from pathlib import Path
from collections import defaultdict, Counter
import argparse
import re
import yaml


def norm(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").lower()
    )


def get_attributes(data):
    attrs = data.get("attributes", {})

    result = set()

    if isinstance(attrs, dict):
        result.update(
            str(k)
            for k in attrs
        )

    elif isinstance(attrs, list):

        for item in attrs:

            if isinstance(item, str):
                result.add(item)

            elif isinstance(item, dict):

                for key in (
                    "name",
                    "attribute",
                    "id",
                    "path",
                    "source_attribute",
                ):

                    value = item.get(key)

                    if isinstance(value, str):
                        result.add(value)
                        break

    return result


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

RAW_TF = (
    ROOT
    / "raw"
    / "terraform"
)

INPUT = (
    ROOT
    / "audit"
    / "semantic_type_resolution.yaml"
)

OUTPUT = (
    ROOT
    / "audit"
    / "final_type_resolution.yaml"
)


# --------------------------------------------------------
# Indexer les sections RAW Terraform par clé normalisée
# --------------------------------------------------------

tf_sections = defaultdict(list)

for path in RAW_TF.glob("*.yaml"):

    try:
        data = yaml.safe_load(
            path.read_text(
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
        or path.stem
    )

    tf_sections[
        norm(sid)
    ].append({
        "id": sid,
        "path": str(path),
        "attributes": get_attributes(data),
    })


report = yaml.safe_load(
    INPUT.read_text(
        encoding="utf-8"
    )
)


records = report.get(
    "records",
    []
)


final_records = []

counter = Counter()


for item in records:

    item = dict(item)

    if (
        item.get("confidence")
        != "needs_review"
    ):
        counter[
            item["resolution"]
        ] += 1

        final_records.append(
            item
        )

        continue


    section = item.get(
        "section",
        ""
    )

    attribute = item.get(
        "attribute",
        ""
    )

    wanted_section = norm(
        section
    )

    base_attr = (
        str(attribute)
        .split(".")[-1]
    )

    companion = (
        base_attr
        + "_string"
    )


    candidates = (
        tf_sections.get(
            wanted_section,
            []
        )
    )


    # Si mapping de section avait enlevé
    # -, _, points différemment, la clé norm()
    # retrouve quand même le RAW Terraform.

    detected = []


    for candidate in candidates:

        attrs = {
            str(a)
            for a
            in candidate[
                "attributes"
            ]
        }

        if (
            base_attr in attrs
            and companion in attrs
        ):

            detected.append({
                "terraform_section":
                    candidate["id"],

                "base_attribute":
                    base_attr,

                "string_companion":
                    companion,

                "file":
                    candidate["path"],
            })


    if detected:

        item[
            "resolution"
        ] = (
            "terraform_dual_representation"
        )

        item[
            "confidence"
        ] = "high"

        item[
            "terraform_variants"
        ] = detected

    else:

        item[
            "resolution"
        ] = "unresolved"

        item[
            "confidence"
        ] = "needs_review"


    counter[
        item["resolution"]
    ] += 1

    final_records.append(
        item
    )


final = {
    "version":
        args.version,

    "total":
        len(final_records),

    "summary":
        dict(counter),

    "unresolved":
        sum(
            1
            for x in final_records
            if x.get("confidence")
            == "needs_review"
        ),

    "records":
        final_records,
}


OUTPUT.write_text(
    yaml.safe_dump(
        final,
        sort_keys=False,
        allow_unicode=True
    ),
    encoding="utf-8"
)


print()
print(
    f"=== FINAL TYPE RESOLUTION {args.version} ==="
)

print(
    "Total:",
    len(final_records)
)

print()

for name, count in counter.most_common():

    pct = (
        count
        / len(final_records)
        * 100
    )

    print(
        f"{name:40}"
        f"{count:5} "
        f"({pct:5.1f}%)"
    )


print()
print(
    "Unresolved:",
    final["unresolved"]
)


if final["unresolved"]:

    print()
    print(
        "=== STILL UNRESOLVED ==="
    )

    for item in final_records:

        if (
            item.get("confidence")
            != "needs_review"
        ):
            continue

        print(
            item.get("section"),
            "::",
            item.get("attribute"),
            item.get("source_types")
        )


print()
print(
    "[OK] Report:",
    OUTPUT
)
