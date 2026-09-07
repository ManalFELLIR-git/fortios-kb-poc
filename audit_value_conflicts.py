from pathlib import Path
from collections import Counter
from decimal import Decimal, InvalidOperation
import argparse
import yaml


SOURCES = (
    "ansible",
    "terraform",
    "cli_reference",
)


FIELD_ALIASES = {

    "default": (
        "default",
    ),

    "min": (
        "min",
        "minimum",
        "min_value",
    ),

    "max": (
        "max",
        "maximum",
        "max_value",
    ),

    "choices": (
        "choices",
        "valid_values",
        "enum_values",
    ),
}


def extract_field(data, logical_field):

    if not isinstance(data, dict):
        return None

    for key in FIELD_ALIASES[logical_field]:

        if key in data:

            value = data[key]

            if value is not None:
                return value

    return None


def normalize_scalar(value):

    if value is None:
        return None

    if isinstance(value, bool):

        return (
            "true"
            if value
            else "false"
        )

    if isinstance(value, (int, float)):

        try:

            return str(
                Decimal(
                    str(value)
                ).normalize()
            )

        except Exception:

            return str(value)


    text = str(value).strip()


    # Normaliser nombres représentés en string
    try:

        number = Decimal(text)

        return str(
            number.normalize()
        )

    except InvalidOperation:
        pass


    # Normaliser booléens simples
    low = text.lower()

    bool_aliases = {
        "true": "true",
        "yes": "true",
        "false": "false",
        "no": "false",
    }

    if low in bool_aliases:
        return bool_aliases[low]


    return text


def normalize_choices(value):

    if value is None:
        return None


    if isinstance(value, dict):

        values = list(
            value.keys()
        )


    elif isinstance(
        value,
        (list, tuple, set)
    ):

        values = []

        for item in value:

            if isinstance(item, dict):

                selected = None

                for key in (
                    "value",
                    "name",
                    "id",
                ):

                    if key in item:

                        selected = item[key]
                        break

                if selected is not None:
                    values.append(
                        selected
                    )

            else:

                values.append(
                    item
                )


    else:

        # certains extracteurs peuvent
        # produire "enable, disable"
        text = str(value).strip()

        if "," in text:

            values = [
                x.strip()
                for x in text.split(",")
                if x.strip()
            ]

        else:

            values = [value]


    return sorted(
        {
            normalize_scalar(v)
            for v in values
            if v is not None
        }
    )


def normalize_value(field, value):

    if field == "choices":

        return normalize_choices(
            value
        )

    return normalize_scalar(
        value
    )


def compare_values(field, values):

    normalized = {
        source:
            normalize_value(
                field,
                value
            )
        for source, value
        in values.items()
    }


    unique = []

    for value in normalized.values():

        if value not in unique:
            unique.append(value)


    if len(unique) == 1:

        return (
            "match",
            normalized
        )


    # -------------------------------------------
    # Cas particulier choices :
    # une source peut avoir un sous-ensemble
    # d'une autre.
    # -------------------------------------------

    if field == "choices":

        sets = [
            set(v)
            for v in normalized.values()
            if isinstance(v, list)
        ]

        if len(sets) >= 2:

            subset_relation = True

            for i, a in enumerate(sets):

                for j, b in enumerate(sets):

                    if i == j:
                        continue

                    if not (
                        a.issubset(b)
                        or b.issubset(a)
                    ):

                        subset_relation = False
                        break

                if not subset_relation:
                    break


            if subset_relation:

                return (
                    "subset_difference",
                    normalized
                )


    return (
        "conflict",
        normalized
    )


def classify_conflict(
    status,
    values
):

    if status == "match":
        return "match"

    if status == "subset_difference":

        if "cli_reference" in values:

            return (
                "choices_subset_with_official"
            )

        return (
            "choices_subset_secondary"
        )


    if "cli_reference" in values:

        return (
            "official_disagreement"
        )

    return (
        "secondary_disagreement"
    )


