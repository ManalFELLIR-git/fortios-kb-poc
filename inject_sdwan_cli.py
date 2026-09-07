from pathlib import Path

from kb_builder.fortinet_docs import fetch, parse_cli_page
from kb_builder.utils import dump_yaml
from kb_builder.reconcile import reconcile_all
from kb_builder.audit import audit


VERSION = "7.6.7"

URL = (
    "https://docs.fortinet.com/document/"
    "fortigate/7.6.7/cli-reference/"
    "838040159/config-system-sdwan"
)

ROOT = Path(
    "knowledge_base/fortios/7.6.7"
)


print("[1] Téléchargement CLI Reference SD-WAN...")

html = fetch(URL)

print(
    "[OK] HTML reçu :",
    len(html),
    "caractères"
)


print("[2] Parsing...")

item = parse_cli_page(
    html,
    URL,
    VERSION
)

if not item:
    raise RuntimeError(
        "La page SD-WAN n'a pas été reconnue par le parser."
    )

print(
    "[OK] Section détectée :",
    item["id"]
)

print(
    "[OK] Attributs top-level :",
    len(item.get("attributes", {}))
)

print(
    "[OK] Sous-sections :",
    len(item.get("children", {}))
)


print("[3] Écriture YAML...")

out = (
    ROOT
    / "raw"
    / "docs"
    / "cli_reference"
    / "system.sdwan.yaml"
)

dump_yaml(
    out,
    item
)

print(
    "[OK] Écrit :",
    out
)


print("[4] Reconciliation...")

reconcile_all(
    ROOT,
    VERSION
)


print("[5] Audit...")

report = audit(
    ROOT,
    VERSION,
    []
)

print()
print("=== RESULTAT ===")
print(report)

print()
print("=== TERMINÉ ===")
