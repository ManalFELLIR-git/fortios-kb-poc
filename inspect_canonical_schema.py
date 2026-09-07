from pathlib import Path
from pprint import pprint

from kb_builder.utils import load_yaml

VERSION = "7.6.7"

ROOT = (
    Path("knowledge_base")
    / "fortios"
    / VERSION
    / "canonical"
)

samples = [
    ("firewall.ippool", "port_per_user"),
    ("firewall.service.custom", "tcp_rst_timer"),
    ("system.global", "ndp_max_entry"),
    ("firewall.policy", "vlan_cos_fwd"),
    ("alertemail.setting", "alert_interval"),
]

for section, attr in samples:

    path = ROOT / f"{section}.yaml"

    print()
    print("=" * 100)
    print(section, "::", attr)
    print("=" * 100)

    if not path.exists():
        print("FILE NOT FOUND:", path)
        continue

    data = load_yaml(path) or {}

    print()
    print("TOP LEVEL KEYS:")
    print(list(data.keys()))

    attrs = data.get("attributes_flat", {}) or {}

    if attr not in attrs:
        print()
        print("ATTRIBUTE NOT FOUND")
        print("First available attributes:")
        print(list(attrs.keys())[:20])
        continue

    entry = attrs[attr]

    print()
    print("ATTRIBUTE KEYS:")
    if isinstance(entry, dict):
        print(list(entry.keys()))
    else:
        print(type(entry))

    print()
    print("FULL ATTRIBUTE:")
    pprint(entry, width=140, sort_dicts=False)

