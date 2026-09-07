from pathlib import Path
from collections import Counter
import argparse
import yaml


parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--samples", type=int, default=60)
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

CANONICAL = (
    ROOT
    / "canonical"
)

OUTPUT = (
    ROOT
    / "audit"
    / "range_conflict_evidence.yaml"
)


triage = yaml.safe_load(
    INPUT.read_text(
        encoding="utf-8"
    )
)

conflicts = triage.get(
    "records",
    []
)


# ------------------------------------------------------------
# Charger les sections canoniques
# ------------------------------------------------------------

sections = {}

for file in CANONICAL.glob("*.yaml"):

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

    sections[sid] = data


# ------------------------------------------------------------
# Retrouver un objet via un path du type :
# attributes_flat.foo
# ------------------------------------------------------------

def get_path(data, path):

    current = data

    for part in str(path).split("."):

        if not isinstance(current, dict):
            return None

        if part not in current:
            return None

        current = current[part]

    return current


def compact_source_evidence(data):

    if not isinstance(data, dict):
        return {}

    wanted = (
        "type",
        "description",
        "default",
        "min",
        "max",
        "choices",
        "source_attribute",
        "optional",
        "required",
        "computed",
        "multiple_values",
    )

    result = {}

    for key in wanted:

        if (
            key in data
            and data[key] is not None
        ):
            result[key] = data[key]

    return result


records = []
signal_counter = Counter()


for conflict in conflicts:

    section = conflict.get(
        "section"
    )

    attr_path = conflict.get(
        "attribute_path"
    )

    canonical_section = sections.get(
        section
    )

    attr = None

    if canonical_section:
        attr = get_path(
            canonical_section,
            attr_path
        )


    item = {
        "section":
            section,

        "attribute":
            attr_path,

        "field":
            conflict.get("field"),

        "values":
            conflict.get("raw_values"),

        "triage_class":
            conflict.get("triage_class"),

        "canonical":
            compact_source_evidence(
                attr
            ),
    }


    evidence_out = {}

    if isinstance(attr, dict):

        evidence = attr.get(
            "evidence",
            {}
        )

        if isinstance(evidence, dict):

            for source in (
                "cli_reference",
                "terraform",
                "ansible",
            ):

                src = evidence.get(
                    source
                )

                if isinstance(src, dict):

                    evidence_out[
                        source
                    ] = compact_source_evidence(
                        src
                    )


    item["evidence"] = evidence_out


    # --------------------------------------------------------
    # Détection purement textuelle de signaux intéressants.
    # Pas de résolution automatique.
    # --------------------------------------------------------

    text_parts = []

    for src in evidence_out.values():

        description = src.get(
            "description"
        )

        if description:
            text_parts.append(
                str(description).lower()
            )

    text = " ".join(
        text_parts
    )


    signals = []


    keyword_groups = {

        "sentinel_or_disable": (
            "disable",
            "disabled",
            "0 to disable",
            "zero to disable",
            "0 means",
        ),

        "special_value": (
            "special",
            "random",
            "randomize",
            "unlimited",
            "automatic",
            "auto ",
        ),

        "time_unit": (
            "second",
            "seconds",
            "millisecond",
            "milliseconds",
            "minute",
            "minutes",
            "hour",
            "hours",
        ),

        "size_unit": (
            "byte",
            "bytes",
            "kb",
            "mb",
            "gb",
        ),

        "platform_hint": (
            "platform",
            "model",
            "hardware",
            "memory",
            "cpu",
            "worker",
            "processor",
        ),
    }


    for signal, keywords in (
        keyword_groups.items()
    ):

        if any(
            keyword in text
            for keyword in keywords
        ):

            signals.append(
                signal
            )

            signal_counter[
                signal
            ] += 1


    item["semantic_signals"] = (
        signals
    )

    records.append(
        item
    )


report = {

    "version":
        args.version,

    "total":
        len(records),

    "semantic_signal_counts":
        dict(signal_counter),

    "records":
        records,
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
    f"=== RANGE CONFLICT EVIDENCE {args.version} ==="
)

print(
    "Total:",
    len(records)
)


print()
print(
    "=== SEMANTIC SIGNALS ==="
)

if signal_counter:

    for name, count in (
        signal_counter.most_common()
    ):

        print(
            f"{name:30} {count}"
        )

else:

    print(
        "No textual semantic signals detected."
    )


print()
print(
    "=== CONFLICT EVIDENCE ==="
)


for index, item in enumerate(
    records[:args.samples],
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
        item["attribute"]
    )

    print(
        "FIELD:",
        item["field"]
    )

    print(
        "VALUES:",
        item["values"]
    )

    print(
        "TRIAGE:",
        item["triage_class"]
    )

    print(
        "SIGNALS:",
        item[
            "semantic_signals"
        ]
    )


    for source, evidence in (
        item["evidence"].items()
    ):

        print()
        print(
            " ",
            source.upper()
        )

        for key, value in (
            evidence.items()
        ):

            print(
                "   ",
                key,
                ":",
                value
            )


print()
print(
    "[OK] Report:",
    OUTPUT
)
