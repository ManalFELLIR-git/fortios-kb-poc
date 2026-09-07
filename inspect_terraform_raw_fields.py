from pathlib import Path
from collections import Counter
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


ROOT = (
    Path("knowledge_base")
    / "fortios"
    / args.version
    / "raw"
    / "terraform"
)


TOKENS = (
    "default",
    "choice",
    "enum",
    "valid",
    "optional",
    "required",
    "computed",
    "multiple",
    "min",
    "max",
)


counter = Counter()
samples = {}


def walk(obj, file_name, path=""):

    if isinstance(obj, dict):

        for key, value in obj.items():

            low = str(key).lower()

            if any(
                token in low
                for token in TOKENS
            ):

                signature = str(key)

                counter[
                    signature
                ] += 1

                if signature not in samples:

                    samples[
                        signature
                    ] = []

                if (
                    len(
                        samples[
                            signature
                        ]
                    )
                    < args.samples
                ):

                    samples[
                        signature
                    ].append({
                        "file":
                            file_name,

                        "path":
                            path,

                        "value":
                            value,
                    })

            child = (
                f"{path}.{key}"
                if path
                else str(key)
            )

            walk(
                value,
                file_name,
                child
            )


    elif isinstance(obj, list):

        for i, value in enumerate(
            obj
        ):

            walk(
                value,
                file_name,
                f"{path}[{i}]"
            )


for file in ROOT.glob(
    "*.yaml"
):

    try:

        data = yaml.safe_load(
            file.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        continue


    walk(
        data,
        file.name
    )


print()
print(
    f"=== TERRAFORM RAW FIELD INVENTORY {args.version} ==="
)


for key, count in (
    counter.most_common()
):

    print()
    print(
        f"{key:30} {count}"
    )

    for sample in samples[
        key
    ]:

        print(
            " ",
            sample
        )


if not counter:

    print(
        "Aucune propriété intéressante détectée."
    )

