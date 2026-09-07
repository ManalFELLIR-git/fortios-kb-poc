from pathlib import Path
import json

from kb_builder.reconcile import reconcile_all
from kb_builder.audit import audit

VERSION = "7.6.7"

ROOT = Path(
    "knowledge_base/fortios/7.6.7"
)

print(
    "=== RECONCILIATION ONLY ==="
)

items = reconcile_all(
    ROOT,
    VERSION
)

report = audit(
    ROOT,
    VERSION,
    []
)

print()
print(
    json.dumps(
        report,
        indent=2
    )
)

print()
print(
    "[OK] Canonical sections:",
    len(items)
)