def walk(
    obj,
    section,
    path=""
):

    records = []


    if isinstance(obj, dict):

        evidence = obj.get(
            "evidence"
        )


        if isinstance(
            evidence,
            dict
        ):

            source_data = {

                source:
                    evidence.get(source)

                for source in SOURCES

                if isinstance(
                    evidence.get(source),
                    dict
                )
            }


            for field in FIELD_ALIASES:

                values = {}

                for source, data in (
                    source_data.items()
                ):

                    value = extract_field(
                        data,
                        field
                    )

                    if value is not None:

                        values[
                            source
                        ] = value


                # Il faut au moins 2 sources
                # donnant réellement ce champ.
                if len(values) < 2:
                    continue


                status, normalized = (
                    compare_values(
                        field,
                        values
                    )
                )


                classification = (
                    classify_conflict(
                        status,
                        values
                    )
                )


                records.append({

                    "section":
                        section,

                    "attribute_path":
                        path,

                    "field":
                        field,

                    "status":
                        status,

                    "classification":
                        classification,

                    "raw_values":
                        values,

                    "normalized_values":
                        normalized,
                })


        for key, value in obj.items():

            if key == "evidence":
                continue

            child_path = (
                f"{path}.{key}"
                if path
                else str(key)
            )

            records.extend(
                walk(
                    value,
                    section,
                    child_path
                )
            )


    elif isinstance(obj, list):

        for index, item in enumerate(
            obj
        ):

            records.extend(
                walk(
                    item,
                    section,
                    f"{path}[{index}]"
                )
            )


    return records


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
)

CANONICAL = (
    ROOT
    / "canonical"
)

OUTPUT = (
    ROOT
    / "audit"
    / "value_conflict_audit.yaml"
)


records = []


for file in sorted(
    CANONICAL.glob("*.yaml")
):

    try:

        data = yaml.safe_load(
            file.read_text(
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


    section = (
        data.get("id")
        or data.get("section_id")
        or file.stem
    )


    records.extend(
        walk(
            data,
            section
        )
    )


status_counter = Counter(
    r["status"]
    for r in records
)

field_counter = Counter(
    r["field"]
    for r in records
)

classification_counter = Counter(
    r["classification"]
    for r in records
)


problem_records = [
    r
    for r in records
    if r["status"] != "match"
]


report = {

    "version":
        args.version,

    "comparable_facts":
        len(records),

    "matches":
        status_counter.get(
            "match",
            0
        ),

    "differences":
        len(problem_records),

    "status_counts":
        dict(status_counter),

    "field_counts":
        dict(field_counter),

    "classification_counts":
        dict(
            classification_counter
        ),

    "differences_detail":
        problem_records,
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
    f"=== VALUE AUDIT FortiOS {args.version} ==="
)

print(
    "Comparable facts :",
    len(records)
)

print(
    "Matches          :",
    status_counter.get(
        "match",
        0
    )
)

print(
    "Differences      :",
    len(problem_records)
)


print()
print(
    "=== BY FIELD ==="
)

for field, count in (
    field_counter.most_common()
):

    print(
        f"{field:15} {count}"
    )


print()
print(
    "=== CLASSIFICATION ==="
)

for name, count in (
    classification_counter.most_common()
):

    print(
        f"{name:35} {count}"
    )


print()
print(
    "=== FIRST DIFFERENCES ==="
)


for index, item in enumerate(
    problem_records[
        :args.samples
    ],
    start=1
):

    print()
    print(
        "-" * 75
    )

    print(
        f"[{index}]",
        item["section"],
        "::",
        item["attribute_path"]
    )

    print(
        "FIELD:",
        item["field"]
    )

    print(
        "STATUS:",
        item["status"]
    )

    print(
        "CLASS:",
        item["classification"]
    )

    print(
        "RAW:",
        item["raw_values"]
    )

    print(
        "NORMALIZED:",
        item[
            "normalized_values"
        ]
    )


print()
print(
    "[OK] Report:",
    OUTPUT
)
