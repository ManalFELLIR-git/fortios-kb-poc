from pathlib import Path
import argparse
import shutil

from kb_builder.utils import load_yaml
from kb_builder.fortinet_docs import build_cli_reference


parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
args = parser.parse_args()

version = args.version

cfg = load_yaml(
    Path("config/sources.yaml")
)

seed = (
    cfg["sources"]
    ["fortinet_docs"]
    ["cli_reference"]
)

OUT = (
    Path(".work")
    / "cli_reextract_test"
    / version
)

if OUT.exists():
    shutil.rmtree(OUT)

stats, errors = build_cli_reference(
    version,
    seed,
    OUT,
)

print()
print(
    f"=== FULL TARGETED CLI EXTRACTION {version} ==="
)

for k, v in stats.items():
    print(f"{k:30}: {v}")

print(
    f"{'errors':30}: {len(errors)}"
)

if errors:
    print()
    print("=== FIRST ERRORS ===")

    for item in errors[:20]:
        print(item)

print()
print(
    "[TEST OUTPUT]",
    OUT
)
