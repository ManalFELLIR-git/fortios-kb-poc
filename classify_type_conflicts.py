from pathlib import Path
from collections import Counter
import argparse
import yaml


COLLECTIONS = {
    "list",
    "set",
    "array",
}

OBJECTS = {
    "object",
    "dict",
    "map",
}

SCALARS = {
    "string",
    "integer",
    "int",
    "number",
    "float",
    "boolean",
    "bool",
}


def normalize_type(value):

    if value is None:
        return None

    value = str(value).lower().strip()

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


def classify(values):

    vals = {
        source: normalize_type(value)
        for source, value in values.items()
        if value is not None
    }

    types = set(vals.values())


    # -------------------------------------------------
    # Toutes les sources d'accord
    # -------------------------------------------------

    if len(types) <= 1:

        return "already_equivalent"


    has_collection = any(
        t in COLLECTIONS
        for t in types
    )

    has_object = any(
        t in OBJECTS
        for t in types
    )

    scalar_types = {
        t
        for t in types
        if t in SCALARS
    }


    # -------------------------------------------------
    # object vs list/set
    #
    # Très fréquent entre Ansible et Terraform :
    # objet structuré vs wrapper collection Terraform
    # -------------------------------------------------

    if (
        has_object
        and has_collection
        and not scalar_types
    ):

        return "object_container_representation"


    # -------------------------------------------------
    # list/set vs scalar
    #
    # Exemple :
    # Ansible=list
    # Terraform=list
    # CLI=string
    #
    # Souvent cardinalité vs type élément.
    # -------------------------------------------------

    if (
        has_collection
        and len(scalar_types) == 1
        and not has_object
    ):

        return "collection_vs_element_type"


    # -------------------------------------------------
    # object + collection + scalar
    # -------------------------------------------------

    if (
        has_object
        and has_collection
        and scalar_types
    ):

        return "structured_representation_complex"


    # -------------------------------------------------
    # list vs set uniquement
    # -------------------------------------------------

    if (
        types
        and types.issubset(
            COLLECTIONS
        )
    ):

        return "collection_kind_only"


    # -------------------------------------------------
    # vrais types scalaires différents
    #
    # ex:
    # integer vs string
    # -------------------------------------------------

    if (
        types
        and types.issubset(
            SCALARS
        )
        and len(types) > 1
    ):

        return "scalar_type_conflict"


    return "needs_review"


def walk(obj, section_id):

    found = []

    if isinstance(obj, dict):

        conflicts = obj.get(
            "conflicts"
        )

        if isinstance(
            conflicts,
            list
        ):

            for conflict in conflicts:

                if (
                    isinstance(conflict, dict)
                    and conflict.get("field")
                    == "type"
                ):

                    found.append({
                        "section":
                            section_id,

                        "attribute":
                            conflict.get(
                                "attribute"
                            ),

                        "values":
                            conflict.get(
                                "values",
                                {}
                            ),
                    })

        conflict = obj.get(
            "conflict"
        )

        if (
            isinstance(conflict, dict)
            and conflict.get("field")
            == "type"
        ):

            found.append({
                "section":
                    section_id,

                "attribute":
                    conflict.get(
                        "attribute"
                    ),

                "values":
                    conflict.get(
                        "values",
                        {}
                    ),
            })

        for key, value in obj.items():

            if key not in (
                "conflict",
                "conflicts",
            ):

                found.extend(
                    walk(
                        value,
                        section_id
                    )
                )

    elif isinstance(obj, list):

        for value in obj:

            found.extend(
                walk(
                    value,
                    section_id
                )
            )

    return found


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
    / "canonical"
)


records = []


for path in ROOT.glob(
    "*.yaml"
):

    try:

        data = yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        continue

    if not isinstance(
        data,
        dict
    ):
        continue

    sid = (
        data.get("id")
        or data.get("section_id")
        or path.stem
    )

    records.extend(
        walk(
            data,
            sid
        )
    )


for record in records:

    record[
        "classification"
    ] = classify(
        record["values"]
    )


counter = Counter(
    record["classification"]
    for record in records
)


print()
print(
    f"=== TYPE CONFLICT CLASSIFICATION {args.version} ==="
)

print(
    "Total:",
    len(records)
)

print()


for name, count in counter.most_common():

    pct = (
        count
        / len(records)
        * 100
        if records
        else 0
    )

    print(
        f"{name:38} "
        f"{count:5} "
        f"({pct:5.1f}%)"
    )


print()
print(
    "=== SAMPLES PER CLASS ==="
)


for classification in counter:

    print()
    print(
        "=" * 75
    )

    print(
        classification.upper()
    )

    shown = 0

    for record in records:

        if (
            record["classification"]
            != classification
        ):
            continue

        print()

        print(
            record["section"],
            "::",
            record["attribute"]
        )

        print(
            record["values"]
        )

        shown += 1

        if shown >= args.samples:
            break


report = {
    "version":
        args.version,

    "total_type_conflicts":
        len(records),

    "classification_counts":
        dict(counter),

    "records":
        records,
}


OUT = (
    Path("knowledge_base")
    / "fortios"
    / args.version
    / "audit"
    / "type_conflict_classification.yaml"
)


OUT.write_text(
    yaml.safe_dump(
        report,
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
