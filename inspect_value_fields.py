from pathlib import Path
from collections import Counter
import argparse
import yaml


parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
args = parser.parse_args()


ROOT = (
    Path("knowledge_base")
    / "fortios"
    / args.version
    / "canonical"
)


interesting = Counter()
samples = {}


for path in ROOT.glob("*.yaml"):

    try:
        data = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        continue

    if not isinstance(data, dict):
        continue


    def walk(obj, p=""):

        if isinstance(obj, dict):

            evidence = obj.get("evidence")

            if isinstance(evidence, dict):

                for source, source_data in evidence.items():

                    if not isinstance(source_data, dict):
                        continue

                    for key in source_data:

                        low = str(key).lower()

                        if any(
                            token in low
                            for token in (
                                "default",
                                "choice",
                                "option",
                                "enum",
                                "valid",
                                "value",
                            )
                        ):

                            signature = (
                                source,
                                str(key)
                            )

                            interesting[
                                signature
                            ] += 1

                            samples.setdefault(
                                signature,
                                {
                                    "file": path.name,
                                    "path": p,
                                    "value":
                                        source_data[key],
                                }
                            )

            for key, value in obj.items():

                if key == "evidence":
                    continue

                child = (
                    f"{p}.{key}"
                    if p
                    else str(key)
                )

                walk(
                    value,
                    child
                )

        elif isinstance(obj, list):

            for i, value in enumerate(obj):

                walk(
                    value,
                    f"{p}[{i}]"
                )


    walk(data)


print()
print(
    f"=== DEFAULT / CHOICES INVENTORY {args.version} ==="
)

for (source, key), count in (
    interesting.most_common()
):

    print()
    print(
        f"{source:15} {key:30} {count}"
    )

    print(
        "  sample:",
        samples[(source, key)]
    )


if not interesting:

    print(
        "Aucune clé default/choices/options trouvée dans evidence."
    )
