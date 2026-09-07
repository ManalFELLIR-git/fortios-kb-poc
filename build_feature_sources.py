from pathlib import Path
import argparse
import json

from kb_builder.utils import load_yaml
from kb_builder.feature_sources import build_feature_sources


parser = argparse.ArgumentParser()

parser.add_argument(
    "--version",
    required=True
)

args = parser.parse_args()


cfg = load_yaml(
    Path("config/sources.yaml")
)

seeds = (
    cfg["sources"]
    ["fortinet_docs"]
)

root = (
    Path("knowledge_base")
    / "fortios"
    / args.version
)


report = build_feature_sources(
    args.version,
    seeds,
    root,
)


print()
print(
    "=== FEATURE SOURCE COLLECTION ==="
)

print(
    json.dumps(
        report,
        indent=2
    )
)
