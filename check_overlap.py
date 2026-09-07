from pathlib import Path
import yaml

ROOT = Path("knowledge_base/fortios/7.6.7/raw")


def load_ids(folder):
    ids = set()

    if not folder.exists():
        return ids

    for p in folder.glob("*.yaml"):
        try:
            data = yaml.safe_load(
                p.read_text(
                    encoding="utf-8"
                )
            )

            if data and data.get("id"):
                ids.add(data["id"])

        except Exception:
            pass

    return ids


a = load_ids(
    ROOT / "ansible"
)

t = load_ids(
    ROOT / "terraform"
)

c = load_ids(
    ROOT / "docs" / "cli_reference"
)


print("=== COUNTS ===")
print("Ansible   :", len(a))
print("Terraform :", len(t))
print("CLI       :", len(c))

print()
print("=== OVERLAPS ===")

print(
    "Ansible ∩ Terraform :",
    len(a & t)
)

print(
    "Ansible ∩ CLI       :",
    len(a & c)
)

print(
    "Terraform ∩ CLI     :",
    len(t & c)
)

print(
    "ALL 3               :",
    len(a & t & c)
)

print()
print("=== ONLY ONE SOURCE ===")

print(
    "Only Ansible   :",
    len(a - t - c)
)

print(
    "Only Terraform :",
    len(t - a - c)
)

print(
    "Only CLI       :",
    len(c - a - t)
)


print()
print("=== EXEMPLES CLI SANS ANSIBLE/TERRAFORM ===")

for x in sorted(c - a - t)[:30]:
    print(x)


print()
print("=== EXEMPLES TERRAFORM SANS CLI ===")

for x in sorted(t - c)[:30]:
    print(x)


print()
print("=== EXEMPLES ANSIBLE SANS CLI ===")

for x in sorted(a - c)[:30]:
    print(x)
