from pathlib import Path
import yaml

p = Path(
    "knowledge_base/fortios/7.6.7/audit/section_mapping.yaml"
)

data = yaml.safe_load(
    p.read_text(encoding="utf-8")
)

print("=== SECTION MAPPING AUDIT ===")
print()

print("RAW COUNTS:")
for k, v in data.get("raw_counts", {}).items():
    print(f"  {k}: {v}")

print()

print("ALIASES:")
for k, v in data.get("alias_counts", {}).items():
    print(f"  {k}: {v}")

print()

print("AMBIGUITIES:")
for source, values in data.get(
    "ambiguities", {}
).items():
    print(
        f"  {source}: {len(values or {})}"
    )

print()

print("COLLISIONS:")
for source, values in data.get(
    "collisions", {}
).items():
    print(
        f"  {source}: {len(values or [])}"
    )

print()
print("=== FIRST TERRAFORM ALIASES ===")

for item in data.get(
    "aliases", {}
).get("terraform", [])[:30]:

    print(
        f'{item["from"]}  ->  {item["to"]}'
    )

print()
print("=== AMBIGUITIES DETAIL ===")

for source, values in data.get(
    "ambiguities", {}
).items():

    if not values:
        continue

    print()
    print(source.upper())

    for key, ids in list(
        values.items()
    )[:20]:

        print(
            key,
            "=>",
            ids
        )

print()
print("=== COLLISIONS DETAIL ===")

for source, values in data.get(
    "collisions", {}
).items():

    if not values:
        continue

    print()
    print(source.upper())

    for item in values[:20]:
        print(item)

