from pathlib import Path
from collections import Counter
from decimal import Decimal, InvalidOperation
import argparse
import math
import yaml


parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--samples", type=int, default=10)
args = parser.parse_args()


ROOT = (
    Path("knowledge_base")
    / "fortios"
    / args.version
)

INPUT = (
    ROOT
    / "audit"
    / "value_conflict_audit.yaml"
)

OUTPUT = (
    ROOT
    / "audit"
    / "range_conflict_triage.yaml"
)


report = yaml.safe_load(
    INPUT.read_text(
        encoding="utf-8"
    )
)

records = report.get(
    "differences_detail",
    []
)


def number(value):

    try:
        return Decimal(
            str(value)
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError
    ):
        return None


def is_power10_ratio(a, b):

    if (
        a is None
        or b is None
        or a == 0
        or b == 0
    ):
        return None

    ratio = abs(
        float(a / b)
    )

    if ratio < 1:
        ratio = 1 / ratio

    candidates = (
        10,
        100,
        1000,
        1024,
        1000000,
    )

    for candidate in candidates:

        if math.isclose(
            ratio,
            candidate,
            rel_tol=0.02
        ):
            return candidate

    return None


def classify(item):

    values = item.get(
        "raw_values",
        {}
    )

    tf = number(
        values.get(
            "terraform"
        )
    )

    cli = number(
        values.get(
            "cli_reference"
        )
    )


    if (
        tf is None
        or cli is None
    ):
        return (
            "non_numeric_review",
            "low"
        )


    delta = abs(
        tf - cli
    )


    # ------------------------------------------------
    # 1. Différence exacte de 1
    # Peut révéler :
    # - borne inclusive/exclusive
    # - valeur sentinelle
    # - provider légèrement obsolète
    # ------------------------------------------------

    if delta == 1:

        return (
            "boundary_or_sentinel_candidate",
            "medium"
        )


    # ------------------------------------------------
    # 2. Rapport proche de 10/100/1000/1024...
    # Peut révéler un problème d'unité.
    # ------------------------------------------------

    scale = is_power10_ratio(
        tf,
        cli
    )

    if scale:

        return (
            f"scale_or_unit_candidate_x{scale}",
            "medium"
        )


    # ------------------------------------------------
    # 3. Range très dépendant de capacité
    # Aucun verdict : seulement triage.
    # ------------------------------------------------

    attribute = str(
        item.get(
            "attribute_path",
            ""
        )
    ).lower()

    capacity_tokens = (
        "worker",
        "memory",
        "mem",
        "device",
        "session",
        "cpu",
        "npu",
        "scanunit",
        "bandwidth",
        "capacity",
        "queue",
        "process",
        "socket",
    )

    if any(
        token in attribute
        for token in capacity_tokens
    ):

        return (
            "platform_or_capacity_candidate",
            "low"
        )


    # ------------------------------------------------
    # 4. Sinon : désaccord générique à examiner
    # ------------------------------------------------

    return (
        "version_or_provider_candidate",
        "low"
    )


classified = []

counter = Counter()


for item in records:

    if item.get(
        "field"
    ) not in (
        "min",
        "max"
    ):
        continue


    classification, confidence = (
        classify(item)
    )

    new_item = dict(item)

    new_item[
        "triage_class"
    ] = classification

    new_item[
        "triage_confidence"
    ] = confidence


    values = item.get(
        "raw_values",
        {}
    )

    tf = number(
        values.get(
            "terraform"
        )
    )

    cli = number(
        values.get(
            "cli_reference"
        )
    )


    if (
        tf is not None
        and cli is not None
    ):

        new_item[
            "numeric_delta"
        ] = str(
            abs(tf - cli)
        )

        if (
            cli != 0
        ):

            new_item[
                "terraform_cli_ratio"
            ] = float(
                tf / cli
            )


    classified.append(
        new_item
    )

    counter[
        classification
    ] += 1


final = {

    "version":
        args.version,

    "total":
        len(classified),

    "note":
        (
            "Triage heuristique uniquement. "
            "Aucune décision canonique appliquée."
        ),

    "summary":
        dict(counter),

    "records":
        classified,
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
    f"=== RANGE CONFLICT TRIAGE {args.version} ==="
)

print(
    "Total:",
    len(classified)
)

print()


for name, count in (
    counter.most_common()
):

    pct = (
        count
        / len(classified)
        * 100
        if classified
        else 0
    )

    print(
        f"{name:40}"
        f"{count:4} "
        f"({pct:5.1f}%)"
    )


print()
print(
    "=== SAMPLES ==="
)


shown = Counter()


for item in classified:

    klass = item[
        "triage_class"
    ]

    if shown[klass] >= args.samples:
        continue

    shown[klass] += 1

    print()
    print(
        "-" * 75
    )

    print(
        klass
    )

    print(
        item.get("section"),
        "::",
        item.get("attribute_path"),
        "::",
        item.get("field")
    )

    print(
        "values:",
        item.get("raw_values")
    )

    print(
        "delta:",
        item.get("numeric_delta")
    )

    if (
        "terraform_cli_ratio"
        in item
    ):

        print(
            "ratio:",
            item[
                "terraform_cli_ratio"
            ]
        )


print()
print(
    "[OK] Report:",
    OUTPUT
)
