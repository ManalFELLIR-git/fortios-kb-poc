from pathlib import Path
from collections import Counter
import argparse
import shutil
import yaml

from kb_builder.terraform_extractor import extract_all


parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
args = parser.parse_args()


RESOURCES = Path(".work/terraform/fortios")
DOCS = Path(".work/terraform/website/docs/r")

OUT = (
    Path(".work")
    / "terraform_reextract_test"
    / args.version
)


if OUT.exists():
    shutil.rmtree(OUT)

OUT.mkdir(
    parents=True,
    exist_ok=True
)


results, errors = extract_all(
    RESOURCES,
    args.version,
    OUT,
    DOCS,
)


counts = Counter()

attributes_total = 0


def walk(obj):

    global attributes_total

    if not isinstance(obj, dict):
        return

    # Un attribut Terraform extrait possède normalement type/raw_type.
    if (
        "type" in obj
        or "raw_type" in obj
    ):

        attributes_total += 1

        for key in (
            "choices",
            "default",
            "min",
            "max",
            "min_length",
            "max_length",
            "optional",
            "required",
            "computed",
        ):

            if key in obj:
                counts[key] += 1

    children = obj.get("children")

    if isinstance(children, dict):

        for child in children.values():
            walk(child)


for file in OUT.glob("*.yaml"):

    try:

        data = yaml.safe_load(
            file.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        continue

    attrs = data.get(
        "attributes",
        {}
    )

    if isinstance(attrs, dict):

        for attr in attrs.values():
            walk(attr)


print()
print(
    f"=== TERRAFORM FULL RE-EXTRACTION {args.version} ==="
)

print(
    "Resources extracted :",
    len(results)
)

print(
    "Errors              :",
    len(errors)
)

print(
    "Attributes          :",
    attributes_total
)

print()
print(
    "=== METADATA COVERAGE ==="
)

for key in (
    "choices",
    "default",
    "min",
    "max",
    "min_length",
    "max_length",
    "optional",
    "required",
    "computed",
):

    print(
        f"{key:15}",
        counts.get(key, 0)
    )


if errors:

    print()
    print(
        "=== EXTRACTION ERRORS ==="
    )

    for err in errors[:30]:
        print(err)


print()
print(
    "[TEST OUTPUT]",
    OUT
)
