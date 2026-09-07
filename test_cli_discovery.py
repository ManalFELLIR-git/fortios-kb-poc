from pathlib import Path

from kb_builder.utils import load_yaml
from kb_builder.fortinet_docs import (
    fetch,
    discover_cli_config_links,
)

cfg = load_yaml(
    Path("config/sources.yaml")
)

version = "7.6.7"

seed = (
    cfg["sources"]
    ["fortinet_docs"]
    ["cli_reference"]
)

html = fetch(
    seed
)

urls = discover_cli_config_links(
    html,
    seed,
    version,
)

print()
print(
    "=== TARGETED CLI DISCOVERY ==="
)

print(
    "Version:",
    version
)

print(
    "Config pages:",
    len(urls)
)

print()
print(
    "First 10:"
)

for url in urls[:10]:
    print(url)

print()
print(
    "Last 10:"
)

for url in urls[-10:]:
    print(url)
