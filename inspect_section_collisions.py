from pathlib import Path
import argparse
import re
import yaml


def norm(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").lower()
    )


def get_section_id(data, path):
    for key in (
        "id",
        "section_id",
        "section",
        "name",
    ):
        value = data.get(key)

        if isinstance(value, str) and value:
            return value

    return path.stem


def get_attributes(data):
    attrs = data.get("attributes", {})

    names = set()

    if isinstance(attrs, dict):
        names.update(
            str(k)
            for k in attrs.keys()
        )

    elif isinstance(attrs, list):
        for item in attrs:

            if isinstance(item, str):
                names.add(item)

            elif isinstance(item, dict):
                for key in (
                    "name",
                    "id",
                    "path",
                    "attribute",
                    "source_attribute",
                ):
                    value = item.get(key)

                    if isinstance(value, str):
                        names.add(value)
                        break

    return names


def find_metadata(data):
    result = {}

    for key in (
        "source_file",
        "source_path",
        "file",
        "path",
        "url",
        "resource",
        "terraform_resource",
        "description",
    ):
        value = data.get(key)

        if value is not None:
            result[key] = value

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

REPORT = (
    ROOT
    / "audit"
    / "section_mapping.yaml"
)

RAW = (
    ROOT
    / "raw"
    / "terraform"
)


report = yaml.safe_load(
    REPORT.read_text(
        encoding="utf-8"
    )
)


# ---------------------------------------------------------
# Charger toutes les sections Terraform RAW
# ---------------------------------------------------------

records = {}

for path in RAW.rglob("*.yaml"):

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

    sid = get_section_id(
        data,
        path
    )

    records.setdefault(
        sid,
        []
    ).append(
        (path, data)
    )


collisions = (
    report
    .get("collisions", {})
    .get("terraform", [])
)


print()
print(
    f"=== TERRAFORM COLLISION ANALYSIS {args.version} ==="
)

print(
    "Collisions:",
    len(collisions)
)


for number, collision in enumerate(
    collisions,
    start=1
):

    canonical = collision[
        "canonical_id"
    ]

    id_a = collision[
        "existing_source_id"
    ]

    id_b = collision[
        "new_source_id"
    ]

    print()
    print(
        "=" * 75
    )

    print(
        f"[{number}] CANONICAL: {canonical}"
    )

    print(
        f"A: {id_a}"
    )

    print(
        f"B: {id_b}"
    )


    def resolve(sid):

        exact = records.get(
            sid,
            []
        )

        if exact:
            return exact[0]

        # fallback normalisé
        wanted = norm(sid)

        matches = []

        for candidate, items in records.items():

            if norm(candidate) == wanted:
                matches.extend(items)

        if len(matches) == 1:
            return matches[0]

        return None


    a = resolve(id_a)
    b = resolve(id_b)


    if a is None:
        print()
        print(
            "[WARN] A introuvable dans RAW"
        )

    if b is None:
        print()
        print(
            "[WARN] B introuvable dans RAW"
        )

    if a is None or b is None:
        continue


    path_a, data_a = a
    path_b, data_b = b

    attrs_a = get_attributes(
        data_a
    )

    attrs_b = get_attributes(
        data_b
    )

    norm_a = {
        norm(x): x
        for x in attrs_a
    }

    norm_b = {
        norm(x): x
        for x in attrs_b
    }

    keys_a = set(
        norm_a
    )

    keys_b = set(
        norm_b
    )

    common = (
        keys_a & keys_b
    )

    only_a = (
        keys_a - keys_b
    )

    only_b = (
        keys_b - keys_a
    )

    union = (
        keys_a | keys_b
    )

    similarity = (
        len(common) / len(union)
        if union
        else 1.0
    )


    print()
    print(
        "--- FILES ---"
    )

    print(
        "A:",
        path_a
    )

    print(
        "B:",
        path_b
    )


    print()
    print(
        "--- METADATA A ---"
    )

    print(
        yaml.safe_dump(
            find_metadata(data_a),
            sort_keys=False,
            allow_unicode=True
        ).strip()
        or "(none)"
    )


    print()
    print(
        "--- METADATA B ---"
    )

    print(
        yaml.safe_dump(
            find_metadata(data_b),
            sort_keys=False,
            allow_unicode=True
        ).strip()
        or "(none)"
    )


    print()
    print(
        "--- ATTRIBUTE COMPARISON ---"
    )

    print(
        "A attributes :",
        len(keys_a)
    )

    print(
        "B attributes :",
        len(keys_b)
    )

    print(
        "Common       :",
        len(common)
    )

    print(
        "Only A       :",
        len(only_a)
    )

    print(
        "Only B       :",
        len(only_b)
    )

    print(
        "Similarity   :",
        f"{similarity:.1%}"
    )


    if only_a:

        print()
        print(
            "First ONLY A:"
        )

        for key in sorted(
            only_a
        )[:20]:

            print(
                "  -",
                norm_a[key]
            )


    if only_b:

        print()
        print(
            "First ONLY B:"
        )

        for key in sorted(
            only_b
        )[:20]:

            print(
                "  -",
                norm_b[key]
            )


print()
print(
    "=== END ==="
)
